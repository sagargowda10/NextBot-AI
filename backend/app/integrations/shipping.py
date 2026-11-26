"""Courier adapters: mock courier for local use, Shiprocket-ready adapter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.exceptions import ExternalServiceNotConfigured


@dataclass
class Booking:
    carrier: str
    tracking_number: str
    simulated: bool


class Courier(Protocol):
    name: str

    async def book(self, *, order_number: str, pincode: str, weight_kg: float, address: dict[str, Any]) -> Booking: ...


class MockCourier:
    name = "MockExpress"

    async def book(self, *, order_number: str, pincode: str, weight_kg: float, address: dict[str, Any]) -> Booking:
        return Booking(self.name, f"MX{uuid.uuid4().hex[:10].upper()}", simulated=True)


class ShiprocketCourier:
    """Shiprocket API v1 (`/auth/login` then `/orders/create/adhoc`)."""

    name = "Shiprocket"
    API = "https://apiv2.shiprocket.in/v1/external"

    def __init__(self, email: str | None, password: str | None) -> None:
        if not email or not password:
            raise ExternalServiceNotConfigured("SHIPROCKET_EMAIL / SHIPROCKET_PASSWORD are not configured")
        self.email, self.password = email, password

    async def book(self, *, order_number: str, pincode: str, weight_kg: float, address: dict[str, Any]) -> Booking:
        import httpx

        async with httpx.AsyncClient(timeout=20) as c:
            token = (await c.post(f"{self.API}/auth/login", json={"email": self.email, "password": self.password})).json()["token"]
            r = await c.post(
                f"{self.API}/orders/create/adhoc",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "order_id": order_number,
                    "billing_pincode": pincode,
                    "billing_address": address.get("line1", ""),
                    "billing_city": address.get("city", ""),
                    "billing_state": address.get("state", ""),
                    "billing_phone": address.get("phone", ""),
                    "weight": weight_kg,
                    "shipping_is_billing": True,
                },
            )
        r.raise_for_status()
        data = r.json()
        return Booking(self.name, str(data.get("awb_code") or data.get("shipment_id")), simulated=False)


def build_courier(provider: str, settings: object) -> Courier:
    if provider == "shiprocket":
        return ShiprocketCourier(getattr(settings, "shiprocket_email", None), getattr(settings, "shiprocket_password", None))
    return MockCourier()
