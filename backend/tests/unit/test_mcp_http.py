"""MCP over real Streamable HTTP (uvicorn + the SDK's HTTP client), mounted exactly like app/main.py does.

Verifies bearer-token identity on the HTTP transport: no token → tool error, bad token → tool error,
valid token → the call runs as that user.
"""

import asyncio
import contextlib
import importlib.util
import socket

import pytest

pytestmark = pytest.mark.anyio
if any(importlib.util.find_spec(m) is None for m in ("starlette", "uvicorn", "httpx2")):
    pytest.skip("starlette/uvicorn/httpx2 not installed", allow_module_level=True)

from tests.fakes import CUSTOMER  # noqa: E402
from tests.unit.harness import make_harness  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_streamable_http_with_bearer_auth():
    import httpx2
    import uvicorn
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.routing import Mount

    from app.mcp.gateway import PluginToolGateway
    from app.mcp.server import build_mcp_server

    h, _ = await make_harness()

    async def authenticate(token: str):
        if token != "valid-token":
            raise ValueError("bad token")
        return CUSTOMER

    server = build_mcp_server(PluginToolGateway(h.plugins, h.services_factory()), default_principal=None, authenticate=authenticate)
    mcp_http = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=["127.0.0.1:*"]),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with server.session_manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", app=mcp_http)], lifespan=lifespan)
    port = free_port()
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    task = asyncio.create_task(uv.serve())
    try:
        for _ in range(100):
            if uv.started:
                break
            await asyncio.sleep(0.05)
        url = f"http://127.0.0.1:{port}/mcp/"

        async def call(headers: dict[str, str]):
            async with httpx2.AsyncClient(headers=headers, timeout=10) as http:
                async with Client(streamable_http_client(url, http_client=http)) as client:
                    names = {t.name for t in (await client.list_tools()).tools}
                    return names, await client.call_tool("search_products", {"category": "laptops", "max_price": 60000})

        names, anon = await call({})
        assert len(names) == 11 and anon.is_error and "Authentication required" in anon.content[0].text
        _, bad = await call({"Authorization": "Bearer nope"})
        assert bad.is_error and "Invalid or expired token" in bad.content[0].text
        _, ok = await call({"Authorization": "Bearer valid-token"})
        assert not ok.is_error and ok.structured_content["count"] == 2
    finally:
        uv.should_exit = True
        await task
