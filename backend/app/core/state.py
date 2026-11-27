"""Process-wide singletons, created once in the FastAPI lifespan and stored on `app.state.nb`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agents.base import AgentMetrics
from app.agents.registry import AgentRegistry
from app.domain.approvals import ApprovalPolicy
from app.events.bus import EventBus
from app.integrations.cache import Cache
from app.integrations.mongo import TraceStore
from app.integrations.payments import PaymentGateway
from app.integrations.shipping import Courier
from app.plugins.manager import PluginManager
from app.rag.pipeline import RagPipeline


@dataclass
class AppState:
    settings: Any
    plugins: PluginManager
    agents: AgentRegistry
    metrics: AgentMetrics
    llm: Any
    rag: RagPipeline
    bus: EventBus
    cache: Cache
    traces: TraceStore
    gateway: PaymentGateway
    courier: Courier
    policy: ApprovalPolicy
    search_index: Any | None = None
    mcp_server: Any | None = None
    n8n: Any | None = None  # N8nForwarder when n8n_webhook_url is configured
    research: Any | None = None  # OpenAIResearchClient when an OpenAI key is configured
    background: list[Any] = field(default_factory=list)
