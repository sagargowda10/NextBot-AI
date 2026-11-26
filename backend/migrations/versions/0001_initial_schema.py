"""Initial schema: 33 domain entities + KnowledgeChunk, OutboxEvent, ProcessedEvent; pgvector extension + HNSW index.

The baseline revision materialises the SQLAlchemy model metadata (single source of truth for the
36 tables, their PK/FK/unique/check constraints and indexes). Every later change must be a normal
`alembic revision --autogenerate` revision on top of this one.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-25
"""
from alembic import op

import app.models  # noqa: F401
from app.database.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        # approximate-nearest-neighbour index for cosine similarity search
        op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
                   "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
