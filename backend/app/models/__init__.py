"""Import every model so `Base.metadata` is complete (Alembic, create_all)."""

from app.models.ai import AgentExecution, AgentToolExecution, Conversation, ConversationMessage, KnowledgeChunk, KnowledgeDocument
from app.models.catalog import Brand, Coupon, Product, ProductCategory, ProductImage, ProductVariant, Review
from app.models.commerce import CartItem, Order, OrderItem, Payment, Refund, ReturnRequest, Shipment, ShoppingCart
from app.models.inventory import Inventory, Warehouse
from app.models.platform import (
    ApprovalRequest,
    AuditLog,
    Notification,
    OutboxEvent,
    Plugin,
    PluginConfiguration,
    PluginExecution,
    ProcessedEvent,
)
from app.models.user import Address, CustomerProfile, Permission, Role, User

__all__ = [
    "Address",
    "AgentExecution",
    "AgentToolExecution",
    "ApprovalRequest",
    "AuditLog",
    "Brand",
    "CartItem",
    "Conversation",
    "ConversationMessage",
    "Coupon",
    "CustomerProfile",
    "Inventory",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "Notification",
    "Order",
    "OrderItem",
    "OutboxEvent",
    "Payment",
    "Permission",
    "Plugin",
    "PluginConfiguration",
    "PluginExecution",
    "ProcessedEvent",
    "Product",
    "ProductCategory",
    "ProductImage",
    "ProductVariant",
    "Refund",
    "ReturnRequest",
    "Review",
    "Role",
    "Shipment",
    "ShoppingCart",
    "User",
    "Warehouse",
]
