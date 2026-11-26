"""ORM → DTO mapping. API responses are always DTOs, never ORM entities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.models.catalog import Product, ProductVariant
from app.models.commerce import Order, Payment, ReturnRequest, Shipment
from app.models.inventory import Inventory
from app.schemas.catalog import ProductDetail, ProductSummary, VariantOut
from app.schemas.commerce import OrderItemOut, OrderOut, PaymentOut, ReturnOut, ShipmentEvent, ShipmentOut, StockLevel

PLACEHOLDER_IMG = "/images/placeholder-product.svg"


def variant_out(v: ProductVariant, available: dict[int, int]) -> VariantOut:
    return VariantOut(id=v.id, sku=v.sku, size=v.size, colour=v.colour, price=v.effective_price, stock_available=available.get(v.id, 0))


def product_summary(p: Product, available: dict[int, int], score: float | None = None) -> ProductSummary:
    variants = [variant_out(v, available) for v in p.variants if v.is_active]
    disc = int(round((float(p.mrp) - float(p.price)) / float(p.mrp) * 100)) if p.mrp else 0
    return ProductSummary(
        id=p.id,
        name=p.name,
        slug=p.slug,
        brand=p.brand.name,
        category=p.category.slug,
        price=p.price,
        mrp=p.mrp,
        discount_percent=disc,
        rating=p.rating,
        image_url=p.images[0].url if p.images else PLACEHOLDER_IMG,
        in_stock=any(v.stock_available > 0 for v in variants),
        variants=variants,
        score=score,
    )


def product_detail(p: Product, available: dict[int, int], review_count: int = 0) -> ProductDetail:
    s = product_summary(p, available)
    return ProductDetail(
        **s.model_dump(),
        description=p.description,
        specifications=p.specifications or {},
        images=[i.url for i in p.images] or [PLACEHOLDER_IMG],
        review_count=review_count,
    )


def order_out(o: Order) -> OrderOut:
    last_payment = o.payments[-1].status if o.payments else None
    return OrderOut(
        id=o.id,
        order_number=o.order_number,
        user_id=o.user_id,
        status=o.status,
        subtotal=o.subtotal,
        discount=o.discount,
        tax=o.tax,
        shipping_fee=o.shipping_fee,
        total=o.total,
        coupon_code=o.coupon_code,
        shipping_pincode=o.shipping_pincode,
        created_at=o.created_at,
        delivered_at=o.delivered_at,
        risk_score=o.risk_score,
        payment_status=last_payment,
        items=[
            OrderItemOut(
                id=i.id,
                product_id=i.product_id,
                variant_id=i.variant_id,
                product_name=i.product_name,
                sku=i.sku,
                quantity=i.quantity,
                unit_price=i.unit_price,
                line_total=i.line_total,
            )
            for i in o.items
        ],
    )


def payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        order_id=p.order_id,
        provider=p.provider,
        method=p.method,
        amount=p.amount,
        currency=p.currency,
        status=p.status,
        provider_reference=p.provider_reference,
        failure_reason=p.failure_reason,
        is_simulated=p.is_simulated,
        created_at=p.created_at,
    )


def shipment_out(s: Shipment) -> ShipmentOut:
    events = [
        ShipmentEvent(status=e["status"], at=datetime.fromisoformat(e["at"]), location=e.get("location"), note=e.get("note"))
        for e in (s.events or [])
    ]
    return ShipmentOut(
        id=s.id,
        order_id=s.order_id,
        carrier=s.carrier,
        tracking_number=s.tracking_number,
        status=s.status,
        estimated_delivery=s.estimated_delivery,
        events=events,
        is_simulated=s.is_simulated,
    )


def return_out(r: ReturnRequest, eligible: bool = True, message: str = "") -> ReturnOut:
    return ReturnOut(
        id=r.id,
        order_id=r.order_id,
        order_number=r.order.order_number if r.order else None,
        status=r.status,
        reason=r.reason,
        refund_amount=r.refund_amount,
        eligible=eligible,
        eligibility_message=message,
        approval_request_id=r.approval_request_id,
        created_at=r.created_at,
    )


def stock_level(inv: Inventory, threshold: int = 5) -> StockLevel:
    v = inv.variant
    return StockLevel(
        inventory_id=inv.id,
        variant_id=v.id,
        product_id=v.product_id,
        product_name=v.product.name,
        sku=v.sku,
        warehouse=inv.warehouse.code if inv.warehouse else None,
        quantity=inv.quantity,
        reserved=inv.reserved,
        available=inv.available,
        low_stock=inv.available <= threshold,
    )


def zero() -> Decimal:
    return Decimal("0")
