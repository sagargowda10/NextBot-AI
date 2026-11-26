"""Vector store interface + in-memory implementation (pgvector implementation: `pgvector_store.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.rag.embeddings import cosine


@dataclass
class StoredChunk:
    id: str
    document_id: str
    title: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredChunk:
    chunk: StoredChunk
    score: float


class VectorStore(Protocol):
    async def upsert(self, chunks: list[StoredChunk]) -> None: ...
    async def search(self, query_vec: list[float], k: int, filters: dict[str, Any] | None = None) -> list[ScoredChunk]: ...
    async def count(self) -> int: ...


def matches(meta: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, val in filters.items():
        have = meta.get(key)
        if isinstance(val, list | tuple | set):
            if have not in val:
                return False
        elif have != val:
            return False
    return True


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, StoredChunk] = {}

    async def upsert(self, chunks: list[StoredChunk]) -> None:
        for c in chunks:
            self._chunks[c.id] = c

    async def search(self, query_vec: list[float], k: int, filters: dict[str, Any] | None = None) -> list[ScoredChunk]:
        scored = [ScoredChunk(c, cosine(query_vec, c.embedding)) for c in self._chunks.values() if matches(c.metadata, filters)]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:k]

    async def count(self) -> int:
        return len(self._chunks)
