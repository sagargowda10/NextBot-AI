"""Order workflow view: rebuilds, from real database records, how one order travelled through NextBot.

Every node maps to an agent / plugin / event step and gets its status from the rows that step writes, so the
admin "Workflows" canvas is an execution trace (like n8n's execution view), not a static diagram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalStatus, PaymentStatus, RefundStatus, ReturnStatus, ShipmentStatus
from app.core.exceptions import NotFoundError
from app.models.commerce import Order, Payment, Refund, ReturnRequest, Shipment
from app.models.platform import ApprovalRequest, Notification, OutboxEvent

DONE, FAILED, REVIEW, PENDING, SKIPPED = "done", "failed", "review", "pending", "skipped"

# (id, label, agent/plugin, kind) - kind drives the icon on the canvas
NODES: list[tuple[str, str, str, str]] = [
    ("checkout", "Checkout", "Order Management Agent", "trigger"),
    ("fraud", "Fraud check", "Fraud Detection Agent", "agent"),
    ("inventory", "Reserve stock", "Inventory Agent", "agent"),
    ("payment", "Payment", "Payment Agent", "agent"),
    ("events", "Event bus", "Outbox -> Kafka", "bus"),
    ("shipping", "Create shipment", "Logistics Agent", "agent"),
    ("courier", "Courier updates", "Shipping plugin", "plugin"),
    ("email", "Email", "Notification Agent", "notify"),
    ("whatsapp", "WhatsApp", "Notification Agent", "notify"),
    ("n8n", "n8n automation", "n8n webhook", "n8n"),
    ("return", "Return request", "Return & Refund Agent", "agent"),
    ("approval", "Human approval", "Admin", "human"),
    ("refund", "Refund", "Payment Agent", "agent"),
]
EDGES: list[tuple[str, str]] = [
    ("checkout", "fraud"),
    ("fraud", "inventory"),
    ("inventory", "payment"),
    ("payment", "events"),
    ("events", "shipping"),
    ("shipping", "courier"),
    ("events", "email"),
    ("events", "whatsapp"),
    ("events", "n8n"),
    ("courier", "return"),
    ("return", "approval"),
    ("approval", "refund"),
]


@dataclass
class Node:
    id: str
    label: str
    actor: str
    kind: str
    status: str = PENDING
    at: str | None = None
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class WorkflowService:
    def __init__(self, session: AsyncSession, n8n: Any | None = None, n8n_editor_url: str | None = None) -> None:
        self.session, self.n8n, self.n8n_editor_url = session, n8n, n8n_editor_url

    async def for_order(self, order_id: int) -> dict[str, Any]:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("Order not found")
        payments = list((await self.session.scalars(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id))).all())
        pay_ids = [str(p.id) for p in payments]
        events = list(
            (
                await self.session.scalars(
                    select(OutboxEvent)
                    .where(
                        or_(
                            (OutboxEvent.aggregate_type == "order") & (OutboxEvent.aggregate_id == str(order.id)),
                            (OutboxEvent.aggregate_type == "payment") & (OutboxEvent.aggregate_id.in_(pay_ids or ["-"])),
                        )
                    )
                    .order_by(OutboxEvent.id)
                )
            ).all()
        )
        shipment = await self.session.scalar(select(Shipment).where(Shipment.order_id == order.id))
        ret = await self.session.scalar(select(ReturnRequest).where(ReturnRequest.order_id == order.id))
        refunds = (
            list((await self.session.scalars(select(Refund).where(Refund.payment_id.in_([p.id for p in payments])))).all())
            if payments
            else []
        )
        approvals = await self._approvals(order, ret)
        notes = [
            n
            for n in (await self.session.scalars(select(Notification).where(Notification.user_id == order.user_id))).all()
            if str((n.meta or {}).get("dedupe_key") or "").endswith(f":{order.order_number}")
        ]

        nodes = {nid: Node(nid, label, actor, kind) for nid, label, actor, kind in NODES}
        by_type: dict[str, list[OutboxEvent]] = {}
        for e in events:
            by_type.setdefault(e.event_type, []).append(e)

        # Checkout
        n = nodes["checkout"]
        n.status, n.at = DONE, _iso(order.created_at)
        n.summary = f"{len(order.items)} item(s) - Rs {order.total}"
        n.details = {
            "order_number": order.order_number,
            "status": order.status,
            "items": [f"{i.quantity} x {i.product_name}" for i in order.items],
            "total": str(order.total),
            "ship_to": order.shipping_pincode,
        }

        # Fraud
        n = nodes["fraud"]
        fraud_appr = next((a for a in approvals if a.action == "SUSPICIOUS_TRANSACTION"), None)
        if order.risk_score is not None:
            n.status = REVIEW if fraud_appr and fraud_appr.status == ApprovalStatus.PENDING else DONE
            n.at = _iso(order.created_at)
            n.summary = f"Risk score {order.risk_score}" + (" - manual review" if fraud_appr else " - auto-approved")
            n.details = {"risk_score": order.risk_score, "review": fraud_appr.status if fraud_appr else "not needed"}
        else:
            n.status, n.summary = SKIPPED, "Order placed without a risk assessment"

        # Inventory
        n = nodes["inventory"]
        if by_type.get("InventoryReserved"):
            e = by_type["InventoryReserved"][0]
            n.status, n.at, n.summary = DONE, _iso(e.created_at), "Stock reserved"
            if by_type.get("InventoryReleased"):
                n.summary = "Reserved, then released"
            n.details = {"items": (e.payload or {}).get("payload", {}).get("items", [])}

        # Payment
        n = nodes["payment"]
        if payments:
            last = payments[-1]
            ok = any(p.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED) for p in payments)
            n.status = DONE if ok else FAILED if last.status == PaymentStatus.FAILED else PENDING
            n.at = _iso(last.updated_at)
            n.summary = f"{last.method} via {last.provider}" + (" (simulated)" if last.is_simulated else "") + f" - {last.status}"
            n.details = {
                "attempts": [
                    {"id": p.id, "status": p.status, "amount": str(p.amount), "reason": p.failure_reason, "at": _iso(p.created_at)}
                    for p in payments
                ],
                "failed_attempts": order.payment_failures,
            }

        # Event bus
        n = nodes["events"]
        if events:
            published = sum(1 for e in events if e.published_at)
            n.status = DONE if published == len(events) else PENDING
            n.at = _iso(events[-1].published_at or events[-1].created_at)
            n.summary = f"{published}/{len(events)} events published"
            n.details = {"events": [f"{e.event_type}{'' if e.published_at else ' (queued)'}" for e in events]}

        # Shipment + courier
        if shipment:
            n = nodes["shipping"]
            n.status, n.at = DONE, _iso(shipment.created_at)
            n.summary = f"{shipment.carrier} {shipment.tracking_number}"
            n.details = {"estimated_delivery": str(shipment.estimated_delivery) if shipment.estimated_delivery else None}
            c = nodes["courier"]
            hist = list(shipment.events or [])
            c.status = DONE if shipment.status == ShipmentStatus.DELIVERED else PENDING
            c.at = hist[-1].get("at") if hist else None
            c.summary = shipment.status.replace("_", " ").title() + (" (simulated)" if shipment.is_simulated else "")
            c.details = {"history": [f"{h.get('status')} - {h.get('location') or ''}" for h in hist]}

        # Notifications
        for channel, nid in (("EMAIL", "email"), ("WHATSAPP", "whatsapp")):
            rows = [x for x in notes if x.channel == channel]
            if rows:
                n = nodes[nid]
                bad = [x for x in rows if x.status in ("FAILED",)]
                n.status = FAILED if bad and len(bad) == len(rows) else DONE
                n.at = _iso(rows[-1].created_at)
                n.summary = f"{len(rows)} message(s) - {rows[-1].status}"
                n.details = {"messages": [f"{x.template}: {x.status}" for x in rows]}

        # n8n
        n = nodes["n8n"]
        if self.n8n is None:
            n.status, n.summary = SKIPPED, "Not configured (set N8N_WEBHOOK_URL)"
        else:
            deliveries = self.n8n.for_events({e.event_id for e in events})
            if deliveries:
                delivered = [d for d in deliveries if d.ok]
                n.status = DONE if len(delivered) == len(deliveries) else FAILED
                n.at = deliveries[0].at
                n.summary = f"{len(delivered)}/{len(deliveries)} events delivered"
                n.details = {"deliveries": [f"{d.event_type}: {'ok' if d.ok else d.error}" for d in deliveries]}
            else:
                n.summary = "No deliveries since the backend started"

        # Return -> approval -> refund
        if ret:
            n = nodes["return"]
            n.status = FAILED if ret.status == ReturnStatus.REJECTED else DONE
            n.at, n.summary = _iso(ret.created_at), f"{ret.status.replace('_', ' ').title()} - Rs {ret.refund_amount}"
            n.details = {"reason": ret.reason, "status": ret.status}
            appr = next((a for a in approvals if a.id == ret.approval_request_id), None)
            a = nodes["approval"]
            if appr:
                a.status = {ApprovalStatus.PENDING: REVIEW, ApprovalStatus.REJECTED: FAILED, ApprovalStatus.FAILED: FAILED}.get(
                    ApprovalStatus(appr.status), DONE
                )
                a.at = _iso(appr.reviewed_at or appr.created_at)
                a.summary = f"{appr.status.title()}" + (f" - {appr.review_note}" if appr.review_note else "")
                a.details = {"action": appr.action, "summary": appr.summary}
            else:
                a.status, a.summary = SKIPPED, "Below the approval threshold"
            r = nodes["refund"]
            mine = [x for x in refunds if x.return_request_id == ret.id] or refunds
            if mine:
                last_r = mine[-1]
                r.status = {RefundStatus.COMPLETED: DONE, RefundStatus.REJECTED: FAILED}.get(RefundStatus(last_r.status), PENDING)
                r.at, r.summary = _iso(last_r.updated_at), f"Rs {last_r.amount} - {last_r.status}"
        else:
            for nid in ("return", "approval", "refund"):
                nodes[nid].status = SKIPPED
            nodes["return"].summary = "No return requested"

        timeline = self._timeline(order, payments, events, shipment, notes, ret, approvals)
        return {
            "order": {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "total": str(order.total),
                "user_id": order.user_id,
                "created_at": _iso(order.created_at),
            },
            "nodes": [n.__dict__ for n in nodes.values()],
            "edges": [{"source": s, "target": t} for s, t in EDGES],
            "timeline": timeline,
            "n8n": self.n8n_status(),
        }

    def n8n_status(self) -> dict[str, Any]:
        base = {"configured": self.n8n is not None, "editor_url": self.n8n_editor_url}
        return {**base, **(self.n8n.status() if self.n8n else {"sent": 0, "failed": 0, "last_error": None})}

    async def _approvals(self, order: Order, ret: ReturnRequest | None) -> list[ApprovalRequest]:
        ids = [ret.approval_request_id] if ret and ret.approval_request_id else []
        rows = (
            await self.session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.requested_for_user_id == order.user_id)
                .order_by(ApprovalRequest.id.desc())
                .limit(200)
            )
        ).all()
        return [a for a in rows if a.id in ids or (a.payload or {}).get("order_id") == order.id]

    @staticmethod
    def _timeline(
        order: Order,
        payments: list[Payment],
        events: list[OutboxEvent],
        shipment: Shipment | None,
        notes: list[Notification],
        ret: ReturnRequest | None,
        approvals: list[ApprovalRequest],
    ) -> list[dict[str, Any]]:
        t: list[dict[str, Any]] = [
            {"at": _iso(order.created_at), "title": "Order created", "detail": order.order_number, "node": "checkout"}
        ]
        t += [
            {"at": _iso(p.created_at), "title": f"Payment {p.status.lower()}", "detail": p.failure_reason or p.method, "node": "payment"}
            for p in payments
        ]
        t += [
            {
                "at": _iso(e.published_at or e.created_at),
                "title": e.event_type,
                "detail": "published to the event bus" if e.published_at else "waiting in outbox",
                "node": "events",
            }
            for e in events
        ]
        if shipment:
            t += [
                {"at": h.get("at"), "title": f"Courier: {h.get('status')}", "detail": h.get("note") or h.get("location"), "node": "courier"}
                for h in shipment.events or []
            ]
        t += [
            {"at": _iso(n.created_at), "title": f"{n.channel.title()} {n.template}", "detail": n.status, "node": n.channel.lower()}
            for n in notes
        ]
        if ret:
            t.append({"at": _iso(ret.created_at), "title": "Return requested", "detail": ret.reason, "node": "return"})
        t += [
            {"at": _iso(a.reviewed_at), "title": f"Approval {a.status.lower()}", "detail": a.summary, "node": "approval"}
            for a in approvals
            if a.reviewed_at
        ]
        return sorted((x for x in t if x["at"]), key=lambda x: str(x["at"]))
