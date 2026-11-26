"""DTOs for auth, users, plugins, agents, approvals, analytics, notifications, AI chat."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.schemas.common import DTO


# ---------- Plugins ----------
class PluginActionInfo(DTO):
    name: str
    description: str
    permission: str


class PluginStatsOut(DTO):
    executions: int = 0
    successes: int = 0
    failures: int = 0
    avg_duration_ms: float = 0.0
    last_execution_at: datetime | None = None
    last_error: str | None = None


class PluginOut(DTO):
    id: str
    name: str
    version: str
    description: str
    status: str
    health: str
    requires_credentials: bool = False
    mode: str = "local"
    registered_at: datetime | None = None
    actions: list[PluginActionInfo] = []
    stats: PluginStatsOut = PluginStatsOut()
    config: dict[str, Any] = {}  # secrets are masked


class PluginConfigUpdate(DTO):
    values: dict[str, Any]


class PluginExecutionOut(DTO):
    id: str
    plugin_id: str
    action: str
    agent: str | None = None
    user_id: int | None = None
    success: bool
    duration_ms: float
    error: str | None = None
    started_at: datetime


# ---------- Agents ----------
class AgentInfoOut(DTO):
    name: str
    display_name: str
    description: str
    is_supervisor: bool = False
    allowed_tools: list[str] = []
    max_iterations: int
    timeout_s: float
    status: str = "READY"
    executions: int = 0
    successes: int = 0
    failures: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0


class AgentExecutionOut(DTO):
    id: str
    agent: str
    intent: str | None = None
    success: bool
    duration_ms: float
    iterations: int = 0
    tool_calls: int = 0
    error: str | None = None
    conversation_id: int | None = None
    started_at: datetime


# ---------- AI chat ----------
class ChatRequest(DTO):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    channel: str = Field("WEB", pattern=r"^(WEB|MOBILE|WHATSAPP|EMAIL|VOICE)$")


class AgentStep(DTO):
    agent: str
    success: bool
    summary: str
    duration_ms: float
    tools: list[str] = []


class ChatResponse(DTO):
    conversation_id: int
    reply: str
    intent: str
    products: list[dict[str, Any]] = []
    data: dict[str, Any] = {}
    agents: list[AgentStep] = []
    sources: list[dict[str, Any]] = []
    suggestions: list[str] = []
    demo_mode: bool = True
    ai_provider: str = "mock"
    requires_approval: bool = False


class AgentExecuteRequest(DTO):
    agent: str
    intent: str
    params: dict[str, Any] = {}


class ConversationOut(DTO):
    id: int
    title: str
    channel: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    messages: list[dict[str, Any]] = []


# ---------- Approvals ----------
class ApprovalOut(DTO):
    id: int
    action: str
    status: str
    summary: str
    payload: dict[str, Any] = {}
    requested_by_agent: str | None = None
    requested_for_user_id: int | None = None
    reviewer_id: int | None = None
    review_note: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ApprovalDecision(DTO):
    approve: bool
    note: str | None = Field(None, max_length=500)


# ---------- Notifications ----------
class NotificationOut(DTO):
    id: int
    user_id: int | None
    channel: str
    template: str
    recipient: str
    subject: str | None = None
    body: str
    status: str
    created_at: datetime


# ---------- Analytics ----------
class SalesSummary(DTO):
    period: str
    start: datetime
    end: datetime
    revenue: Decimal
    orders: int
    average_order_value: Decimal
    by_day: list[dict[str, Any]] = []


class DashboardOut(DTO):
    revenue_30d: Decimal
    orders_30d: int
    customers: int
    products: int
    low_stock_items: int
    open_returns: int
    pending_approvals: int
    plugins_enabled: int
    plugins_total: int
    agent_executions_24h: int
    agent_success_rate: float
    top_products: list[dict[str, Any]] = []
    sales_by_day: list[dict[str, Any]] = []
    orders_by_status: dict[str, int] = {}


class GroundedAnswer(DTO):
    answer: str
    sources: list[dict[str, Any]] = []
    grounded: bool = True
    max_score: float = 0.0
