"""Shared enumerations. Pure Python — safe to import from any layer."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    INVENTORY_MANAGER = "INVENTORY_MANAGER"
    SYSTEM = "SYSTEM"  # internal principal used by event consumers / MCP service account


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURNED = "RETURNED"


class PaymentStatus(StrEnum):
    INITIATED = "INITIATED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class RefundStatus(StrEnum):
    PENDING = "PENDING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class ShipmentStatus(StrEnum):
    CREATED = "CREATED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"


class ReturnStatus(StrEnum):
    REQUESTED = "REQUESTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RECEIVED = "RECEIVED"
    REFUNDED = "REFUNDED"


class PluginStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    INITIALIZING = "INITIALIZING"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ApprovalAction(StrEnum):
    HIGH_VALUE_REFUND = "HIGH_VALUE_REFUND"
    LARGE_ORDER_CANCELLATION = "LARGE_ORDER_CANCELLATION"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"
    SUSPICIOUS_TRANSACTION = "SUSPICIOUS_TRANSACTION"
    ACCOUNT_CHANGE = "ACCOUNT_CHANGE"


class Channel(StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    VOICE = "VOICE"


class NotificationStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    SIMULATED = "SIMULATED"  # mock adapter: nothing left the machine
    FAILED = "FAILED"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
