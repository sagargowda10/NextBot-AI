"""Event envelope and catalogue of domain events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    ORDER_CREATED = "OrderCreated"
    PAYMENT_INITIATED = "PaymentInitiated"
    PAYMENT_SUCCESSFUL = "PaymentSuccessful"
    PAYMENT_FAILED = "PaymentFailed"
    INVENTORY_RESERVED = "InventoryReserved"
    INVENTORY_RELEASED = "InventoryReleased"
    SHIPMENT_CREATED = "ShipmentCreated"
    ORDER_DELIVERED = "OrderDelivered"
    RETURN_REQUESTED = "ReturnRequested"
    REFUND_INITIATED = "RefundInitiated"
    REFUND_COMPLETED = "RefundCompleted"
    NOTIFICATION_REQUESTED = "NotificationRequested"


TOPICS: dict[EventType, str] = {
    EventType.ORDER_CREATED: "orders",
    EventType.ORDER_DELIVERED: "orders",
    EventType.PAYMENT_INITIATED: "payments",
    EventType.PAYMENT_SUCCESSFUL: "payments",
    EventType.PAYMENT_FAILED: "payments",
    EventType.INVENTORY_RESERVED: "inventory",
    EventType.INVENTORY_RELEASED: "inventory",
    EventType.SHIPMENT_CREATED: "shipments",
    EventType.RETURN_REQUESTED: "returns",
    EventType.REFUND_INITIATED: "returns",
    EventType.REFUND_COMPLETED: "returns",
    EventType.NOTIFICATION_REQUESTED: "notifications",
}


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: EventType
    aggregate_type: str
    aggregate_id: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)
    attempt: int = 0

    @property
    def topic(self) -> str:
        return TOPICS[self.event_type]

    @property
    def key(self) -> str:  # same aggregate → same partition → ordered
        return f"{self.aggregate_type}:{self.aggregate_id}"
