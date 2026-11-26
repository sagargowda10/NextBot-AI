"""Human-in-the-loop policy: decides which operations need an administrator's approval."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums import ApprovalAction


@dataclass(frozen=True)
class ApprovalPolicy:
    refund_threshold: Decimal = Decimal("10000")
    cancellation_threshold: Decimal = Decimal("50000")
    inventory_adjustment_units: int = 500
    fraud_review_score: int = 60

    def refund_needs_approval(self, amount: Decimal) -> bool:
        return amount >= self.refund_threshold

    def cancellation_needs_approval(self, amount: Decimal) -> bool:
        return amount >= self.cancellation_threshold

    def inventory_adjustment_needs_approval(self, delta: int) -> bool:
        return abs(delta) >= self.inventory_adjustment_units

    def transaction_needs_review(self, risk_score: int) -> bool:
        return risk_score >= self.fraud_review_score

    def action_for(self, kind: str) -> ApprovalAction:
        return ApprovalAction(kind)
