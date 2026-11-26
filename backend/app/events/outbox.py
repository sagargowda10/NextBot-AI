"""Transactional outbox + relay, and a DB-backed idempotency store for consumers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.events.bus import EventBus
from app.events.schemas import EventEnvelope, EventType
from app.models.platform import OutboxEvent, ProcessedEvent

log = get_logger("outbox")


def add_event(
    session: AsyncSession, event_type: EventType, aggregate_type: str, aggregate_id: Any, payload: dict[str, Any]
) -> EventEnvelope:
    """Stage an event in the caller's transaction. It is published only if that transaction commits."""
    env = EventEnvelope(event_type=event_type, aggregate_type=aggregate_type, aggregate_id=str(aggregate_id), payload=payload)
    session.add(
        OutboxEvent(
            event_id=env.event_id,
            event_type=env.event_type.value,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            payload=env.model_dump(mode="json"),
        )
    )
    return env


class OutboxRelay:
    """Polls unpublished outbox rows and publishes them. At-least-once; consumers dedupe by event_id."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], bus: EventBus, interval_s: float = 1.0, batch: int = 100) -> None:
        self.sessions, self.bus, self.interval, self.batch = sessions, bus, interval_s, batch
        self._stop = asyncio.Event()
        self.published = 0

    async def run_once(self) -> int:
        async with self.sessions() as s:
            rows = list(
                (
                    await s.scalars(
                        select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.id).limit(self.batch)
                    )
                ).all()
            )
            ids = [(r.id, r.payload) for r in rows]
        done = 0
        for row_id, payload in ids:
            env = EventEnvelope.model_validate(payload)
            try:
                await self.bus.publish(env)
                status: dict[str, Any] = {"published_at": datetime.now(UTC)}
                done += 1
            except Exception as exc:  # broker down: leave unpublished, retry next tick
                status = {"last_error": str(exc)[:480]}
                log.warning("outbox_publish_failed", extra={"event": env.event_id, "error": str(exc)})
            async with self.sessions() as s, s.begin():
                row = await s.get(OutboxEvent, row_id)
                if row is not None:
                    row.attempts += 1
                    for k, v in status.items():
                        setattr(row, k, v)
        self.published += done
        return done

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("outbox_relay_error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()


class DbIdempotencyStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def seen(self, consumer: str, event_id: str) -> bool:
        async with self.sessions() as s:
            return (
                await s.scalar(select(ProcessedEvent.id).where(ProcessedEvent.consumer == consumer, ProcessedEvent.event_id == event_id))
            ) is not None

    async def mark(self, consumer: str, event_id: str) -> None:
        try:
            async with self.sessions() as s, s.begin():
                s.add(ProcessedEvent(consumer=consumer, event_id=event_id))
        except IntegrityError:  # concurrent duplicate — already processed
            pass
