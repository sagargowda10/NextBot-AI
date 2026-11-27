"""RAG retrieval on real PostgreSQL + pgvector (Testcontainers): the cosine-distance query must work there,
not only on the SQLite fallback path. Requires Docker; skipped otherwise."""

import importlib.util
import shutil

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.containers, pytest.mark.anyio]

if importlib.util.find_spec("testcontainers") is None or shutil.which("docker") is None:
    pytest.skip("Docker/testcontainers not available", allow_module_level=True)


async def test_pgvector_search_and_grounded_answer():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer

    from app.database.base import Base
    from app.models.ai import KnowledgeDocument
    from app.rag.embeddings import HashingEmbedder
    from app.rag.pgvector_store import PgVectorStore
    from app.rag.pipeline import KnowledgeDoc, RagPipeline

    docs = [
        KnowledgeDoc("return-policy", "Return policy", "policy", "Most items can be returned within 10 days of delivery.", "kb/r.md"),
        KnowledgeDoc("shipping", "Shipping policy", "policy", "Standard delivery takes 3 to 5 working days across India.", "kb/s.md"),
    ]
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        engine = create_async_engine(pg.get_connection_url().replace("psycopg2", "asyncpg"))
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as s, s.begin():
            s.add_all(
                KnowledgeDocument(id=d.doc_id, title=d.title, category=d.category, source=d.source, content=d.content, checksum="x")
                for d in docs
            )
        rag = RagPipeline(HashingEmbedder(384), PgVectorStore(sessions), chunk_size=600, overlap=80, top_k=2, min_score=0.05)
        assert await rag.index(docs) >= 2
        hits = await rag.retrieve("How many days do I have to return an item?")
        assert hits and hits[0].chunk.document_id == "return-policy"
        ans = await rag.answer("What is your return policy?")
        assert ans.grounded and "10 days" in ans.answer
        await engine.dispose()
