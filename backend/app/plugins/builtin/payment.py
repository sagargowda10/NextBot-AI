"""Plugin 4 — Payment: mock gateway + Razorpay/Stripe-ready adapters, verification, refunds."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, HealthStatus, NoInput, PluginContext, action


class InitiateIn(BaseModel):
    order_id: int = Field(gt=0)
    method: str = Field("mock_upi", pattern=r"^(mock_upi|mock_card|mock_fail|razorpay|stripe)$")
    idempotency_key: str = Field(min_length=8, max_length=80)


class PaymentIdIn(BaseModel):
    payment_id: int = Field(gt=0)


class HistoryIn(BaseModel):
    limit: int = Field(10, ge=1, le=50)


class RefundIn(BaseModel):
    payment_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=300)


class PaymentPlugin(BasePlugin):
    plugin_id = "payment"
    name = "Payment"
    version = "2.0.0"
    description = (
        "Payment initiation, verification, history and refunds. Mock gateway in demo mode; Razorpay and Stripe adapters need credentials."
    )
    default_config = {"provider": "mock", "razorpay_key_id": None, "razorpay_key_secret": None, "stripe_secret_key": None}
    secret_keys = frozenset({"razorpay_key_secret", "stripe_secret_key"})

    @property
    def requires_credentials(self) -> bool:  # type: ignore[override]
        return self.config.get("provider") != "mock"

    @property
    def mode(self) -> str:
        return "mock" if self.config.get("provider") == "mock" else "live"

    def validate_configuration(self, config: dict) -> list[str]:
        provider = config.get("provider")
        if provider not in ("mock", "razorpay", "stripe"):
            return ["provider must be mock, razorpay or stripe"]
        if provider == "razorpay" and not (config.get("razorpay_key_id") and config.get("razorpay_key_secret")):
            return ["razorpay requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"]
        if provider == "stripe" and not config.get("stripe_secret_key"):
            return ["stripe requires STRIPE_SECRET_KEY"]
        return []

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"provider={self.config.get('provider')} ({self.mode})")

    @action("initiate", InitiateIn, "payment:own", "Start a payment for one of the caller's orders (idempotent)")
    async def initiate(self, p: InitiateIn, ctx: PluginContext) -> dict:
        return (await ctx.services.payments.initiate(ctx.principal, p.order_id, p.method, p.idempotency_key)).model_dump(mode="json")

    @action("verify", PaymentIdIn, "payment:own", "Current status of a payment")
    async def verify(self, p: PaymentIdIn, ctx: PluginContext) -> dict:
        return (await ctx.services.payments.get(ctx.principal, p.payment_id)).model_dump(mode="json")

    @action("history", HistoryIn, "payment:own", "Caller's recent payments")
    async def history(self, p: HistoryIn, ctx: PluginContext) -> dict:
        items = await ctx.services.payments.history(ctx.principal, p.limit)
        return {"items": [i.model_dump(mode="json") for i in items]}

    @action("refund", RefundIn, "payment:refund", "Refund a payment (high values require approval)")
    async def refund(self, p: RefundIn, ctx: PluginContext) -> dict:
        res = await ctx.services.payments.refund(ctx.principal, p.payment_id, p.amount, p.reason, agent=ctx.agent)
        return res.model_dump(mode="json")

    @action("providers", NoInput, "catalog:read", "Configured payment provider and mode")
    async def providers(self, p: NoInput, ctx: PluginContext) -> dict:
        return {
            "provider": self.config.get("provider"),
            "mode": self.mode,
            "adapters": {"mock": "ready", "razorpay": "requires credentials", "stripe": "requires credentials"},
        }
