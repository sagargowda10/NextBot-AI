"""Builds the application-managed plugin set (exactly 12) and maps settings → plugin config.

Discovery: built-ins are listed here explicitly; additional trusted plugins can be shipped as
packages that declare the `nextbot.plugins` entry-point group. Entry-point discovery is opt-in
(`NEXTBOT_ENABLE_ENTRYPOINT_PLUGINS=1`) — NextBot never downloads or runs arbitrary code.
"""

from __future__ import annotations

import os
from importlib.metadata import entry_points
from typing import Any

from app.plugins.base import BasePlugin
from app.plugins.builtin.analytics import AnalyticsPlugin
from app.plugins.builtin.customer_support import CustomerSupportPlugin
from app.plugins.builtin.email import EmailPlugin
from app.plugins.builtin.fraud_detection import FraudDetectionPlugin
from app.plugins.builtin.inventory import InventoryPlugin
from app.plugins.builtin.mcp_integration import McpIntegrationPlugin
from app.plugins.builtin.order_management import OrderManagementPlugin
from app.plugins.builtin.payment import PaymentPlugin
from app.plugins.builtin.product_search import ProductSearchPlugin
from app.plugins.builtin.recommendation import RecommendationPlugin
from app.plugins.builtin.shipping import ShippingPlugin
from app.plugins.builtin.whatsapp import WhatsAppPlugin

BUILTIN_PLUGINS: tuple[type[BasePlugin], ...] = (
    ProductSearchPlugin,
    RecommendationPlugin,
    InventoryPlugin,
    PaymentPlugin,
    OrderManagementPlugin,
    ShippingPlugin,
    CustomerSupportPlugin,
    WhatsAppPlugin,
    EmailPlugin,
    AnalyticsPlugin,
    FraudDetectionPlugin,
    McpIntegrationPlugin,
)


def builtin_plugins() -> list[BasePlugin]:
    return [cls() for cls in BUILTIN_PLUGINS]


def entrypoint_plugins() -> list[BasePlugin]:
    if os.getenv("NEXTBOT_ENABLE_ENTRYPOINT_PLUGINS") != "1":
        return []
    found: list[BasePlugin] = []
    for ep in entry_points(group="nextbot.plugins"):
        cls = ep.load()
        if isinstance(cls, type) and issubclass(cls, BasePlugin):
            found.append(cls())
    return found


def configs_from_settings(s: Any) -> dict[str, dict[str, Any]]:
    """Secrets flow env → settings → plugin config, server-side only (masked in every API response)."""
    return {
        "inventory": {"low_stock_threshold": s.low_stock_threshold},
        "payment": {
            "provider": s.payment_provider,
            "razorpay_key_id": s.razorpay_key_id,
            "razorpay_key_secret": s.razorpay_key_secret,
            "stripe_secret_key": s.stripe_secret_key,
        },
        "shipping": {"provider": s.shipping_provider, "shiprocket_email": s.shiprocket_email, "shiprocket_password": s.shiprocket_password},
        "whatsapp": {"enabled": s.whatsapp_enabled, "token": s.whatsapp_token, "phone_number_id": s.whatsapp_phone_number_id},
        "email": {
            "enabled": s.email_enabled,
            "smtp_host": s.smtp_host,
            "smtp_port": s.smtp_port,
            "smtp_user": s.smtp_user,
            "smtp_password": s.smtp_password,
            "sender": s.smtp_from,
        },
        "fraud_detection": {"review_threshold": s.fraud_review_score},
    }
