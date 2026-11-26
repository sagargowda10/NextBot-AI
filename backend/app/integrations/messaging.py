"""Channel adapters for email and WhatsApp.

Mock adapters never send anything; they return status SIMULATED so the UI and logs can show
exactly what *would* have been sent. Real adapters refuse to run without credentials.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

from app.core.enums import NotificationStatus
from app.core.exceptions import ExternalServiceNotConfigured

TEMPLATES: dict[str, tuple[str, str]] = {
    "order_confirmation": (
        "Order {order_number} confirmed",
        "Hi {name}, your order {order_number} for {total} is confirmed. We'll notify you when it ships.",
    ),
    "payment_success": ("Payment received for {order_number}", "We received {total} for order {order_number}. Reference: {reference}."),
    "payment_failed": (
        "Payment failed for {order_number}",
        "Your payment for order {order_number} did not go through ({reason}). You can retry from your orders page.",
    ),
    "shipment_update": ("Order {order_number}: {status}", "Your order {order_number} is now {status}. Tracking number: {tracking_number}."),
    "return_update": ("Return update for {order_number}", "Your return request for {order_number} is {status}. {message}"),
    "refund_update": ("Refund {status} for {order_number}", "A refund of {amount} for order {order_number} is {status}."),
    "support_escalation": ("We're on it", "Hi {name}, a support specialist will reply within 4 working hours. Ticket: {ticket}."),
    "generic": ("Update from NextBot", "{message}"),
}


class _SafeDict(dict):  # leaves unknown placeholders visible instead of raising
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(template: str, context: dict[str, Any]) -> tuple[str, str]:
    subject, body = TEMPLATES.get(template, TEMPLATES["generic"])
    ctx = _SafeDict({k: str(v) for k, v in context.items()})
    return subject.format_map(ctx), body.format_map(ctx)


@dataclass
class SendResult:
    status: NotificationStatus
    provider: str
    provider_message_id: str | None = None
    detail: str = ""


class EmailAdapter(Protocol):
    name: str

    async def send(self, to: str, subject: str, body: str) -> SendResult: ...


class WhatsAppAdapter(Protocol):
    name: str

    async def send(self, to: str, body: str) -> SendResult: ...


class MockEmailAdapter:
    name = "mock-email"

    async def send(self, to: str, subject: str, body: str) -> SendResult:
        return SendResult(NotificationStatus.SIMULATED, self.name, detail="EMAIL_ENABLED=false: not sent")


class SmtpEmailAdapter:
    name = "smtp"

    def __init__(self, host: str | None, port: int, user: str | None, password: str | None, sender: str) -> None:
        if not host:
            raise ExternalServiceNotConfigured("SMTP_HOST is not configured")
        self.host, self.port, self.user, self.password, self.sender = host, port, user, password, sender

    def _send_sync(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.starttls()
            if self.user and self.password:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> SendResult:
        try:
            await asyncio.to_thread(self._send_sync, to, subject, body)
            return SendResult(NotificationStatus.SENT, self.name)
        except (OSError, smtplib.SMTPException) as exc:
            return SendResult(NotificationStatus.FAILED, self.name, detail=str(exc))


class MockWhatsAppAdapter:
    name = "mock-whatsapp"

    async def send(self, to: str, body: str) -> SendResult:
        return SendResult(NotificationStatus.SIMULATED, self.name, detail="WHATSAPP_ENABLED=false: not sent")


class WhatsAppCloudAdapter:
    """Meta WhatsApp Business Cloud API (Graph API `/{phone_number_id}/messages`)."""

    name = "whatsapp-cloud"
    GRAPH = "https://graph.facebook.com/v21.0"

    def __init__(self, token: str | None, phone_number_id: str | None) -> None:
        if not token or not phone_number_id:
            raise ExternalServiceNotConfigured("WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required")
        self.token, self.phone_number_id = token, phone_number_id

    async def send(self, to: str, body: str) -> SendResult:
        import httpx

        payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": body[:4096]}}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{self.GRAPH}/{self.phone_number_id}/messages", headers={"Authorization": f"Bearer {self.token}"}, json=payload
            )
        if r.status_code >= 400:
            return SendResult(NotificationStatus.FAILED, self.name, detail=f"HTTP {r.status_code}")
        mid = (r.json().get("messages") or [{}])[0].get("id")
        return SendResult(NotificationStatus.SENT, self.name, provider_message_id=mid)


def parse_whatsapp_webhook(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Extract inbound text messages from a WhatsApp Cloud API webhook payload."""
    out: list[dict[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                if msg.get("type") == "text":
                    out.append({"from": msg.get("from", ""), "id": msg.get("id", ""), "text": msg["text"].get("body", "")})
    return out
