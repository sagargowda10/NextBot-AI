"""Plugin 9 — Email Notification: templated order/payment/shipping/return/refund emails over SMTP."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import ValidationFailed
from app.integrations.messaging import TEMPLATES, EmailAdapter, MockEmailAdapter, SmtpEmailAdapter, render
from app.plugins.base import BasePlugin, HealthStatus, NoInput, PluginContext, action


class SendIn(BaseModel):
    template: str = Field(pattern=r"^[a-z_]{3,40}$")
    context: dict[str, Any] = {}
    user_id: int | None = Field(None, gt=0)  # staff only
    dedupe_key: str | None = Field(None, max_length=120)  # same key → sent at most once per channel


class EmailPlugin(BasePlugin):
    plugin_id = "email"
    name = "Email Notification"
    version = "1.1.0"
    description = "Order confirmation, payment, shipping, return and refund emails. Configurable SMTP; mock mode records without sending."
    default_config = {
        "enabled": False,
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_user": None,
        "smtp_password": None,
        "sender": "NextBot AI <no-reply@nextbot.local>",
    }
    secret_keys = frozenset({"smtp_password"})

    def __init__(self) -> None:
        super().__init__()
        self.adapter: EmailAdapter = MockEmailAdapter()

    @property
    def mode(self) -> str:
        return "live" if isinstance(self.adapter, SmtpEmailAdapter) else "mock"

    def validate_configuration(self, config: dict) -> list[str]:
        if config.get("enabled") and not config.get("smtp_host"):
            return ["SMTP_HOST is required when EMAIL_ENABLED=true"]
        return []

    async def initialize(self, config: dict[str, Any] | None = None) -> None:
        await super().initialize(config)
        c = self.config
        self.adapter = (
            SmtpEmailAdapter(c["smtp_host"], int(c["smtp_port"]), c.get("smtp_user"), c.get("smtp_password"), c["sender"])
            if c.get("enabled")
            else MockEmailAdapter()
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"adapter={self.adapter.name}")

    @action("send", SendIn, "notify:self", "Send a templated email")
    async def send(self, p: SendIn, ctx: PluginContext) -> dict:
        target = p.user_id if (p.user_id and ctx.principal.has("notify:any")) else ctx.principal.user_id
        if target is None:
            raise ValidationFailed("No recipient")
        to = await ctx.services.notifications.recipient_for(target, "EMAIL")
        if not to:
            raise ValidationFailed("Recipient has no email address")
        if p.dedupe_key and await ctx.services.notifications.already_sent(target, "EMAIL", p.dedupe_key):
            return {"notification_id": None, "status": "DUPLICATE_SKIPPED", "simulated": self.mode == "mock"}
        subject, body = render(p.template, p.context)
        res = await self.adapter.send(to, subject, body)
        note = await ctx.services.notifications.record(
            user_id=target,
            channel="EMAIL",
            template=p.template,
            recipient=to,
            subject=subject,
            body=body,
            status=res.status.value,
            meta={"provider": res.provider, "detail": res.detail, "dedupe_key": p.dedupe_key},
        )
        return {"notification_id": note.id, "status": res.status.value, "subject": subject, "simulated": self.mode == "mock"}

    @action("templates", NoInput, "notify:self", "Available templates")
    async def templates(self, p: NoInput, ctx: PluginContext) -> dict:
        return {"templates": sorted(TEMPLATES)}
