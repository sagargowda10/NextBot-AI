from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrderStatus, ShipmentStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.state import AppState
from app.domain.delivery import estimate_delivery
from app.domain.order_state import assert_transition
from app.events.outbox import add_event
from app.events.schemas import EventType
from app.models.commerce import Order, Shipment
from app.models.user import Address
from app.schemas.commerce import DeliveryEstimateOut, ShipmentOut
from app.security.permissions import Principal
from app.services.mappers import shipment_out

FLOW = [ShipmentStatus.CREATED, ShipmentStatus.PACKED, ShipmentStatus.SHIPPED, ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELIVERED]
NOTES = {
    ShipmentStatus.PACKED: "Packed at fulfilment centre",
    ShipmentStatus.SHIPPED: "Handed to courier",
    ShipmentStatus.OUT_FOR_DELIVERY: "Out for delivery",
    ShipmentStatus.DELIVERED: "Delivered",
}


def _event(status: str, note: str, location: str | None = None) -> dict[str, str | None]:
    return {"status": status, "at": datetime.now(UTC).isoformat(), "note": note, "location": location}


class ShipmentService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def create_for_order(self, order_id: int) -> ShipmentOut:
        existing = await self.session.scalar(select(Shipment).where(Shipment.order_id == order_id))
        if existing is not None:  # idempotent: agent path and event consumer may both ask
            return shipment_out(existing)
        order = await self.session.get(Order, order_id, with_for_update=True)
        if order is None:
            raise NotFoundError("Order not found")
        if order.status != OrderStatus.CONFIRMED:
            raise ConflictError(f"Order is {order.status}; shipments are created after payment")
        booking = await self.state.courier.book(
            order_number=order.order_number, pincode=order.shipping_pincode or "", weight_kg=1.0, address=order.shipping_address or {}
        )
        est = estimate_delivery(order.shipping_pincode or "")
        shipment = Shipment(
            order_id=order.id,
            carrier=booking.carrier,
            tracking_number=booking.tracking_number,
            status=ShipmentStatus.CREATED,
            estimated_delivery=est.latest if est.serviceable else None,
            events=[_event(ShipmentStatus.CREATED, "Shipment booked", "Bengaluru FC")],
            is_simulated=booking.simulated,
        )
        self.session.add(shipment)
        order.status = assert_transition(order.status, OrderStatus.PROCESSING)
        await self.session.flush()
        add_event(
            self.session,
            EventType.SHIPMENT_CREATED,
            "order",
            order.id,
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "user_id": order.user_id,
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
            },
        )
        return shipment_out(shipment)

    async def track(self, principal: Principal, order_id: int) -> ShipmentOut | None:
        order = await self.session.get(Order, order_id)
        if order is None or not principal.can_access_user_resource(order.user_id, "shipment:read_all"):
            raise NotFoundError("Order not found")
        s = await self.session.scalar(select(Shipment).where(Shipment.order_id == order_id))
        return shipment_out(s) if s else None

    async def get(self, principal: Principal, shipment_id: int) -> ShipmentOut:
        s = await self.session.get(Shipment, shipment_id)
        if s is None:
            raise NotFoundError("Shipment not found")
        result = await self.track(principal, s.order_id)
        assert result is not None
        return result

    async def estimate(self, pincode: str) -> DeliveryEstimateOut:
        return DeliveryEstimateOut(**estimate_delivery(pincode).__dict__)

    async def advance(self, shipment_id: int, status: str, location: str | None = None) -> ShipmentOut:
        s = await self.session.get(Shipment, shipment_id, with_for_update=True)
        if s is None:
            raise NotFoundError("Shipment not found")
        target = ShipmentStatus(status)
        if FLOW.index(target) <= FLOW.index(ShipmentStatus(s.status)):
            raise ConflictError(f"Shipment is already {s.status}")
        order = await self.session.get(Order, s.order_id)
        assert order is not None
        for step in FLOW[FLOW.index(ShipmentStatus(s.status)) + 1 : FLOW.index(target) + 1]:  # walk intermediate steps
            order.status = assert_transition(order.status, OrderStatus(step.value))
            s.events = [*(s.events or []), _event(step, NOTES[step], location)]
        s.status = target
        if target == ShipmentStatus.DELIVERED:
            order.delivered_at = datetime.now(UTC)
            add_event(
                self.session,
                EventType.ORDER_DELIVERED,
                "order",
                order.id,
                {"order_id": order.id, "order_number": order.order_number, "user_id": order.user_id},
            )
        await self.session.flush()
        return shipment_out(s)

    async def default_pincode(self, user_id: int) -> str | None:
        return await self.session.scalar(
            select(Address.pincode).where(Address.user_id == user_id).order_by(Address.is_default.desc(), Address.id).limit(1)
        )
