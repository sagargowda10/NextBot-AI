"""pgvector-backed vector store (KnowledgeChunk table). Falls back to in-Python cosine on SQLite."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.ai import KnowledgeChunk
from app.rag.embeddings import cosine
from app.rag.vector_store import ScoredChunk, StoredChunk, matches


class PgVectorStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], read_sessions: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.sessions = sessions
        self.read_sessions = read_sessions or sessions  # search runs inside chat requests -> must not need the write lock

    async def upsert(self, chunks: list[StoredChunk]) -> None:
        async with self.sessions() as s, s.begin():
            doc_ids = {c.document_id for c in chunks}
            await s.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(doc_ids)))
            s.add_all(
                KnowledgeChunk(
                    id=c.id,
                    document_id=c.document_id,
                    title=c.title,
                    chunk_index=int(c.metadata.get("chunk_index", 0)),
                    content=c.content,
                    category=str(c.metadata.get("category", "general")),
                    meta=c.metadata,
                    embedding=c.embedding,
                )
                for c in chunks
            )

    async def search(self, query_vec: list[float], k: int, filters: dict[str, Any] | None = None) -> list[ScoredChunk]:
        async with self.read_sessions() as s:
            dialect = s.bind.dialect.name
            if dialect == "postgresql":
                # pgvector cosine distance. Use the SQL operator directly: the Embedding TypeDecorator (Text impl, so the
                # same model works on SQLite) hides pgvector's .cosine_distance() comparator.
                dist = KnowledgeChunk.embedding.op("<=>", return_type=Float)(query_vec)
                stmt = select(KnowledgeChunk, dist.label("d"))
                if filters and "category" in filters:
                    cat = filters["category"]
                    stmt = stmt.where(KnowledgeChunk.category.in_(cat) if isinstance(cat, list) else KnowledgeChunk.category == cat)
                rows = (await s.execute(stmt.order_by(dist).limit(k))).all()
                return [ScoredChunk(_to_stored(r[0]), 1.0 - float(r[1])) for r in rows]
            rows2 = (await s.scalars(select(KnowledgeChunk))).all()
            scored = [
                ScoredChunk(_to_stored(r), cosine(query_vec, r.embedding))
                for r in rows2
                if matches({**r.meta, "category": r.category}, filters)
            ]
            scored.sort(key=lambda x: x.score, reverse=True)
            return scored[:k]

    async def count(self) -> int:
        async with self.read_sessions() as s:
            return len((await s.scalars(select(KnowledgeChunk.id))).all())


def _to_stored(r: KnowledgeChunk) -> StoredChunk:
    return StoredChunk(
        id=r.id,
        document_id=r.document_id,
        title=r.title,
        content=r.content,
        embedding=r.embedding or [],
        metadata={**(r.meta or {}), "category": r.category},
    )
