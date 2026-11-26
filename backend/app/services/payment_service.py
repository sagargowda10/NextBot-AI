"""Payments: idempotent initiation, gateway callbacks (signed webhooks), failure policy, refunds."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalAction, ApprovalStatus, OrderStatus, PaymentStatus, RefundStatus
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, PaymentError, ValidationFailed
from app.core.logging import get_logger
from app.core.state import AppState
from app.domain.order_state import assert_transition
from app.events.outbox import add_event
from app.events.schemas import EventType
from app.models.commerce import Order, Payment, Refund
from app.models.platform import ApprovalRequest, ProcessedEvent
from app.models.user import CustomerProfile
from app.schemas.commerce import PaymentOut, PaymentWebhook, RefundOut
from app.security import webhooks
from app.security.permissions import Principal
from app.services.audit_service import audit
from app.services.inventory_service import InventoryService
from app.services.mappers import payment_out

log = get_logger("payments")


class PaymentService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.inventory = InventoryService(session, state)
        self.max_failures = int(getattr(state.settings, "max_payment_failures", 3))

    async def initiate(self, principal: Principal, order_id: int, method: str, idempotency_key: str) -> PaymentOut:
        existing = await self.session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing is not None:  # idempotent replay: same key → same result, no double charge
            if existing.user_id != principal.user_id or existing.order_id != order_id:
                raise ConflictError("Idempotency key already used for a different payment")
            return payment_out(existing)
        order = await self.session.get(Order, order_id, with_for_update=True)
        if order is None or order.user_id != principal.user_id:
            raise NotFoundError("Order not found")
        if order.status != OrderStatus.PAYMENT_PENDING:
            raise ConflictError(f"Order is {order.status}; payment is not required")
        under_review = await self.session.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.action == ApprovalAction.SUSPICIOUS_TRANSACTION,
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.requested_for_user_id == order.user_id,
            )
        )
        if under_review and order.risk_score is not None and self.state.policy.transaction_needs_review(order.risk_score):
            raise PaymentError("This order is being reviewed by our team. No money has been taken.")
        provider = self.state.gateway.name
        async with self.session.begin_nested():
            pay = Payment(
                order_id=order.id,
                user_id=order.user_id,
                provider=provider,
                method=method,
                amount=order.total,
                status=PaymentStatus.INITIATED,
                idempotency_key=idempotency_key,
            )
            order.payments.append(pay)
            await self.session.flush()
            add_event(self.session, EventType.PAYMENT_INITIATED, "payment", pay.id, {"order_id": order.id, "amount": str(order.total)})
            res = await self.state.gateway.charge(
                amount=order.total, currency="INR", method=method, order_number=order.order_number, idempotency_key=idempotency_key
            )
            pay.provider_reference, pay.is_simulated = res.provider_reference, res.simulated
            if res.status == PaymentStatus.SUCCEEDED:
                await self._succeed(pay, order)
            elif res.status == PaymentStatus.FAILED:
                await self._fail(pay, order, res.failure_reason or "Declined")
            await audit(self.session, principal, "payment.initiate", "payment", pay.id, {"status": pay.status, "provider": provider})
        return payment_out(pay)

    async def _succeed(self, pay: Payment, order: Order) -> None:
        pay.status = PaymentStatus.SUCCEEDED
        order.status = assert_transition(order.status, OrderStatus.CONFIRMED)
        order.confirmed_at = datetime.now(UTC)
        order.reservation_expires_at = None
        await self.inventory.commit_for_order(order)
        prof = await self.session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == order.user_id))
        if prof is not None:
            prof.lifetime_value = (prof.lifetime_value or Decimal("0")) + order.total
            prof.loyalty_points += int(order.total // 100)
        add_event(
            self.session,
            EventType.PAYMENT_SUCCESSFUL,
            "order",
            order.id,
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "user_id": order.user_id,
                "total": str(order.total),
                "reference": pay.provider_reference,
            },
        )

    async def _fail(self, pay: Payment, order: Order, reason: str) -> None:
        pay.status, pay.failure_reason = PaymentStatus.FAILED, reason[:200]
        order.payment_failures += 1
        add_event(
            self.session,
            EventType.PAYMENT_FAILED,
            "order",
            order.id,
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "user_id": order.user_id,
                "reason": reason,
                "attempt": order.payment_failures,
            },
        )
        if order.payment_failures >= self.max_failures:  # stop holding stock for an order that can't be paid
            from app.services.order_service import OrderService

            await OrderService(self.session, self.state).perform_cancel(order, "Too many failed payment attempts", None)

    async def handle_webhook(self, body: bytes, signature: str | None) -> dict[str, str]:
        if not webhooks.verify(self.state.settings.webhook_secret, body, signature):
            raise AuthenticationError("Invalid webhook signature")
        evt = PaymentWebhook.model_validate(json.loads(body))
        dup = await self.session.scalar(
            select(ProcessedEvent.id).where(ProcessedEvent.consumer == "payment_webhook", ProcessedEvent.event_id == evt.event_id)
        )
        if dup:
            return {"status": "duplicate"}
        pay = await self.session.scalar(select(Payment).where(Payment.provider_reference == evt.provider_reference))
        if pay is None:
            raise NotFoundError("Unknown payment reference")
        self.session.add(ProcessedEvent(consumer="payment_webhook", event_id=evt.event_id))
        if pay.status != PaymentStatus.INITIATED:
            return {"status": "ignored", "payment_status": pay.status}
        order = await self.session.get(Order, pay.order_id, with_for_update=True)
        assert order is not None
        if evt.status == "SUCCEEDED":
            await self._succeed(pay, order)
        else:
            await self._fail(pay, order, evt.failure_reason or "Declined")
        return {"status": "processed", "payment_status": pay.status}

    async def get(self, principal: Principal, payment_id: int) -> PaymentOut:
        pay = await self.session.get(Payment, payment_id)
        if pay is None or not principal.can_access_user_resource(pay.user_id, "payment:read_all"):
            raise NotFoundError("Payment not found")
        return payment_out(pay)

    async def history(self, principal: Principal, limit: int = 10) -> list[PaymentOut]:
        rows = (
            await self.session.scalars(select(Payment).where(Payment.user_id == principal.user_id).order_by(Payment.id.desc()).limit(limit))
        ).all()
        return [payment_out(p) for p in rows]

    async def refund(self, principal: Principal, payment_id: int, amount: Decimal, reason: str, agent: str | None = None) -> RefundOut:
        pay = await self.session.get(Payment, payment_id)
        if pay is None:
            raise NotFoundError("Payment not found")
        if agent is not None and self.state.policy.refund_needs_approval(amount):  # agents propose, humans approve
            from app.services.approval_service import ApprovalService

            aid = await ApprovalService(self.session, self.state).create(
                action=ApprovalAction.HIGH_VALUE_REFUND,
                summary=f"Refund ₹{amount} on payment {pay.id}: {reason}",
                payload={"payment_id": pay.id, "amount": str(amount), "reason": reason},
                agent=agent,
                user_id=pay.user_id,
            )
            return RefundOut(
                id=0, payment_id=pay.id, amount=amount, status=RefundStatus.PENDING_APPROVAL, reason=reason, approval_request_id=aid
            )
        return await self.refund_internal(pay, amount, reason)

    async def refund_internal(self, pay: Payment, amount: Decimal, reason: str, return_request_id: int | None = None) -> RefundOut:
        if pay.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
            raise ValidationFailed("Only successful payments can be refunded")
        already = Decimal(
            str(
                await self.session.scalar(
                    select(func.coalesce(func.sum(Refund.amount), 0)).where(
                        Refund.payment_id == pay.id, Refund.status == RefundStatus.COMPLETED
                    )
                )
                or 0
            )
        )
        if amount <= 0 or already + amount > pay.amount:
            raise ValidationFailed("Refund exceeds the captured amount")
        add_event(self.session, EventType.REFUND_INITIATED, "payment", pay.id, {"amount": str(amount)})
        res = await self.state.gateway.refund(provider_reference=pay.provider_reference or "", amount=amount)
        refund = Refund(
            payment_id=pay.id,
            amount=amount,
            status=RefundStatus.COMPLETED,
            reason=reason,
            provider_reference=res.provider_reference,
            return_request_id=return_request_id,
        )
        self.session.add(refund)
        pay.status = PaymentStatus.REFUNDED if already + amount >= pay.amount else PaymentStatus.PARTIALLY_REFUNDED
        await self.session.flush()
        order = await self.session.get(Order, pay.order_id)
        add_event(
            self.session,
            EventType.REFUND_COMPLETED,
            "payment",
            pay.id,
            {"amount": str(amount), "user_id": pay.user_id, "order_number": order.order_number if order else ""},
        )
        return RefundOut(id=refund.id, payment_id=pay.id, amount=amount, status=refund.status, reason=reason)
