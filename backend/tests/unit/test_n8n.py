import json

import httpx
import pytest

from app.events.schemas import EventEnvelope, EventType
from app.integrations.n8n import N8nForwarder, sign

pytestmark = pytest.mark.anyio


def event() -> EventEnvelope:
    return EventEnvelope(event_type=EventType.ORDER_CREATED, aggregate_type="order", aggregate_id="7", payload={"order_number": "NB-1"})


async def test_forwards_signed_event_to_n8n():
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(headers=dict(req.headers), body=req.content, url=str(req.url))
        return httpx.Response(200, json={"message": "Workflow was started"})

    fw = N8nForwarder("http://n8n:5678/webhook/nextbot-events", "tok", "secret", transport=httpx.MockTransport(handler))
    evt = event()
    await fw(evt)
    assert seen["url"].endswith("/webhook/nextbot-events")
    assert seen["headers"]["x-nextbot-token"] == "tok" and seen["headers"]["x-nextbot-event"] == "OrderCreated"
    assert seen["headers"]["x-nextbot-signature"] == sign("secret", seen["body"])  # receiver can verify integrity
    assert json.loads(seen["body"])["payload"]["order_number"] == "NB-1"
    assert fw.sent == 1 and fw.failed == 0 and fw.for_events({evt.event_id})[0].ok


async def test_inactive_workflow_or_outage_never_raises():
    fw404 = N8nForwarder("http://n8n/webhook/x", "t", "s", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    await fw404(event())  # must not raise: n8n is optional and must never block orders
    assert fw404.failed == 1 and "Active" in (fw404.last_error or "")

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down = N8nForwarder("http://n8n/webhook/x", "t", "s", transport=httpx.MockTransport(boom))
    await down(event())
    assert down.failed == 1 and "unreachable" in (down.last_error or "")
