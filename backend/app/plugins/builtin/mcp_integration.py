"""Plugin 12 — MCP Integration: discover and call tools on MCP servers with an allow-list.

Uses the official MCP SDK client over real protocol transports (in-process memory streams,
Streamable HTTP or stdio). By default it is wired to NextBot's own MCP server, which makes the
protocol round-trip demonstrable without any external service.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError, PermissionDenied, ValidationFailed
from app.mcp import client as mcp_client
from app.mcp.client import McpServerConfig
from app.plugins.base import BasePlugin, HealthStatus, NoInput, PluginContext, action


class ServerIn(BaseModel):
    server: str = Field(min_length=1, max_length=60)


class CallIn(BaseModel):
    server: str = Field(min_length=1, max_length=60)
    tool: str = Field(pattern=r"^[a-zA-Z0-9_\-]{1,64}$")
    arguments: dict[str, Any] = {}


class McpIntegrationPlugin(BasePlugin):
    plugin_id = "mcp_integration"
    name = "MCP Integration"
    version = "1.0.0"
    description = "Model Context Protocol client: external tool discovery and permission-checked tool execution."
    default_config: dict[str, Any] = {
        "servers": [
            {
                "name": "nextbot",
                "transport": "inprocess",
                "description": "NextBot's own MCP server",
                "allowed_tools": ["search_products", "get_product_details", "check_inventory", "get_sales_summary"],
            },
        ],
        "timeout_s": 10,
    }

    def __init__(self) -> None:
        super().__init__()
        self.inprocess_server: Any | None = None  # set by the app factory

    def validate_configuration(self, config: dict) -> list[str]:
        errors = []
        for s in config.get("servers", []):
            if s.get("transport") not in ("inprocess", "http", "stdio"):
                errors.append(f"server {s.get('name')}: transport must be inprocess, http or stdio")
        return errors

    def _server(self, name: str) -> McpServerConfig:
        for s in self.config.get("servers", []):
            if s.get("name") == name:
                return McpServerConfig.from_dict(s)
        raise NotFoundError(f"MCP server {name!r} is not configured")

    async def health_check(self) -> HealthStatus:
        n = len(self.config.get("servers", []))
        return HealthStatus(healthy=True, detail=f"{n} MCP server(s) configured")

    @action("list_servers", NoInput, "mcp:use", "Configured MCP servers and their tool allow-lists")
    async def list_servers(self, p: NoInput, ctx: PluginContext) -> dict:
        return {
            "servers": [
                {
                    "name": s["name"],
                    "transport": s.get("transport"),
                    "allowed_tools": s.get("allowed_tools", []),
                    "description": s.get("description", ""),
                }
                for s in self.config.get("servers", [])
            ]
        }

    @action("discover_tools", ServerIn, "mcp:use", "List tools exposed by an MCP server (tools/list)")
    async def discover_tools(self, p: ServerIn, ctx: PluginContext) -> dict:
        cfg = self._server(p.server)
        tools = await mcp_client.list_tools(cfg, self.inprocess_server, float(self.config.get("timeout_s", 10)))
        for t in tools:
            t["allowed"] = t["name"] in cfg.allowed_tools
        return {"server": cfg.name, "tools": tools}

    @action("call_tool", CallIn, "mcp:use", "Call an allow-listed tool on an MCP server (tools/call)")
    async def call_tool(self, p: CallIn, ctx: PluginContext) -> dict:
        cfg = self._server(p.server)
        if p.tool not in cfg.allowed_tools:
            raise PermissionDenied(f"Tool {p.tool!r} is not allow-listed for MCP server {cfg.name!r}")
        res = await mcp_client.call_tool(cfg, p.tool, p.arguments, self.inprocess_server, float(self.config.get("timeout_s", 10)))
        if res["is_error"]:
            raise ValidationFailed(f"MCP tool error: {res['text']}")
        return {"server": cfg.name, "tool": p.tool, "result": res["structured"], "text": res["text"]}
