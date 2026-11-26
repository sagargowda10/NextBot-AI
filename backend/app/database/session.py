"""Async engine/session management."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_read_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, echo: bool = False) -> AsyncEngine:
    global _engine, _sessionmaker, _read_sessionmaker
    kwargs: dict = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"echo": echo, "connect_args": {"check_same_thread": False}}
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    _engine = create_async_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _enable_sqlite_savepoints(_engine)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    # Read-only helpers (RAG search) run *inside* a request that may already hold SQLite's write lock,
    # so they must not ask for it: they get a deferred BEGIN (WAL readers never block).
    _read_sessionmaker = async_sessionmaker(_engine.execution_options(nextbot_read_only=True), expire_on_commit=False, autoflush=False)
    return _engine


def _enable_sqlite_savepoints(engine: AsyncEngine) -> None:
    """pysqlite/aiosqlite don't emit BEGIN themselves, which breaks SAVEPOINT (begin_nested).
    This is the recipe from the SQLAlchemy SQLite dialect docs; also turns on FK enforcement."""

    @event.listens_for(engine.sync_engine, "connect")
    def _connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer (outbox relay, sinks)
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn):  # type: ignore[no-untyped-def]
        # IMMEDIATE takes SQLite's single write lock up front. With a plain (deferred) BEGIN, a request that reads and then
        # writes while a background writer (outbox relay, event consumers, execution sink) commits fails at once with
        # "database is locked" (stale WAL snapshot), ignoring busy_timeout. IMMEDIATE makes it wait instead.
        # SQLite only (local demo/tests); PostgreSQL uses normal MVCC transactions.
        conn.exec_driver_sql("BEGIN" if conn.get_execution_options().get("nextbot_read_only") else "BEGIN IMMEDIATE")


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine not initialised")
    return _engine


def read_session_factory() -> async_sessionmaker[AsyncSession]:
    """Sessions for read-only work nested inside a request (never take SQLite's write lock)."""
    if _read_sessionmaker is None:
        raise RuntimeError("Database engine not initialised")
    return _read_sessionmaker


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database engine not initialised")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session (unit of work) per request; commit on success."""
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()
