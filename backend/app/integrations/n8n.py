"""n8n integration: forwards NextBot domain events to an n8n webhook so business teams can automate on them.

Best effort by design: n8n being down or the workflow being inactive must never block orders, so failures are
recorded (and shown on the admin Workflows page) instead of being retried into the dead-letter queue.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.logging import get_logger
from app.events.schemas import EventEnvelope

log = get_logger("n8n")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@dataclass
class Delivery:
    event_id: str
    event_type: str
    aggregate_id: str
    ok: bool
    status_code: int | None
    error: str | None
    at: str


@dataclass
class N8nForwarder:
    url: str
    token: str
    secret: str
    timeout_s: float = 5.0
    transport: httpx.AsyncBaseTransport | None = None  # injectable for tests
    sent: int = 0
    failed: int = 0
    last_error: str | None = None
    recent: deque[Delivery] = field(default_factory=lambda: deque(maxlen=200))

    async def __call__(self, event: EventEnvelope) -> None:
        body = json.dumps(event.model_dump(mode="json"), separators=(",", ":")).encode()
        headers = {
            "content-type": "application/json",
            "x-nextbot-event": event.event_type.value,
            "x-nextbot-token": self.token,
            "x-nextbot-signature": sign(self.secret, body),
        }
        code: int | None = None
        error: str | None = None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
                res = await client.post(self.url, content=body, headers=headers)
            code = res.status_code
            if res.status_code >= 400:
                error = f"n8n answered HTTP {res.status_code}" + (" - is the workflow Active?" if res.status_code == 404 else "")
        except httpx.HTTPError as e:
            error = f"n8n unreachable: {type(e).__name__}"
        ok = error is None
        self.sent += ok
        self.failed += not ok
        self.last_error = error or self.last_error
        self.recent.appendleft(
            Delivery(event.event_id, event.event_type.value, event.aggregate_id, ok, code, error, datetime.now(UTC).isoformat())
        )
        if not ok:
            log.warning("n8n_forward_failed", extra={"event": event.event_id, "error": error})

    def for_events(self, event_ids: set[str]) -> list[Delivery]:
        return [d for d in self.recent if d.event_id in event_ids]

    def status(self) -> dict[str, Any]:
        return {"sent": self.sent, "failed": self.failed, "last_error": self.last_error}
