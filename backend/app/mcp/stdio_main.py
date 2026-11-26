"""Run the NextBot MCP server over stdio (for Claude Desktop, IDEs or any MCP host).

    NEXTBOT_MCP_USER=asha@nextbot.demo python -m app.mcp.stdio_main

Tool calls execute as the configured user (permissions are that user's role permissions).
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select


async def _main() -> None:
    from app.bootstrap import build_state, start
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.database.session import init_engine, session_factory
    from app.mcp.gateway import PluginToolGateway
    from app.mcp.server import build_mcp_server
    from app.models.user import User
    from app.services.auth_service import principal_for
    from app.services.container import container_factory

    s = get_settings()
    configure_logging("WARNING", sys.stderr)  # stdout belongs to the MCP protocol
    init_engine(s.database_url)
    state = build_state(s)
    await start(state)
    email = os.environ.get("NEXTBOT_MCP_USER", "asha@nextbot.demo")
    async with session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        raise SystemExit(f"NEXTBOT_MCP_USER {email!r} not found")
    server = build_mcp_server(
        PluginToolGateway(state.plugins, container_factory(state), {"agent_metrics": state.metrics}), default_principal=principal_for(user)
    )
    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(_main())
