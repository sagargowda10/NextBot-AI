"""Wires the application: settings → infrastructure adapters → plugins → agents → RAG → events → MCP."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentMetrics
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.core.enums import Role
from app.core.logging import get_logger
from app.core.state import AppState
from app.database.session import read_session_factory, session_factory
from app.domain.approvals import ApprovalPolicy
from app.events.bus import InMemoryEventBus
from app.events.handlers import register_consumers
from app.events.outbox import DbIdempotencyStore, OutboxRelay
from app.integrations.cache import build_cache
from app.integrations.llm.openai_provider import build_llm
from app.integrations.mongo import build_trace_store
from app.integrations.payments import MockGateway, build_gateway
from app.integrations.search import OpenSearchProductIndex
from app.integrations.shipping import MockCourier, build_courier
from app.mcp.gateway import PluginToolGateway
from app.mcp.server import build_mcp_server
from app.models.ai import KnowledgeDocument
from app.models.catalog import Product
from app.models.platform import Plugin, PluginConfiguration
from app.orchestration.orchestrator import DbPluginExecutionSink
from app.plugins.manager import PluginManager
from app.plugins.registry import builtin_plugins, configs_from_settings, entrypoint_plugins
from app.rag.embeddings import HashingEmbedder, OpenAIEmbedder
from app.rag.pgvector_store import PgVectorStore
from app.rag.pipeline import KnowledgeDoc, RagPipeline
from app.rag.vector_store import StoredChunk
from app.security.permissions import Principal
from app.services.container import container_factory

log = get_logger("bootstrap")


def build_state(s: Settings) -> AppState:
    embedder: Any = (
        OpenAIEmbedder(s.openai_api_key, s.openai_embedding_model, s.embedding_dim)
        if s.ai_provider == "openai" and s.openai_api_key
        else HashingEmbedder(s.embedding_dim)
    )
    rag = RagPipeline(
        embedder,
        PgVectorStore(session_factory(), read_session_factory()),
        chunk_size=s.rag_chunk_size,
        overlap=s.rag_chunk_overlap,
        top_k=s.rag_top_k,
        min_score=s.rag_min_score,
    )
    plugins = PluginManager(sink=DbPluginExecutionSink(session_factory()), default_timeout_s=s.agent_timeout_s)
    plugins.register_many([*builtin_plugins(), *entrypoint_plugins()])
    try:
        gateway: Any = build_gateway(s.payment_provider, s)
    except Exception as exc:
        log.error("payment_gateway_unavailable_using_mock", extra={"error": str(exc)})
        gateway = MockGateway()
    try:
        courier: Any = build_courier(s.shipping_provider, s)
    except Exception as exc:
        log.error("courier_unavailable_using_mock", extra={"error": str(exc)})
        courier = MockCourier()
    if s.event_bus == "kafka":
        from app.events.kafka import KafkaEventBus

        bus: Any = KafkaEventBus(s.kafka_bootstrap_servers, s.kafka_topic_prefix, DbIdempotencyStore(session_factory()))
    else:
        bus = InMemoryEventBus(idempotency=DbIdempotencyStore(session_factory()))
    return AppState(
        settings=s,
        plugins=plugins,
        agents=AgentRegistry(),
        metrics=AgentMetrics(),
        llm=build_llm(s.ai_provider, s.openai_api_key, s.openai_model),
        rag=rag,
        bus=bus,
        cache=build_cache(s.redis_url),
        traces=build_trace_store(s.mongo_url, s.mongo_db),
        gateway=gateway,
        courier=courier,
        policy=ApprovalPolicy(
            Decimal(str(s.refund_approval_threshold)),
            Decimal(str(s.cancellation_approval_threshold)),
            s.inventory_adjustment_approval_units,
            s.fraud_review_score,
        ),
        search_index=OpenSearchProductIndex(s.opensearch_url) if s.search_backend == "opensearch" and s.opensearch_url else None,
    )


async def start(state: AppState) -> None:
    s = state.settings
    sessions = session_factory()
    # 1. plugins: env config + admin overrides from DB, then sync the durable registry rows
    configs = configs_from_settings(s)
    async with sessions() as db:
        for row in (await db.scalars(select(PluginConfiguration))).all():
            configs[row.plugin_id] = {**configs.get(row.plugin_id, {}), **(row.values or {})}
        disabled = {r.id for r in (await db.scalars(select(Plugin).where(Plugin.desired_enabled.is_(False)))).all()}
    for pid in disabled & set(state.plugins.ids()):
        state.plugins.get(pid).desired_enabled = False
    await state.plugins.initialize_all(configs)
    async with sessions() as db, db.begin():
        for reg in state.plugins.list():
            p = reg.plugin
            plugin_row = await db.get(Plugin, p.plugin_id)
            if plugin_row is None:
                db.add(
                    Plugin(
                        id=p.plugin_id,
                        name=p.name,
                        version=p.version,
                        description=p.description,
                        status=reg.status.value,
                        desired_enabled=reg.desired_enabled,
                        registered_at=reg.registered_at,
                    )
                )
            else:
                plugin_row.version, plugin_row.status, plugin_row.description = p.version, reg.status.value, p.description

    # 2. RAG index: knowledge documents + product descriptions (for semantic product search)
    await index_knowledge(state)

    # 3. MCP server (in-process; also mounted at /mcp) + wire the MCP Integration plugin to it
    gateway = PluginToolGateway(state.plugins, container_factory(state), {"agent_metrics": state.metrics})
    admin_service = Principal(user_id=None, email="mcp-client@nextbot.local", roles=frozenset({Role.SYSTEM}))
    local_server = build_mcp_server(gateway, default_principal=admin_service)
    state.plugins.get("mcp_integration").plugin.inprocess_server = local_server  # type: ignore[attr-defined]

    # 4. events: consumers, broker, outbox relay, reservation sweeper
    register_consumers(state.bus, state)
    await state.bus.start()
    relay = OutboxRelay(sessions, state.bus, s.outbox_poll_interval_s)
    state.background += [
        relay,
        asyncio.create_task(relay.run_forever()),
        asyncio.create_task(_sweeper(state)),
        asyncio.create_task(_flush_executions(state)),
    ]
    log.info(
        "nextbot_started",
        extra={
            "demo_mode": s.demo_mode,
            "ai": state.llm.name,
            "bus": type(state.bus).__name__,
            "cache": state.cache.name,
            "traces": state.traces.name,
        },
    )


async def stop(state: AppState) -> None:
    for item in state.background:
        if isinstance(item, OutboxRelay):
            item.stop()
        elif isinstance(item, asyncio.Task):
            item.cancel()
    await state.bus.stop()
    await state.plugins.shutdown_all()


async def index_knowledge(state: AppState) -> int:
    sessions = session_factory()

    async with sessions() as db:
        docs = [KnowledgeDoc(d.id, d.title, d.category, d.content, d.source) for d in (await db.scalars(select(KnowledgeDocument))).all()]

        products = (await db.scalars(select(Product).where(Product.is_active.is_(True)))).all()

        product_rows = [
            (
                p.id,
                p.name,
                p.category.slug,
                f"{p.name}. {p.description} {p.tags} " + " ".join(f"{k}: {v}." for k, v in (p.specifications or {}).items()),
            )
            for p in products
        ]

    # Index existing knowledge-base documents.
    n = await state.rag.index(docs) if docs else 0

    # Create parent documents before inserting product chunks.
    if product_rows:
        async with sessions() as db, db.begin():
            for pid, name, _cat, content in product_rows:
                doc_id = f"product-{pid}"

                checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

                document = await db.get(KnowledgeDocument, doc_id)

                if document is None:
                    db.add(
                        KnowledgeDocument(
                            id=doc_id,
                            title=name,
                            category="product",
                            source=f"products/{pid}",
                            content=content,
                            checksum=checksum,
                        )
                    )
                else:
                    document.title = name
                    document.category = "product"
                    document.source = f"products/{pid}"
                    document.content = content
                    document.checksum = checksum

        # Generate product embeddings.
        vectors = await state.rag.embedder.embed([content for _, _, _, content in product_rows])

        # Insert child chunks after parent records are committed.
        chunks = [
            StoredChunk(
                id=f"product-{pid}:0",
                document_id=f"product-{pid}",
                title=name,
                content=content,
                embedding=vector,
                metadata={
                    "category": "product",
                    "product_id": pid,
                    "product_category": cat,
                    "chunk_index": 0,
                },
            )
            for (pid, name, cat, content), vector in zip(product_rows, vectors, strict=True)
        ]

        await state.rag.store.upsert(chunks)

    # Optional OpenSearch indexing.
    if state.search_index is not None:
        try:
            async with sessions() as db:
                rows = (await db.scalars(select(Product).where(Product.is_active.is_(True)))).all()

                docs_os = [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "tags": p.tags,
                        "category": p.category.slug,
                        "brand": p.brand.slug,
                        "price": float(p.price),
                        "is_active": True,
                        "colours": sorted({(v.colour or "").lower() for v in p.variants if v.colour}),
                        "sizes": sorted({(v.size or "").lower() for v in p.variants if v.size}),
                    }
                    for p in rows
                ]

            await state.search_index.index_products(docs_os)

        except Exception as exc:
            log.warning("opensearch_index_failed", extra={"error": str(exc)})

    log.info(
        "rag_indexed",
        extra={
            "kb_chunks": n,
            "products": len(product_rows),
            "at": datetime.now(UTC).isoformat(),
        },
    )

    return n


def _authenticator() -> Any:
    from app.security.dependencies import principal_from_token

    async def authenticate(token: str) -> Principal:
        async with session_factory()() as db:
            return await principal_from_token(token, db)

    return authenticate


async def _flush_executions(state: AppState) -> None:
    sink = state.plugins._sink  # noqa: SLF001 - the sink we installed in build_state
    while isinstance(sink, DbPluginExecutionSink):
        await asyncio.sleep(2)
        try:
            await sink.flush()
        except Exception:
            log.warning("plugin_execution_flush_failed")


async def _sweeper(state: AppState) -> None:
    from app.services.order_service import OrderService

    while True:
        await asyncio.sleep(60)
        try:
            async with session_factory()() as db, db.begin():
                n = await OrderService(db, state).expire_stale_reservations()
            if n:
                log.info("reservations_expired", extra={"orders": n})
        except Exception:
            log.exception("sweeper_failed")
