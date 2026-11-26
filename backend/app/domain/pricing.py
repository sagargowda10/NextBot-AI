"""Cart pricing rules: subtotal, coupon discounts, GST, shipping. Pure functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

GST_RATE = Decimal("0.18")
FREE_SHIPPING_THRESHOLD = Decimal("999")
SHIPPING_FEE = Decimal("79")
TWO = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineInput:
    unit_price: Decimal
    quantity: int


@dataclass(frozen=True)
class CouponRule:
    code: str
    discount_type: str  # "PERCENT" | "FLAT"
    value: Decimal
    min_order_value: Decimal = Decimal("0")
    max_discount: Decimal | None = None
    active: bool = True
    expires_at: datetime | None = None


@dataclass(frozen=True)
class CartTotals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal
    coupon_code: str | None = None
    coupon_error: str | None = None


def coupon_discount(rule: CouponRule, subtotal: Decimal, now: datetime | None = None) -> tuple[Decimal, str | None]:
    now = now or datetime.now(UTC)
    if not rule.active:
        return Decimal("0"), "Coupon is inactive"
    if rule.expires_at is not None and rule.expires_at.replace(tzinfo=rule.expires_at.tzinfo or UTC) < now:
        return Decimal("0"), "Coupon has expired"
    if subtotal < rule.min_order_value:
        return Decimal("0"), f"Minimum order value is ₹{rule.min_order_value}"
    if rule.discount_type == "PERCENT":
        disc = subtotal * rule.value / Decimal(100)
    else:
        disc = rule.value
    if rule.max_discount is not None:
        disc = min(disc, rule.max_discount)
    return money(min(disc, subtotal)), None


def calculate_totals(lines: list[LineInput], coupon: CouponRule | None = None) -> CartTotals:
    """Prices are GST-inclusive in the catalogue; tax is reported as the included component."""
    subtotal = money(sum((line.unit_price * line.quantity for line in lines), Decimal("0")))
    discount, coupon_error = (Decimal("0"), None)
    if coupon is not None:
        discount, coupon_error = coupon_discount(coupon, subtotal)
    taxable = subtotal - discount
    tax = money(taxable - taxable / (1 + GST_RATE))
    shipping = Decimal("0") if taxable >= FREE_SHIPPING_THRESHOLD or taxable == 0 else SHIPPING_FEE
    return CartTotals(
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        shipping=money(shipping),
        total=money(taxable + shipping),
        coupon_code=coupon.code if coupon and coupon_error is None else None,
        coupon_error=coupon_error,
    )
