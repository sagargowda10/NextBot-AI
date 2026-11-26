from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalAction, OrderStatus, PaymentStatus, ReturnStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.state import AppState
from app.domain.order_state import assert_transition
from app.domain.returns import check_return_eligibility
from app.events.outbox import add_event
from app.events.schemas import EventType
from app.models.commerce import Order, ReturnRequest
from app.schemas.commerce import ReturnOut
from app.security.permissions import Principal
from app.services.audit_service import audit
from app.services.mappers import return_out


class ReturnService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.window = int(getattr(state.settings, "return_window_days", 10))

    async def request(self, principal: Principal, order_id: int | None, reason: str, agent: str | None = None) -> ReturnOut:
        if order_id is not None:
            order = await self.session.get(Order, order_id)
            if order is None or order.user_id != principal.user_id:
                raise NotFoundError("Order not found")
        else:
            order = await self.session.scalar(
                select(Order)
                .where(Order.user_id == principal.user_id, Order.status.in_([OrderStatus.DELIVERED, OrderStatus.RETURN_REQUESTED]))
                .order_by(Order.delivered_at.desc())
                .limit(1)
            )
            if order is None:
                raise NotFoundError("You don't have a delivered order to return.")
        existing = await self.session.scalar(select(ReturnRequest).where(ReturnRequest.order_id == order.id))
        el = check_return_eligibility(
            status=order.status,
            delivered_at=order.delivered_at,
            window_days=self.window,
            category_slugs=[i.category_slug for i in order.items],
            already_requested=existing is not None,
        )
        if not el.eligible:
            return ReturnOut(
                id=existing.id if existing else 0,
                order_id=order.id,
                order_number=order.order_number,
                status=existing.status if existing else ReturnStatus.REJECTED,
                reason=reason,
                refund_amount=order.total - order.shipping_fee,
                eligible=False,
                eligibility_message=el.reason,
                created_at=datetime.now(UTC),
            )
        async with self.session.begin_nested():
            refund_amount = order.total - order.shipping_fee
            r = ReturnRequest(
                order_id=order.id, user_id=order.user_id, reason=reason, refund_amount=refund_amount, status=ReturnStatus.APPROVED
            )
            self.session.add(r)
            await self.session.flush()
            if self.state.policy.refund_needs_approval(refund_amount):
                from app.services.approval_service import ApprovalService

                r.status = ReturnStatus.PENDING_APPROVAL
                r.approval_request_id = await ApprovalService(self.session, self.state).create(
                    action=ApprovalAction.HIGH_VALUE_REFUND,
                    summary=f"Return {order.order_number}: refund ₹{refund_amount}",
                    payload={"return_id": r.id, "order_id": order.id, "amount": str(refund_amount)},
                    agent=agent,
                    user_id=order.user_id,
                )
            order.status = assert_transition(order.status, OrderStatus.RETURN_REQUESTED)
            add_event(
                self.session,
                EventType.RETURN_REQUESTED,
                "order",
                order.id,
                {"return_id": r.id, "order_number": order.order_number, "user_id": order.user_id, "status": r.status},
            )
            await audit(self.session, principal, "return.request", "return", r.id, {"order_id": order.id})
        await self.session.refresh(r)
        return return_out(r, True, el.reason)

    async def list(self, principal: Principal) -> list[ReturnOut]:
        stmt = select(ReturnRequest).order_by(ReturnRequest.id.desc()).limit(50)
        if not principal.has("return:manage"):
            stmt = stmt.where(ReturnRequest.user_id == principal.user_id)
        return [return_out(r) for r in (await self.session.scalars(stmt)).all()]

    async def get(self, principal: Principal, return_id: int) -> ReturnOut:
        r = await self.session.get(ReturnRequest, return_id)
        if r is None or not principal.can_access_user_resource(r.user_id, "return:manage"):
            raise NotFoundError("Return not found")
        return return_out(r)

    async def mark_received(self, principal: Principal, return_id: int) -> ReturnOut:
        """Warehouse confirms receipt → restock + refund (approved returns only)."""
        r = await self.session.get(ReturnRequest, return_id, with_for_update=True)
        if r is None:
            raise NotFoundError("Return not found")
        if r.status != ReturnStatus.APPROVED:
            raise ConflictError(f"Return is {r.status}")
        from app.services.inventory_service import InventoryService
        from app.services.payment_service import PaymentService

        order = r.order
        async with self.session.begin_nested():
            await InventoryService(self.session, self.state).restock_for_order(order)
            pay = next((p for p in order.payments if p.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED)), None)
            if pay is not None:
                await PaymentService(self.session, self.state).refund_internal(pay, r.refund_amount, "Return received", r.id)
            r.status = ReturnStatus.REFUNDED
            order.status = assert_transition(order.status, OrderStatus.RETURNED)
            await audit(self.session, principal, "return.received", "return", r.id)
        return return_out(r)
