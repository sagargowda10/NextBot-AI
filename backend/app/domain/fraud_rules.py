"""Explainable, rule-based fraud scoring.

The score is advisory: a high score routes the order to human review via an
ApprovalRequest. Nothing here auto-rejects a customer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class RiskSignals:
    account_age_days: int
    failed_payments_24h: int
    orders_last_hour: int
    avg_order_value: Decimal
    lifetime_orders: int
    shipping_pincode_changed_recently: bool = False


@dataclass(frozen=True)
class RiskFactor:
    code: str
    points: int
    explanation: str


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    level: str  # LOW | MEDIUM | HIGH
    factors: list[RiskFactor] = field(default_factory=list)
    recommend_manual_review: bool = False

    def explain(self) -> str:
        if not self.factors:
            return "No risk signals detected."
        return "; ".join(f"{f.explanation} (+{f.points})" for f in self.factors)


def assess(signals: RiskSignals, amount: Decimal, review_threshold: int = 60) -> RiskAssessment:
    factors: list[RiskFactor] = []
    if signals.failed_payments_24h >= 3:
        factors.append(RiskFactor("REPEATED_FAILED_PAYMENTS", 35, f"{signals.failed_payments_24h} failed payments in 24h"))
    elif signals.failed_payments_24h >= 1:
        factors.append(RiskFactor("FAILED_PAYMENT", 10, f"{signals.failed_payments_24h} failed payment(s) in 24h"))
    if signals.orders_last_hour >= 4:
        factors.append(RiskFactor("ORDER_VELOCITY", 25, f"{signals.orders_last_hour} orders in the last hour"))
    if signals.lifetime_orders >= 3 and signals.avg_order_value > 0 and amount > signals.avg_order_value * 5:
        factors.append(RiskFactor("UNUSUAL_AMOUNT", 25, f"Amount is >5x the customer's average (₹{signals.avg_order_value:.0f})"))
    if amount >= Decimal("150000"):
        factors.append(RiskFactor("HIGH_VALUE", 20, "Order value above ₹1,50,000"))
    if signals.account_age_days < 1 and amount >= Decimal("25000"):
        factors.append(RiskFactor("NEW_ACCOUNT_HIGH_VALUE", 25, "New account placing a high-value order"))
    if signals.shipping_pincode_changed_recently:
        factors.append(RiskFactor("ADDRESS_CHANGE", 10, "Shipping address changed recently"))
    score = min(100, sum(f.points for f in factors))
    level = "HIGH" if score >= review_threshold else "MEDIUM" if score >= review_threshold // 2 else "LOW"
    return RiskAssessment(score=score, level=level, factors=factors, recommend_manual_review=score >= review_threshold)
