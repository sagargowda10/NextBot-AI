"""Checkout and order lifecycle."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalAction, OrderStatus, PaymentStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.state import AppState
from app.domain.fraud_rules import RiskSignals
from app.domain.order_state import assert_transition, is_cancellable
from app.domain.pricing import LineInput, calculate_totals
from app.events.outbox import add_event
from app.events.schemas import EventType
from app.models.commerce import Order, OrderItem, Payment
from app.models.user import Address, User
from app.schemas.commerce import CheckoutRequest, OrderOut
from app.security.permissions import Principal
from app.services.audit_service import audit
from app.services.cart_service import CartService, coupon_rule
from app.services.inventory_service import InventoryService
from app.services.mappers import order_out

RESERVATION_MINUTES = 30
PAID_STATUSES = (
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
    OrderStatus.RETURN_REQUESTED,
)


def new_order_number() -> str:
    return f"NB-{datetime.now(UTC):%y%m%d}-{secrets.token_hex(3).upper()}"


class OrderService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.cart = CartService(session, state)
        self.inventory = InventoryService(session, state)

    async def _load(self, principal: Principal, order_id: int) -> Order:
        order = await self.session.get(Order, order_id)
        # Same error for "missing" and "not yours" so order IDs can't be probed.
        if order is None or not principal.can_access_user_resource(order.user_id, "order:read_all"):
            raise NotFoundError("Order not found")
        return order

    async def _address(self, user_id: int, address_id: int | None) -> Address:
        stmt = select(Address).where(Address.user_id == user_id)
        stmt = stmt.where(Address.id == address_id) if address_id else stmt.order_by(Address.is_default.desc(), Address.id)
        addr = await self.session.scalar(stmt.limit(1))
        if addr is None:
            raise ValidationFailed("Please add a delivery address before checking out")
        return addr

    async def checkout(self, principal: Principal, req: CheckoutRequest, risk_score: int | None = None) -> OrderOut:
        if principal.user_id is None:
            raise ValidationFailed("Only customers can check out")
        async with self.session.begin_nested():  # all-or-nothing: order rows, reservation, cart clear, outbox
            cart = await self.cart.get(principal.user_id)
            if not cart.items:
                raise ValidationFailed("Your cart is empty")
            addr = await self._address(principal.user_id, req.address_id)
            coupon = await self.cart.coupon(req.coupon_code or cart.coupon_code)
            totals = calculate_totals([LineInput(i.unit_price, i.quantity) for i in cart.items], coupon_rule(coupon) if coupon else None)
            if req.coupon_code and totals.coupon_error:
                raise ValidationFailed(totals.coupon_error)
            from app.models.catalog import ProductVariant

            order = Order(
                order_number=new_order_number(),
                user_id=principal.user_id,
                status=OrderStatus.CREATED,
                subtotal=totals.subtotal,
                discount=totals.discount,
                tax=totals.tax,
                shipping_fee=totals.shipping,
                total=totals.total,
                coupon_code=totals.coupon_code,
                shipping_pincode=addr.pincode,
                risk_score=risk_score,
                shipping_address={
                    "line1": addr.line1,
                    "line2": addr.line2,
                    "city": addr.city,
                    "state": addr.state,
                    "pincode": addr.pincode,
                    "phone": addr.phone,
                },
                reservation_expires_at=datetime.now(UTC) + timedelta(minutes=RESERVATION_MINUTES),
            )
            for ci in cart.items:
                variant = await self.session.get(ProductVariant, ci.variant_id)
                order.items.append(
                    OrderItem(
                        product_id=ci.product_id,
                        variant_id=ci.variant_id,
                        product_name=ci.product_name,
                        sku=ci.sku,
                        quantity=ci.quantity,
                        unit_price=ci.unit_price,
                        line_total=ci.line_total,
                        category_slug=variant.product.category.slug if variant else "",
                    )
                )
            self.session.add(order)
            await self.session.flush()
            await self.inventory.reserve_for_order(order.id)
            order.status = assert_transition(order.status, OrderStatus.PAYMENT_PENDING)
            if coupon is not None and totals.coupon_code:
                coupon.used_count += 1
            await self.cart.clear(principal.user_id)
            add_event(
                self.session,
                EventType.ORDER_CREATED,
                "order",
                order.id,
                {"order_number": order.order_number, "user_id": order.user_id, "total": str(order.total)},
            )
            if risk_score is not None and self.state.policy.transaction_needs_review(risk_score):
                from app.services.approval_service import ApprovalService

                await ApprovalService(self.session, self.state).create(
                    action=ApprovalAction.SUSPICIOUS_TRANSACTION,
                    summary=f"Review order {order.order_number} (risk {risk_score})",
                    payload={"order_id": order.id, "risk_score": risk_score},
                    agent="fraud_detection",
                    user_id=order.user_id,
                )
            await audit(self.session, principal, "order.checkout", "order", order.id, {"total": str(order.total)})
        await self.session.refresh(order)
        return order_out(order)

    async def get(self, principal: Principal, order_id: int) -> OrderOut:
        return order_out(await self._load(principal, order_id))

    async def latest(self, principal: Principal, status: str | None = None) -> OrderOut | None:
        stmt = select(Order).where(Order.user_id == principal.user_id)
        if status:
            stmt = stmt.where(Order.status == status)
        o = await self.session.scalar(stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(1))
        return order_out(o) if o else None

    async def history(self, principal: Principal, limit: int = 10, offset: int = 0) -> list[OrderOut]:
        stmt = select(Order).where(Order.user_id == principal.user_id).order_by(Order.created_at.desc(), Order.id.desc())
        return [order_out(o) for o in (await self.session.scalars(stmt.offset(offset).limit(limit))).all()]

    async def count_for(self, principal: Principal) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(Order).where(Order.user_id == principal.user_id)) or 0)

    async def list_all(self, offset: int, limit: int, status: str | None = None) -> tuple[list[OrderOut], int]:
        stmt = select(Order)
        cnt = select(func.count()).select_from(Order)
        if status:
            stmt, cnt = stmt.where(Order.status == status), cnt.where(Order.status == status)
        rows = (await self.session.scalars(stmt.order_by(Order.id.desc()).offset(offset).limit(limit))).all()
        return [order_out(o) for o in rows], int(await self.session.scalar(cnt) or 0)

    async def cancel(self, principal: Principal, order_id: int, reason: str, agent: str | None = None) -> dict[str, Any]:
        order = await self._load(principal, order_id)
        if not is_cancellable(order.status):
            raise ConflictError(f"Order is already {order.status.lower().replace('_', ' ')} and can no longer be cancelled")
        if self.state.policy.cancellation_needs_approval(order.total) and not principal.has("order:manage"):
            from app.services.approval_service import ApprovalService

            aid = await ApprovalService(self.session, self.state).create(
                action=ApprovalAction.LARGE_ORDER_CANCELLATION,
                summary=f"Cancel {order.order_number} ({order.total}): {reason}",
                payload={"order_id": order.id, "reason": reason},
                agent=agent,
                user_id=order.user_id,
            )
            return {"order": order_out(order).model_dump(mode="json"), "approval_request_id": aid}
        await self.perform_cancel(order, reason, principal)
        return {"order": order_out(order).model_dump(mode="json"), "approval_request_id": None}

    async def perform_cancel(self, order: Order, reason: str, principal: Principal | None) -> None:
        async with self.session.begin_nested():
            paid = order.status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING)
            order.status = assert_transition(order.status, OrderStatus.CANCELLED)
            order.cancelled_at = datetime.now(UTC)
            if paid:
                await self.inventory.restock_for_order(order)
                from app.services.payment_service import PaymentService

                pay = next((p for p in order.payments if p.status == PaymentStatus.SUCCEEDED), None)
                if pay is not None:
                    await PaymentService(self.session, self.state).refund_internal(pay, order.total, f"Order cancelled: {reason}")
            else:
                await self.inventory.release_for_order(order.id)
            await audit(self.session, principal, "order.cancel", "order", order.id, {"reason": reason})

    async def expire_stale_reservations(self) -> int:
        """Release stock held by unpaid orders whose reservation window passed."""
        now = datetime.now(UTC)
        rows = (
            await self.session.scalars(
                select(Order).where(Order.status == OrderStatus.PAYMENT_PENDING, Order.reservation_expires_at < now).limit(100)
            )
        ).all()
        for o in rows:
            await self.perform_cancel(o, "Payment not completed in time", None)
        return len(rows)


class RiskDataService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def signals_for(self, user_id: int) -> RiskSignals:
        now = datetime.now(UTC)
        user = await self.session.get(User, user_id)
        created = user.created_at if user and user.created_at else now
        created = created if created.tzinfo else created.replace(tzinfo=UTC)
        failed = await self.session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.user_id == user_id, Payment.status == PaymentStatus.FAILED, Payment.created_at >= now - timedelta(hours=24))
        )
        recent = await self.session.scalar(
            select(func.count()).select_from(Order).where(Order.user_id == user_id, Order.created_at >= now - timedelta(hours=1))
        )
        avg, n = (
            await self.session.execute(
                select(func.avg(Order.total), func.count()).where(Order.user_id == user_id, Order.status.in_(PAID_STATUSES))
            )
        ).one()
        addr_changed = await self.session.scalar(
            select(func.count())
            .select_from(Address)
            .where(Address.user_id == user_id, Address.updated_at >= now - timedelta(days=1), Address.created_at < now - timedelta(days=1))
        )
        return RiskSignals(
            account_age_days=max(0, (now - created).days),
            failed_payments_24h=int(failed or 0),
            orders_last_hour=int(recent or 0),
            avg_order_value=Decimal(str(avg or 0)),
            lifetime_orders=int(n or 0),
            shipping_pincode_changed_recently=bool(addr_changed),
        )

    async def cart_total(self, user_id: int) -> Decimal:
        return await CartService(self.session, self.state).total(user_id)
