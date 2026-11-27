"""Event consumers. Each runs on its own transaction with the SYSTEM principal, through the Plugin Manager."""

from __future__ import annotations

from app.agents.base import AgentRunContext, AgentTask
from app.core.logging import get_logger
from app.core.state import AppState
from app.events.bus import EventBus
from app.events.schemas import EventEnvelope, EventType
from app.plugins.base import PluginContext
from app.security.permissions import SYSTEM_PRINCIPAL
from app.services.container import container_factory

log = get_logger("consumers")

TEMPLATE_FOR = {
    EventType.PAYMENT_SUCCESSFUL: "order_confirmation",
    EventType.PAYMENT_FAILED: "payment_failed",
    EventType.SHIPMENT_CREATED: "shipment_update",
    EventType.ORDER_DELIVERED: "shipment_update",
    EventType.RETURN_REQUESTED: "return_update",
    EventType.REFUND_COMPLETED: "refund_update",
}


def register_consumers(bus: EventBus, state: AppState) -> None:
    factory = container_factory(state)

    async def fulfilment(event: EventEnvelope) -> None:
        """PaymentSuccessful → ensure a shipment exists (idempotent; the chat flow may already have created it)."""
        async with factory() as services:
            ctx = PluginContext(
                principal=SYSTEM_PRINCIPAL, services=services, agent="event:fulfilment", extras={"plugin_manager": state.plugins}
            )
            res = await state.plugins.execute("shipping", "create_shipment", {"order_id": event.payload["order_id"]}, ctx)
            if not res.success and res.error_code not in ("conflict",):
                raise RuntimeError(res.error or "shipment creation failed")

    async def notifier(event: EventEnvelope) -> None:
        """Lifecycle events → Notification Agent (email + WhatsApp), de-duplicated per order/template."""
        user_id = event.payload.get("user_id")
        if not user_id:
            return
        template = TEMPLATE_FOR[event.event_type]
        context = {k: v for k, v in event.payload.items() if isinstance(v, str | int | float)}
        context.setdefault("status", {"ORDER_DELIVERED": "delivered", "SHIPMENT_CREATED": "shipped"}.get(event.event_type.name, "updated"))
        context.setdefault("message", "")
        context.setdefault("name", "there")
        async with factory() as services:
            ctx = AgentRunContext(
                principal=SYSTEM_PRINCIPAL,
                services=services,
                plugins=state.plugins,
                metrics=state.metrics,
                memory={"last_order_number": event.payload.get("order_number", ""), "last_order_total": event.payload.get("total", "")},
                llm=state.llm,
            )
            agent = state.agents.specialised["notification"]
            res = await agent.run(
                AgentTask(intent=event.event_type.value, params={"template": template, "context": context, "user_id": user_id}), ctx
            )
            if not res.success:
                log.warning("notification_consumer_failed", extra={"event": event.event_id, "error": res.error})

    bus.subscribe("fulfilment", [EventType.PAYMENT_SUCCESSFUL], fulfilment)
    bus.subscribe("notifier", list(TEMPLATE_FOR), notifier)

    s = state.settings
    if s.n8n_webhook_url:
        from app.integrations.n8n import N8nForwarder

        state.n8n = N8nForwarder(s.n8n_webhook_url, s.n8n_webhook_token, s.n8n_signing_secret)
        bus.subscribe("n8n", list(EventType), state.n8n)
