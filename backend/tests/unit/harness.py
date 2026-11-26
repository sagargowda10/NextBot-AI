"""Wires the real Supervisor, 11 agents, Plugin Manager and 12 plugins to in-memory services."""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentMetrics, AgentResult, AgentRunContext, AgentTask
from app.agents.registry import AgentRegistry
from app.integrations.llm.mock import MockLLMProvider
from app.mcp.gateway import PluginToolGateway
from app.mcp.server import build_mcp_server
from app.plugins.manager import PluginManager
from app.plugins.registry import builtin_plugins
from app.security.permissions import Principal
from tests.fakes import CUSTOMER, Store, build_services


class Harness:
    def __init__(self) -> None:
        self.services, self.store = build_services()
        self.plugins = PluginManager()
        self.plugins.register_many(builtin_plugins())
        self.agents = AgentRegistry()
        self.metrics = AgentMetrics()
        self.llm = MockLLMProvider()
        self.memory: dict[str, dict[str, Any]] = {}

    async def start(self) -> Harness:
        await self.plugins.initialize_all()
        return self

    def services_factory(self) -> Any:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def factory():  # type: ignore[no-untyped-def]
            yield self.services

        return factory

    def mcp_server(self, principal: Principal | None = CUSTOMER) -> Any:
        gateway = PluginToolGateway(self.plugins, self.services_factory(), {"agent_metrics": self.metrics})
        return build_mcp_server(gateway, default_principal=principal)

    async def chat(self, message: str, principal: Principal = CUSTOMER) -> AgentResult:
        mem = self.memory.setdefault(principal.email, {})
        ctx = AgentRunContext(
            principal=principal,
            services=self.services,
            plugins=self.plugins,
            metrics=self.metrics,
            memory=mem,
            conversation_id=1,
            llm=self.llm,
        )
        return await self.agents.supervisor.run(AgentTask(intent="chat", message=message), ctx)


async def make_harness() -> tuple[Harness, Store]:
    h = await Harness().start()
    return h, h.store
