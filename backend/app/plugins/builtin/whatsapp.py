"""Plugin 8 — WhatsApp Integration: Business Cloud API adapter, inbound webhooks, order updates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import ValidationFailed
from app.integrations.messaging import (
    MockWhatsAppAdapter,
    WhatsAppAdapter,
    WhatsAppCloudAdapter,
    parse_whatsapp_webhook,
    render,
)
from app.plugins.base import BasePlugin, HealthStatus, PluginContext, action


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    user_id: int | None = Field(None, gt=0)  # staff only; customers always message themselves


class TemplateIn(BaseModel):
    template: str = Field(pattern=r"^[a-z_]{3,40}$")
    context: dict[str, Any] = {}
    user_id: int | None = Field(None, gt=0)
    dedupe_key: str | None = Field(None, max_length=120)


class WebhookIn(BaseModel):
    payload: dict[str, Any]


class WhatsAppPlugin(BasePlugin):
    plugin_id = "whatsapp"
    name = "WhatsApp Integration"
    version = "1.0.0"
    description = "WhatsApp Business Cloud API messaging and inbound webhooks. Runs in mock mode until credentials are set."
    default_config = {"enabled": False, "token": None, "phone_number_id": None}
    secret_keys = frozenset({"token"})

    def __init__(self) -> None:
        super().__init__()
        self.adapter: WhatsAppAdapter = MockWhatsAppAdapter()

    @property
    def requires_credentials(self) -> bool:  # type: ignore[override]
        return True

    @property
    def mode(self) -> str:
        return "live" if isinstance(self.adapter, WhatsAppCloudAdapter) else "mock"

    async def initialize(self, config: dict[str, Any] | None = None) -> None:
        await super().initialize(config)
        if self.config.get("enabled"):
            self.adapter = WhatsAppCloudAdapter(self.config.get("token"), self.config.get("phone_number_id"))
        else:
            self.adapter = MockWhatsAppAdapter()

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"adapter={self.adapter.name}")

    async def _deliver(
        self, ctx: PluginContext, user_id: int | None, template: str, subject: str | None, body: str, dedupe_key: str | None = None
    ) -> dict:
        target = user_id if (user_id and ctx.principal.has("notify:any")) else ctx.principal.user_id
        if target is None:
            raise ValidationFailed("No recipient")
        phone = await ctx.services.notifications.recipient_for(target, "WHATSAPP")
        if not phone:
            raise ValidationFailed("Customer has no WhatsApp number on file")
        if dedupe_key and await ctx.services.notifications.already_sent(target, "WHATSAPP", dedupe_key):
            return {"notification_id": None, "status": "DUPLICATE_SKIPPED", "simulated": self.mode == "mock"}
        res = await self.adapter.send(phone, body)
        note = await ctx.services.notifications.record(
            user_id=target,
            channel="WHATSAPP",
            template=template,
            recipient=phone,
            subject=subject,
            body=body,
            status=res.status.value,
            meta={"provider": res.provider, "detail": res.detail, "dedupe_key": dedupe_key},
        )
        return {"notification_id": note.id, "status": res.status.value, "provider": res.provider, "simulated": self.mode == "mock"}

    @action("send_message", SendIn, "notify:self", "Send a WhatsApp text")
    async def send_message(self, p: SendIn, ctx: PluginContext) -> dict:
        return await self._deliver(ctx, p.user_id, "generic", None, p.text)

    @action("send_template", TemplateIn, "notify:self", "Send an order/payment/shipment update")
    async def send_template(self, p: TemplateIn, ctx: PluginContext) -> dict:
        subject, body = render(p.template, p.context)
        return await self._deliver(ctx, p.user_id, p.template, subject, f"*{subject}*\n{body}", p.dedupe_key)

    @action("handle_webhook", WebhookIn, "notify:any", "Parse inbound WhatsApp messages (webhook)")
    async def handle_webhook(self, p: WebhookIn, ctx: PluginContext) -> dict:
        return {"messages": parse_whatsapp_webhook(p.payload)}
