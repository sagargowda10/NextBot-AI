"""Payment gateway adapters. Card data never touches NextBot: real gateways use hosted checkout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.exceptions import ExternalServiceNotConfigured


@dataclass
class GatewayResult:
    provider_reference: str
    status: str  # SUCCEEDED | FAILED | INITIATED
    failure_reason: str | None = None
    simulated: bool = False
    checkout_url: str | None = None


class PaymentGateway(Protocol):
    name: str

    async def charge(self, *, amount: Decimal, currency: str, method: str, order_number: str, idempotency_key: str) -> GatewayResult: ...
    async def refund(self, *, provider_reference: str, amount: Decimal) -> GatewayResult: ...


class MockGateway:
    """Deterministic simulator. `mock_fail` always declines; everything else succeeds immediately."""

    name = "mock"

    async def charge(self, *, amount: Decimal, currency: str, method: str, order_number: str, idempotency_key: str) -> GatewayResult:
        ref = f"mock_pay_{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:16]}"
        if method == "mock_fail":
            return GatewayResult(ref, "FAILED", "Card declined by issuing bank (simulated)", simulated=True)
        return GatewayResult(ref, "SUCCEEDED", simulated=True)

    async def refund(self, *, provider_reference: str, amount: Decimal) -> GatewayResult:
        return GatewayResult(f"mock_rfnd_{uuid.uuid4().hex[:12]}", "SUCCEEDED", simulated=True)


class RazorpayGateway:
    """Razorpay Orders API. Creates an order; the customer completes payment in Razorpay Checkout and the
    result arrives via the signed webhook (`/api/v1/payments/webhook`)."""

    name = "razorpay"
    API = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str | None, key_secret: str | None) -> None:
        if not key_id or not key_secret:
            raise ExternalServiceNotConfigured("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not configured")
        self.auth = (key_id, key_secret)

    async def charge(self, *, amount: Decimal, currency: str, method: str, order_number: str, idempotency_key: str) -> GatewayResult:
        import httpx

        async with httpx.AsyncClient(timeout=15, auth=self.auth) as c:
            r = await c.post(
                f"{self.API}/orders",
                json={
                    "amount": int(amount * 100),
                    "currency": currency,
                    "receipt": order_number,
                    "notes": {"idempotency_key": idempotency_key},
                },
            )
        r.raise_for_status()
        return GatewayResult(r.json()["id"], "INITIATED")

    async def refund(self, *, provider_reference: str, amount: Decimal) -> GatewayResult:
        import httpx

        async with httpx.AsyncClient(timeout=15, auth=self.auth) as c:
            r = await c.post(f"{self.API}/payments/{provider_reference}/refund", json={"amount": int(amount * 100)})
        r.raise_for_status()
        return GatewayResult(r.json()["id"], "SUCCEEDED")


class StripeGateway:
    """Stripe PaymentIntents API (amounts in paise for INR)."""

    name = "stripe"
    API = "https://api.stripe.com/v1"

    def __init__(self, secret_key: str | None) -> None:
        if not secret_key:
            raise ExternalServiceNotConfigured("STRIPE_SECRET_KEY is not configured")
        self.key = secret_key

    async def charge(self, *, amount: Decimal, currency: str, method: str, order_number: str, idempotency_key: str) -> GatewayResult:
        import httpx

        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.API}/payment_intents",
                auth=(self.key, ""),
                headers={"Idempotency-Key": idempotency_key},
                data={"amount": int(amount * 100), "currency": currency.lower(), "metadata[order]": order_number},
            )
        r.raise_for_status()
        return GatewayResult(r.json()["id"], "INITIATED")

    async def refund(self, *, provider_reference: str, amount: Decimal) -> GatewayResult:
        import httpx

        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.API}/refunds", auth=(self.key, ""), data={"payment_intent": provider_reference, "amount": int(amount * 100)}
            )
        r.raise_for_status()
        return GatewayResult(r.json()["id"], "SUCCEEDED")


def build_gateway(provider: str, settings: object) -> PaymentGateway:
    if provider == "razorpay":
        return RazorpayGateway(getattr(settings, "razorpay_key_id", None), getattr(settings, "razorpay_key_secret", None))
    if provider == "stripe":
        return StripeGateway(getattr(settings, "stripe_secret_key", None))
    return MockGateway()
