"""MongoDB store for flexible agent traces and conversation transcripts (PyMongo async API).

PostgreSQL holds the authoritative conversation rows; MongoDB keeps the schemaless per-turn
trace (plan, entities, every agent output and tool call) that is handy for debugging and analytics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol


class TraceStore(Protocol):
    name: str

    async def save_turn(self, doc: dict[str, Any]) -> None: ...
    async def recent(self, user_id: int | None, limit: int = 20) -> list[dict[str, Any]]: ...
    async def ping(self) -> bool: ...


class NullTraceStore:
    name = "disabled"

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def save_turn(self, doc: dict[str, Any]) -> None:
        self.docs = (self.docs + [doc])[-200:]

    async def recent(self, user_id: int | None, limit: int = 20) -> list[dict[str, Any]]:
        return [d for d in reversed(self.docs) if user_id is None or d.get("user_id") == user_id][:limit]

    async def ping(self) -> bool:
        return True


class MongoTraceStore:
    name = "mongodb"

    def __init__(self, url: str, db: str) -> None:
        from pymongo import AsyncMongoClient

        self.client: Any = AsyncMongoClient(url, serverSelectionTimeoutMS=2000)
        self.col = self.client[db]["agent_traces"]

    async def save_turn(self, doc: dict[str, Any]) -> None:
        await self.col.insert_one({**doc, "created_at": datetime.now(UTC)})

    async def recent(self, user_id: int | None, limit: int = 20) -> list[dict[str, Any]]:
        q = {} if user_id is None else {"user_id": user_id}
        cur = self.col.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [d async for d in cur]

    async def ping(self) -> bool:
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False


def build_trace_store(url: str | None, db: str) -> TraceStore:
    return MongoTraceStore(url, db) if url else NullTraceStore()
