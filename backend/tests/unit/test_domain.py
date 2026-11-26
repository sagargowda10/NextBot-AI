from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums import OrderStatus
from app.core.exceptions import ConflictError
from app.domain.approvals import ApprovalPolicy
from app.domain.delivery import estimate_delivery
from app.domain.fraud_rules import RiskSignals, assess
from app.domain.order_state import assert_transition, can_transition, is_cancellable
from app.domain.pricing import CouponRule, LineInput, calculate_totals
from app.domain.returns import check_return_eligibility

D = Decimal


class TestPricing:
    def test_free_shipping_above_threshold_and_gst_inclusive(self):
        t = calculate_totals([LineInput(D("1180"), 1)])
        assert t.shipping == 0 and t.total == D("1180.00") and t.tax == D("180.00")

    def test_shipping_fee_below_threshold(self):
        t = calculate_totals([LineInput(D("500"), 1)])
        assert t.shipping == D("79.00") and t.total == D("579.00")

    def test_percent_coupon_with_cap(self):
        c = CouponRule("WELCOME10", "PERCENT", D("10"), min_order_value=D("1500"), max_discount=D("1000"))
        t = calculate_totals([LineInput(D("54990"), 1)], c)
        assert t.discount == D("1000.00") and t.coupon_code == "WELCOME10"

    def test_coupon_min_order_and_expiry(self):
        c = CouponRule("FLAT500", "FLAT", D("500"), min_order_value=D("4999"))
        assert calculate_totals([LineInput(D("2000"), 1)], c).coupon_error.startswith("Minimum order")
        expired = CouponRule("OLD", "FLAT", D("100"), expires_at=datetime.now(UTC) - timedelta(days=1))
        assert calculate_totals([LineInput(D("2000"), 1)], expired).coupon_error == "Coupon has expired"


class TestOrderStateMachine:
    def test_happy_path(self):
        path = [
            OrderStatus.CREATED,
            OrderStatus.PAYMENT_PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.PACKED,
            OrderStatus.SHIPPED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.RETURN_REQUESTED,
            OrderStatus.RETURNED,
        ]
        for a, b in zip(path, path[1:], strict=False):
            assert can_transition(a, b)

    def test_illegal_transition_raises(self):
        with pytest.raises(ConflictError):
            assert_transition(OrderStatus.SHIPPED, OrderStatus.CANCELLED)
        assert not is_cancellable(OrderStatus.PACKED) and is_cancellable(OrderStatus.CONFIRMED)


class TestReturns:
    now = datetime(2026, 11, 20, tzinfo=UTC)

    def test_within_window(self):
        e = check_return_eligibility(
            status="DELIVERED", delivered_at=self.now - timedelta(days=3), category_slugs=["footwear"], window_days=10, now=self.now
        )
        assert e.eligible

    def test_window_closed(self):
        e = check_return_eligibility(
            status="DELIVERED", delivered_at=self.now - timedelta(days=11), category_slugs=[], window_days=10, now=self.now
        )
        assert not e.eligible and "window ended" in e.reason

    def test_not_delivered_and_non_returnable(self):
        assert not check_return_eligibility(status="SHIPPED", delivered_at=None, category_slugs=[], window_days=10).eligible
        e = check_return_eligibility(status="DELIVERED", delivered_at=self.now, category_slugs=["innerwear"], window_days=10, now=self.now)
        assert not e.eligible and "innerwear" in e.reason


class TestDelivery:
    def test_zones(self):
        now = datetime(2026, 11, 20, tzinfo=UTC)
        assert estimate_delivery("560001", now).max_days == 1
        assert (estimate_delivery("570001", now).min_days, estimate_delivery("570001", now).max_days) == (1, 2)
        assert estimate_delivery("110001", now).max_days == 5
        assert not estimate_delivery("12345", now).serviceable


class TestFraud:
    def test_low_risk(self):
        r = assess(RiskSignals(400, 0, 0, D("3000"), 10), D("2500"))
        assert r.score == 0 and r.level == "LOW" and not r.recommend_manual_review

    def test_high_risk_is_explained_and_only_recommends_review(self):
        r = assess(RiskSignals(0, 4, 5, D("2000"), 3), D("160000"))
        assert r.recommend_manual_review and r.level == "HIGH" and r.score == 100
        codes = {f.code for f in r.factors}
        assert {"REPEATED_FAILED_PAYMENTS", "ORDER_VELOCITY", "UNUSUAL_AMOUNT", "HIGH_VALUE"} <= codes
        assert "failed payments" in r.explain()


def test_approval_policy_thresholds():
    p = ApprovalPolicy()
    assert p.refund_needs_approval(D("10000")) and not p.refund_needs_approval(D("9999"))
    assert p.cancellation_needs_approval(D("50000")) and p.inventory_adjustment_needs_approval(-600)
    assert p.transaction_needs_review(60) and not p.transaction_needs_review(59)
