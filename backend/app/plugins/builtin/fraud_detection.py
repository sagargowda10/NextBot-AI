"""Plugin 11 — Fraud Detection: explainable rule-based risk scoring. Flags for review; never auto-rejects."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.fraud_rules import assess
from app.plugins.base import BasePlugin, PluginContext, action


class AssessOrderIn(BaseModel):
    amount: Decimal | None = Field(None, gt=0)  # defaults to the caller's current cart total


class AssessPaymentIn(BaseModel):
    order_id: int = Field(gt=0)


class FraudDetectionPlugin(BasePlugin):
    plugin_id = "fraud_detection"
    name = "Fraud Detection"
    version = "1.0.0"
    description = "Rule-based risk scoring for orders and payments with human-readable reasons and manual-review flags."
    default_config = {"review_threshold": 60}

    def validate_configuration(self, config: dict) -> list[str]:
        t = config.get("review_threshold")
        return [] if isinstance(t, int) and 1 <= t <= 100 else ["review_threshold must be 1-100"]

    async def _assess(self, ctx: PluginContext, amount: Decimal) -> dict:
        signals = await ctx.services.risk.signals_for(ctx.principal.user_id or 0)
        result = assess(signals, amount, int(self.config["review_threshold"]))
        return {
            "score": result.score,
            "level": result.level,
            "recommend_manual_review": result.recommend_manual_review,
            "explanation": result.explain(),
            "amount": str(amount),
            "factors": [{"code": f.code, "points": f.points, "explanation": f.explanation} for f in result.factors],
        }

    @action("assess_order", AssessOrderIn, "order:own", "Risk score for the caller's pending order/cart")
    async def assess_order(self, p: AssessOrderIn, ctx: PluginContext) -> dict:
        amount = p.amount or await ctx.services.risk.cart_total(ctx.principal.user_id or 0)
        return await self._assess(ctx, amount)

    @action("assess_payment", AssessPaymentIn, "payment:own", "Risk score before initiating a payment")
    async def assess_payment(self, p: AssessPaymentIn, ctx: PluginContext) -> dict:
        order = await ctx.services.orders.get(ctx.principal, p.order_id)
        return await self._assess(ctx, order.total)
