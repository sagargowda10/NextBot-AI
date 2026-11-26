"""Human-in-the-loop approvals: agents propose, administrators decide, the system executes and audits."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalAction, ApprovalStatus, OrderStatus, ReturnStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.state import AppState
from app.domain.order_state import assert_transition
from app.models.commerce import Order, Payment, ReturnRequest
from app.models.platform import ApprovalRequest
from app.schemas.platform import ApprovalOut
from app.security.permissions import Principal
from app.services.audit_service import audit

log = get_logger("approvals")


def approval_out(a: ApprovalRequest) -> ApprovalOut:
    return ApprovalOut(
        id=a.id,
        action=a.action,
        status=a.status,
        summary=a.summary,
        payload=a.payload or {},
        requested_by_agent=a.requested_by_agent,
        requested_for_user_id=a.requested_for_user_id,
        reviewer_id=a.reviewer_id,
        review_note=a.review_note,
        result=a.result,
        created_at=a.created_at,
        reviewed_at=a.reviewed_at,
    )


class ApprovalService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def create(self, *, action: str, summary: str, payload: dict[str, Any], agent: str | None, user_id: int | None) -> int:
        a = ApprovalRequest(
            action=ApprovalAction(action),
            summary=summary[:300],
            payload=payload,
            requested_by_agent=agent,
            requested_for_user_id=user_id,
            status=ApprovalStatus.PENDING,
        )
        self.session.add(a)
        await self.session.flush()
        await audit(self.session, None, "approval.requested", "approval", a.id, {"action": action, "agent": agent})
        return a.id

    async def list(self, status: str | None = None, limit: int = 50) -> list[ApprovalOut]:
        stmt = select(ApprovalRequest).order_by(ApprovalRequest.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        return [approval_out(a) for a in (await self.session.scalars(stmt)).all()]

    async def decide(self, reviewer: Principal, approval_id: int, approve: bool, note: str | None) -> ApprovalOut:
        a = await self.session.get(ApprovalRequest, approval_id, with_for_update=True)
        if a is None:
            raise NotFoundError("Approval request not found")
        if a.status != ApprovalStatus.PENDING:
            raise ConflictError(f"Request already {a.status}")
        a.reviewer_id, a.review_note, a.reviewed_at = reviewer.user_id, note, datetime.now(UTC)
        try:
            async with self.session.begin_nested():
                result = await (self._execute(a, reviewer) if approve else self._reject(a, reviewer))
            a.status = ApprovalStatus.EXECUTED if approve else ApprovalStatus.REJECTED
            a.result = result
        except Exception as exc:  # approved but execution failed: keep the record, surface the error
            log.exception("approval_execution_failed", extra={"approval": a.id})
            a.status, a.result = ApprovalStatus.FAILED, {"error": str(exc)[:400]}
        await audit(
            self.session,
            reviewer,
            f"approval.{'approved' if approve else 'rejected'}",
            "approval",
            a.id,
            {"action": a.action, "status": a.status, "note": note},
        )
        await self.session.flush()
        return approval_out(a)

    async def _execute(self, a: ApprovalRequest, reviewer: Principal) -> dict[str, Any]:
        from app.services.inventory_service import InventoryService
        from app.services.order_service import OrderService
        from app.services.payment_service import PaymentService

        p = a.payload or {}
        match ApprovalAction(a.action):
            case ApprovalAction.HIGH_VALUE_REFUND if "return_id" in p:
                r = await self.session.get(ReturnRequest, p["return_id"])
                if r is None:
                    raise NotFoundError("Return not found")
                r.status = ReturnStatus.APPROVED
                return {"return_id": r.id, "status": r.status, "next": "refund issued when the item is received"}
            case ApprovalAction.HIGH_VALUE_REFUND:
                pay = await self.session.get(Payment, p["payment_id"])
                if pay is None:
                    raise NotFoundError("Payment not found")
                refund = await PaymentService(self.session, self.state).refund_internal(
                    pay, Decimal(p["amount"]), p.get("reason", "Approved refund")
                )
                return {"refund_id": refund.id, "amount": str(refund.amount)}
            case ApprovalAction.LARGE_ORDER_CANCELLATION:
                order = await self.session.get(Order, p["order_id"])
                if order is None:
                    raise NotFoundError("Order not found")
                await OrderService(self.session, self.state).perform_cancel(order, p.get("reason", "Approved cancellation"), reviewer)
                return {"order_id": order.id, "status": order.status}
            case ApprovalAction.INVENTORY_ADJUSTMENT:
                res = await InventoryService(self.session, self.state).apply_adjustment(
                    reviewer, p["inventory_id"], int(p["delta"]), p["reason"]
                )
                return res.model_dump(mode="json")
            case ApprovalAction.SUSPICIOUS_TRANSACTION:
                order = await self.session.get(Order, p["order_id"])
                if order is None:
                    raise NotFoundError("Order not found")
                order.risk_score = 0  # cleared by a human; payment may proceed
                return {"order_id": order.id, "cleared": True}
        return {"note": "recorded"}

    async def _reject(self, a: ApprovalRequest, reviewer: Principal) -> dict[str, Any]:
        p = a.payload or {}
        if a.action == ApprovalAction.HIGH_VALUE_REFUND and "return_id" in p:
            r = await self.session.get(ReturnRequest, p["return_id"])
            if r is not None:
                r.status = ReturnStatus.REJECTED
                r.order.status = assert_transition(r.order.status, OrderStatus.DELIVERED)
        if a.action == ApprovalAction.SUSPICIOUS_TRANSACTION:
            order = await self.session.get(Order, p["order_id"])
            if order is not None and order.status == OrderStatus.PAYMENT_PENDING:
                from app.services.order_service import OrderService

                await OrderService(self.session, self.state).perform_cancel(order, "Rejected after fraud review", reviewer)
        return {"rejected": True}
