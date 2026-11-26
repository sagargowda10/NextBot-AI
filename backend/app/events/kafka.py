"""Kafka implementation of the event bus (aiokafka).

* Producer: idempotent (`enable_idempotence=True`, `acks="all"`), keyed by aggregate for ordering.
* Consumers: one consumer group per subscription; manual commit *after* the handler (at-least-once),
  made effectively-once by the idempotency store; poison messages go to `<topic>.dlq`.
* Events are published from the transactional outbox (`outbox.py`), so a Kafka outage never blocks
  order creation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logging import get_logger
from app.events.bus import ConsumerRunner, DeadLetter, Handler, IdempotencyStore, RetryPolicy, Subscription
from app.events.schemas import TOPICS, EventEnvelope, EventType

log = get_logger("events.kafka")


class KafkaEventBus:
    def __init__(self, bootstrap: str, prefix: str, idempotency: IdempotencyStore, retry: RetryPolicy | None = None) -> None:
        self.bootstrap, self.prefix = bootstrap, prefix
        self.subscriptions: list[Subscription] = []
        self.runner = ConsumerRunner(idempotency, retry or RetryPolicy(), self._dlq)
        self._producer: Any = None
        self._tasks: list[asyncio.Task[None]] = []
        self._consumers: list[Any] = []

    def topic(self, name: str) -> str:
        return f"{self.prefix}.{name}"

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap,
            enable_idempotence=True,
            acks="all",
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
            key_serializer=lambda k: k.encode(),
        )
        await self._producer.start()
        for sub in self.subscriptions:
            self._tasks.append(asyncio.create_task(self._consume(sub)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for c in self._consumers:
            await c.stop()
        if self._producer is not None:
            await self._producer.stop()

    def subscribe(self, name: str, event_types: list[EventType], handler: Handler) -> None:
        self.subscriptions.append(Subscription(name, frozenset(event_types), handler))

    async def publish(self, event: EventEnvelope) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer not started")
        await self._producer.send_and_wait(self.topic(event.topic), event.model_dump(mode="json"), key=event.key)

    async def _dlq(self, dl: DeadLetter) -> None:
        payload = {**dl.event.model_dump(mode="json"), "dlq_consumer": dl.consumer, "dlq_error": dl.error}
        await self._producer.send_and_wait(self.topic(dl.event.topic) + ".dlq", payload, key=dl.event.key)
        log.error("event_dead_lettered", extra={"consumer": dl.consumer, "event": dl.event.event_id})

    async def _consume(self, sub: Subscription) -> None:
        from aiokafka import AIOKafkaConsumer

        topics = sorted({self.topic(TOPICS[t]) for t in sub.event_types})
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap,
            group_id=f"{self.prefix}.{sub.name}",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda b: json.loads(b.decode()),
        )
        await consumer.start()
        self._consumers.append(consumer)
        try:
            async for msg in consumer:
                try:
                    event = EventEnvelope.model_validate(msg.value)
                except Exception:
                    log.error("event_unparseable", extra={"topic": msg.topic, "offset": msg.offset})
                    await consumer.commit()
                    continue
                if event.event_type in sub.event_types:
                    await self.runner.deliver(sub, event)
                await consumer.commit()
        except asyncio.CancelledError:
            pass
