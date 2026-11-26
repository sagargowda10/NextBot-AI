"""NextBot AI — FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.bootstrap import build_state, start, stop
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.database.base import Base
from app.database.session import dispose_engine, get_engine, init_engine, session_factory
from app.monitoring import metrics
from app.monitoring.tracing import setup_tracing

log = get_logger("app")
API_DESCRIPTION = """
**NextBot AI** — an omnichannel e-commerce platform run by a Supervisor Agent and 11 specialised AI agents
that act only through 12 permission-checked business plugins.

* Demo mode (`DEMO_MODE=true`, `AI_PROVIDER=mock`, `PAYMENT_PROVIDER=mock`) needs no paid credentials.
* Authenticate with `POST /api/v1/auth/login`, then click **Authorize** and paste the access token.
* MCP endpoint: `POST /mcp` (Streamable HTTP, `Authorization: Bearer <access token>`).
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    configure_logging(s.log_level)
    init_engine(s.database_url, s.db_echo)
    state = build_state(s)

    from mcp.server.transport_security import TransportSecuritySettings

    from app.bootstrap import _authenticator
    from app.mcp.gateway import PluginToolGateway
    from app.mcp.server import build_mcp_server
    from app.services.container import container_factory

    state_mcp = build_mcp_server(
        PluginToolGateway(state.plugins, container_factory(state), {"agent_metrics": state.metrics}),
        default_principal=None,
        authenticate=_authenticator(),
    )
    mcp_http = state_mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=s.mcp_allowed_hosts, allowed_origins=s.cors_origins),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            if s.environment in ("local", "test") or s.is_sqlite:
                async with get_engine().begin() as conn:  # dev convenience; production uses `alembic upgrade head`
                    if not s.is_sqlite:
                        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    await conn.run_sync(Base.metadata.create_all)
            if s.seed_on_startup:
                from app.database.seed import seed

                async with session_factory()() as db:
                    if await seed(db):
                        log.info("demo_data_seeded")
                    await db.commit()
            await start(state)
            await stack.enter_async_context(state_mcp.session_manager.run())
            yield
            await stop(state)
        await dispose_engine()

    app = FastAPI(
        title="NextBot AI",
        version="1.0.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=[{"name": "AI Assistant", "description": "Supervisor + 11 agents"}],
    )
    app.state.nb = state
    state.mcp_server = state_mcp
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    metrics.install(app, state)
    register_exception_handlers(app)
    app.include_router(api_router)
    app.mount("/mcp", mcp_http)
    setup_tracing(app, s, get_engine())

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, Any]:
        return {"status": "ok", "demo_mode": s.demo_mode, "ai_provider": state.llm.name, "payment_provider": state.gateway.name}

    @app.get("/health/ready", tags=["Health"])
    async def ready() -> JSONResponse:
        checks: dict[str, Any] = {}
        try:
            async with session_factory()() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        checks["cache"] = f"{state.cache.name}:{'ok' if await state.cache.ping() else 'down'}"
        checks["traces"] = f"{state.traces.name}:{'ok' if await state.traces.ping() else 'down'}"
        checks["plugins"] = state.plugins.summary()
        checks["event_bus"] = type(state.bus).__name__
        ok = checks["database"] == "ok"
        return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)

    return app
