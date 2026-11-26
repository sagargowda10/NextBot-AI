from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.schemas.common import DTO


# ---------- Cart ----------
class CartItemAdd(DTO):
    variant_id: int = Field(gt=0)
    quantity: int = Field(1, ge=1, le=10)


class CartItemUpdate(DTO):
    quantity: int = Field(ge=0, le=10)


class CartItemOut(DTO):
    id: int
    variant_id: int
    product_id: int
    product_name: str
    sku: str
    size: str | None = None
    colour: str | None = None
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    image_url: str | None = None


class CartOut(DTO):
    id: int
    items: list[CartItemOut] = []
    subtotal: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    shipping: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    coupon_code: str | None = None
    coupon_error: str | None = None


# ---------- Address ----------
class AddressIn(DTO):
    label: str = Field("Home", max_length=40)
    line1: str = Field(min_length=3, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    phone: str = Field(pattern=r"^\+?[0-9]{10,13}$")
    is_default: bool = False


class AddressOut(AddressIn):
    id: int


# ---------- Orders ----------
class CheckoutRequest(DTO):
    address_id: int | None = None  # defaults to the customer's default address
    coupon_code: str | None = Field(None, max_length=40)
    payment_method: str = Field("mock_upi", pattern=r"^(mock_upi|mock_card|mock_fail|razorpay|stripe)$")
    idempotency_key: str | None = Field(None, max_length=80)


class OrderItemOut(DTO):
    id: int
    product_id: int
    variant_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderOut(DTO):
    id: int
    order_number: str
    user_id: int
    status: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping_fee: Decimal
    total: Decimal
    coupon_code: str | None = None
    items: list[OrderItemOut] = []
    shipping_pincode: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None
    risk_score: int | None = None
    payment_status: str | None = None


class CancelRequest(DTO):
    reason: str = Field("Changed my mind", max_length=300)


# ---------- Payments ----------
class PaymentInitiate(DTO):
    order_id: int
    method: str = Field("mock_upi", pattern=r"^(mock_upi|mock_card|mock_fail|razorpay|stripe)$")
    idempotency_key: str = Field(min_length=8, max_length=80)


class PaymentOut(DTO):
    id: int
    order_id: int
    provider: str
    method: str
    amount: Decimal
    currency: str = "INR"
    status: str
    provider_reference: str | None = None
    failure_reason: str | None = None
    is_simulated: bool = True
    created_at: datetime


class PaymentWebhook(DTO):
    event_id: str
    provider_reference: str
    status: str = Field(pattern=r"^(SUCCEEDED|FAILED)$")
    failure_reason: str | None = None


class RefundOut(DTO):
    id: int
    payment_id: int
    amount: Decimal
    status: str
    reason: str | None = None
    approval_request_id: int | None = None


# ---------- Shipments ----------
class ShipmentEvent(DTO):
    status: str
    at: datetime
    location: str | None = None
    note: str | None = None


class ShipmentOut(DTO):
    id: int
    order_id: int
    carrier: str
    tracking_number: str
    status: str
    estimated_delivery: date | None = None
    events: list[ShipmentEvent] = []
    is_simulated: bool = True


class DeliveryEstimateOut(DTO):
    pincode: str
    min_days: int
    max_days: int
    earliest: date
    latest: date
    serviceable: bool
    message: str


class ShipmentStatusUpdate(DTO):
    status: str = Field(pattern=r"^(PACKED|SHIPPED|OUT_FOR_DELIVERY|DELIVERED)$")
    location: str | None = None


# ---------- Returns ----------
class ReturnCreate(DTO):
    order_id: int | None = None  # None → latest delivered order
    reason: str = Field("Not as expected", min_length=3, max_length=500)


class ReturnOut(DTO):
    id: int
    order_id: int
    order_number: str | None = None
    status: str
    reason: str
    refund_amount: Decimal
    eligible: bool = True
    eligibility_message: str = ""
    approval_request_id: int | None = None
    created_at: datetime


# ---------- Inventory ----------
class StockLevel(DTO):
    inventory_id: int | None = None
    variant_id: int
    product_id: int
    product_name: str
    sku: str
    warehouse: str | None = None
    quantity: int
    reserved: int
    available: int
    low_stock: bool = False


class InventoryAdjust(DTO):
    delta: int = Field(ge=-10000, le=10000)
    reason: str = Field(min_length=3, max_length=200)


class InventoryAdjustResult(DTO):
    applied: bool
    stock: StockLevel | None = None
    approval_request_id: int | None = None
    message: str = ""


# ---------- Generic result payload ----------
class ActionResult(DTO):
    ok: bool
    message: str
    data: dict[str, Any] = {}
