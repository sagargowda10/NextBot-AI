from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrderStatus, PaymentStatus, RefundStatus, ReturnStatus, ShipmentStatus
from app.database.base import Base, TimestampMixin
from app.models.catalog import ProductVariant


class ShoppingCart(TimestampMixin, Base):
    __tablename__ = "shopping_carts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", lazy="selectin", cascade="all, delete-orphan", order_by="CartItem.id"
    )


class CartItem(TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id", name="cart_variant"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("shopping_carts.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    cart: Mapped[ShoppingCart] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship(lazy="selectin")


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=OrderStatus.CREATED, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    shipping_address: Mapped[dict[str, Any]] = mapped_column(default=dict)  # immutable snapshot
    shipping_pincode: Mapped[str | None] = mapped_column(String(6))
    risk_score: Mapped[int | None] = mapped_column(Integer)
    payment_failures: Mapped[int] = mapped_column(Integer, default=0)
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", lazy="selectin", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(lazy="selectin", order_by="Payment.id")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(64))
    category_slug: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    order: Mapped[Order] = relationship(back_populates="items")


class Payment(TimestampMixin, Base):
    """No card data is ever stored: only provider references and status."""

    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.INITIATED, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    provider_reference: Mapped[str | None] = mapped_column(String(80), unique=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    return_request_id: Mapped[int | None] = mapped_column(ForeignKey("return_requests.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default=RefundStatus.PENDING)
    reason: Mapped[str | None] = mapped_column(String(300))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"))
    provider_reference: Mapped[str | None] = mapped_column(String(80))


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    carrier: Mapped[str] = mapped_column(String(40))
    tracking_number: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(24), default=ShipmentStatus.CREATED, index=True)
    estimated_delivery: Mapped[date | None] = mapped_column(Date)
    events: Mapped[list[Any]] = mapped_column(default=list)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class ReturnRequest(TimestampMixin, Base):
    __tablename__ = "return_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)  # one return per order
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=ReturnStatus.REQUESTED, index=True)
    reason: Mapped[str] = mapped_column(Text)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    approval_request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"))
    order: Mapped[Order] = relationship(lazy="selectin")
