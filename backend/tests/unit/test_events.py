import pytest

from app.events.bus import InMemoryEventBus, RetryPolicy
from app.events.schemas import EventEnvelope, EventType

pytestmark = pytest.mark.anyio


async def no_sleep(_: float) -> None:
    return None


def order_created(order_id: str = "1") -> EventEnvelope:
    return EventEnvelope(event_type=EventType.ORDER_CREATED, aggregate_type="order", aggregate_id=order_id, payload={"total": "100"})


async def test_publish_delivers_to_matching_subscribers_only():
    bus = InMemoryEventBus(sleep=no_sleep)
    seen: list[str] = []

    async def on_order(e: EventEnvelope) -> None:
        seen.append(e.event_type)

    bus.subscribe("notifier", [EventType.ORDER_CREATED], on_order)
    await bus.publish(order_created())
    await bus.publish(EventEnvelope(event_type=EventType.PAYMENT_FAILED, aggregate_type="payment", aggregate_id="9"))
    assert seen == ["OrderCreated"] and bus.stats["processed"] == 1


async def test_duplicate_events_are_processed_once():
    bus = InMemoryEventBus(sleep=no_sleep)
    calls = 0

    async def handler(e: EventEnvelope) -> None:
        nonlocal calls
        calls += 1

    bus.subscribe("idem", [EventType.ORDER_CREATED], handler)
    ev = order_created()
    await bus.publish(ev)
    await bus.publish(ev)  # redelivery (e.g. consumer restart before commit)
    assert calls == 1 and bus.stats["duplicate"] == 1


async def test_transient_failure_is_retried_then_succeeds():
    bus = InMemoryEventBus(retry=RetryPolicy(max_attempts=3), sleep=no_sleep)
    attempts: list[int] = []

    async def flaky(e: EventEnvelope) -> None:
        attempts.append(e.attempt)
        if e.attempt < 2:
            raise ConnectionError("smtp down")

    bus.subscribe("flaky", [EventType.ORDER_CREATED], flaky)
    await bus.publish(order_created())
    assert attempts == [1, 2] and not bus.dead_letters


async def test_poison_event_goes_to_dead_letter_queue_and_other_consumers_still_run():
    bus = InMemoryEventBus(retry=RetryPolicy(max_attempts=3), sleep=no_sleep)
    ok: list[str] = []

    async def broken(e: EventEnvelope) -> None:
        raise ValueError("bad payload")

    async def healthy(e: EventEnvelope) -> None:
        ok.append(e.event_id)

    bus.subscribe("broken", [EventType.ORDER_CREATED], broken)
    bus.subscribe("healthy", [EventType.ORDER_CREATED], healthy)
    ev = order_created("42")
    await bus.publish(ev)
    assert len(bus.dead_letters) == 1 and bus.dead_letters[0].consumer == "broken"
    assert "ValueError" in bus.dead_letters[0].error and ok == [ev.event_id]


def test_retry_backoff_and_partition_key():
    r = RetryPolicy(base_delay_s=0.5, max_delay_s=3)
    assert [r.delay(i) for i in (1, 2, 3, 4)] == [0.5, 1.0, 2.0, 3]
    assert order_created("7").key == "order:7" and order_created().topic == "orders"
