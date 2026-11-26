"""Bridges MCP tool calls to the Plugin Manager with a fresh service container per call."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from app.plugins.base import PluginContext, PluginResult
from app.plugins.manager import PluginManager
from app.security.permissions import Principal
from app.services.contracts import ServiceContainer

ServicesFactory = Callable[[], AbstractAsyncContextManager[ServiceContainer]]


class PluginToolGateway:
    def __init__(self, plugins: PluginManager, services_factory: ServicesFactory, extras: dict[str, Any] | None = None):
        self.plugins = plugins
        self.services_factory = services_factory
        self.extras = extras or {}

    async def call(self, plugin_id: str, action: str, payload: dict[str, Any], principal: Principal) -> PluginResult:
        async with self.services_factory() as services:
            ctx = PluginContext(
                principal=principal, services=services, agent="mcp_client", extras={"plugin_manager": self.plugins, **self.extras}
            )
            return await self.plugins.execute(plugin_id, action, payload, ctx)
