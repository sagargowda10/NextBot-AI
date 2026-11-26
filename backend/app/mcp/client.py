"""MCP client connections used by the MCP Integration plugin (official `mcp` SDK `Client`)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters


@dataclass
class McpServerConfig:
    name: str
    transport: str  # "inprocess" | "http" | "stdio"
    url: str | None = None
    command: str | None = None
    allowed_tools: list[str] = field(default_factory=list)  # empty = discovery only, no calls
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> McpServerConfig:
        return cls(
            name=d["name"],
            transport=d.get("transport", "http"),
            url=d.get("url"),
            command=d.get("command"),
            allowed_tools=list(d.get("allowed_tools", [])),
            description=d.get("description", ""),
        )


def _target(cfg: McpServerConfig, inprocess_server: Any | None) -> Any:
    if cfg.transport == "inprocess":
        if inprocess_server is None:
            raise ValueError("In-process MCP server is not available")
        return inprocess_server
    if cfg.transport == "http":
        if not cfg.url:
            raise ValueError(f"MCP server {cfg.name} has no url")
        return cfg.url
    if cfg.transport == "stdio":
        if not cfg.command:
            raise ValueError(f"MCP server {cfg.name} has no command")
        parts = shlex.split(cfg.command)
        return StdioServerParameters(command=parts[0], args=parts[1:])
    raise ValueError(f"Unsupported MCP transport {cfg.transport!r}")


async def list_tools(cfg: McpServerConfig, inprocess_server: Any | None = None, timeout: float = 10.0) -> list[dict[str, Any]]:  # noqa: ASYNC109 - forwarded to the MCP SDK's own timeout
    async with Client(_target(cfg, inprocess_server), read_timeout_seconds=timeout) as client:
        res = await client.list_tools()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in res.tools]


async def call_tool(
    cfg: McpServerConfig,
    tool: str,
    arguments: dict[str, Any],
    inprocess_server: Any | None = None,
    timeout: float = 15.0,  # noqa: ASYNC109 - forwarded to the MCP SDK's own timeout
) -> dict[str, Any]:
    async with Client(_target(cfg, inprocess_server), read_timeout_seconds=timeout) as client:
        res = await client.call_tool(tool, arguments)
        text = " ".join(getattr(c, "text", "") for c in res.content)
        return {"is_error": bool(res.is_error), "structured": res.structured_content, "text": text}
