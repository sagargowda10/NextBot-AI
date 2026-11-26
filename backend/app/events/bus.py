"""Event bus abstraction with retry, dead-letter and idempotent consumers.

`InMemoryEventBus` (demo/tests) and `KafkaEventBus` (`kafka.py`) share `ConsumerRunner`, so the
retry → DLQ → idempotency semantics are identical and unit-testable without a broker.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.core.logging import get_logger
from app.events.schemas import EventEnvelope, EventType

log = get_logger("events")

Handler = Callable[[EventEnvelope], Awaitable[None]]


class IdempotencyStore(Protocol):
    async def seen(self, consumer: str, event_id: str) -> bool: ...
    async def mark(self, consumer: str, event_id: str) -> None: ...


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    async def seen(self, consumer: str, event_id: str) -> bool:
        return (consumer, event_id) in self._seen

    async def mark(self, consumer: str, event_id: str) -> None:
        self._seen.add((consumer, event_id))


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.2
    max_delay_s: float = 5.0

    def delay(self, attempt: int) -> float:
        return min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))


@dataclass
class Subscription:
    name: str
    event_types: frozenset[EventType]
    handler: Handler


@dataclass
class DeadLetter:
    consumer: str
    event: EventEnvelope
    error: str


class ConsumerRunner:
    """Runs one handler for one event with idempotency, retries and dead-lettering."""

    def __init__(
        self,
        idempotency: IdempotencyStore,
        retry: RetryPolicy,
        dlq: Callable[[DeadLetter], Awaitable[None]],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.idem, self.retry, self.dlq, self.sleep = idempotency, retry, dlq, sleep

    async def deliver(self, sub: Subscription, event: EventEnvelope) -> str:
        if await self.idem.seen(sub.name, event.event_id):
            log.info("event_duplicate_skipped", extra={"consumer": sub.name, "event": event.event_id})
            return "duplicate"
        last_error = ""
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                await sub.handler(event.model_copy(update={"attempt": attempt}))
                await self.idem.mark(sub.name, event.event_id)
                return "processed"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "event_handler_failed", extra={"consumer": sub.name, "event": event.event_id, "attempt": attempt, "error": last_error}
                )
                if attempt < self.retry.max_attempts:
                    await self.sleep(self.retry.delay(attempt))
        await self.dlq(DeadLetter(sub.name, event, last_error))
        return "dead_lettered"


class EventBus(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...
    def subscribe(self, name: str, event_types: list[EventType], handler: Handler) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


@dataclass
class InMemoryEventBus:
    idempotency: IdempotencyStore = field(default_factory=MemoryIdempotencyStore)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        self.subscriptions: list[Subscription] = []
        self.dead_letters: list[DeadLetter] = []
        self.published: list[EventEnvelope] = []
        self.stats: dict[str, int] = defaultdict(int)
        self.runner = ConsumerRunner(self.idempotency, self.retry, self._dlq, self.sleep)

    async def _dlq(self, dl: DeadLetter) -> None:
        self.dead_letters.append(dl)
        self.stats["dead_lettered"] += 1
        log.error("event_dead_lettered", extra={"consumer": dl.consumer, "event": dl.event.event_id, "error": dl.error})

    def subscribe(self, name: str, event_types: list[EventType], handler: Handler) -> None:
        self.subscriptions.append(Subscription(name, frozenset(event_types), handler))

    async def publish(self, event: EventEnvelope) -> None:
        self.published.append(event)
        self.stats["published"] += 1
        for sub in self.subscriptions:
            if event.event_type in sub.event_types:
                outcome = await self.runner.deliver(sub, event)
                self.stats[outcome] += 1

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
