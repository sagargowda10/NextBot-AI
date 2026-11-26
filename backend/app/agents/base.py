"""Agent framework: typed inputs/outputs, tool allow-lists, iteration & time limits, tracing.

An agent never touches the database directly. Its only way to act on the world is
`run.call(plugin_id, action, payload)`, which goes through the Plugin Manager with the
agent's allow-list attached — so an agent cannot call a tool it was not granted, and the
user's own permissions still apply underneath.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.plugins.base import PluginContext, PluginResult
from app.plugins.manager import PluginManager
from app.security.permissions import Principal
from app.services.contracts import ServiceContainer

log = get_logger("agents")


@dataclass(frozen=True)
class AgentSpec:
    name: str
    display_name: str
    description: str
    tools: frozenset[str]  # "plugin_id.action" or "plugin_id.*"
    max_iterations: int = 6
    timeout_s: float = 15.0
    read_only: bool = True  # read-only agents may run in parallel with each other


class AgentTask(BaseModel):
    intent: str
    params: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class ToolCallRecord(BaseModel):
    plugin: str
    action: str
    success: bool
    duration_ms: float
    error: str | None = None


class AgentResult(BaseModel):
    agent: str = ""
    intent: str = ""
    success: bool = True
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    products: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    requires_approval: bool = False
    halt: bool = False  # tell the supervisor to stop the remaining pipeline
    error: str | None = None
    duration_ms: float = 0.0
    iterations: int = 0


class AgentLimitExceeded(Exception):
    pass


@dataclass
class AgentExecutionRecord:
    id: str
    agent: str
    intent: str
    success: bool
    duration_ms: float
    iterations: int
    tool_calls: int
    error: str | None
    started_at: datetime
    conversation_id: int | None
    user_id: int | None


class AgentRecorder(Protocol):
    async def record(self, rec: AgentExecutionRecord, tools: list[ToolCallRecord]) -> None: ...


class AgentMetrics:
    """In-process ring buffer + counters; the DB holds the durable copy."""

    def __init__(self, history: int = 1000) -> None:
        self.recent: deque[AgentExecutionRecord] = deque(maxlen=history)
        self.counts: dict[str, dict[str, float]] = defaultdict(lambda: {"executions": 0, "successes": 0, "failures": 0, "total_ms": 0.0})

    def add(self, rec: AgentExecutionRecord) -> None:
        self.recent.append(rec)
        c = self.counts[rec.agent]
        c["executions"] += 1
        c["successes" if rec.success else "failures"] += 1
        c["total_ms"] += rec.duration_ms

    def stats(self, agent: str) -> dict[str, float]:
        c = self.counts.get(agent, {"executions": 0, "successes": 0, "failures": 0, "total_ms": 0.0})
        n = c["executions"]
        return {
            "executions": int(n),
            "successes": int(c["successes"]),
            "failures": int(c["failures"]),
            "success_rate": round(c["successes"] / n * 100, 1) if n else 0.0,
            "avg_duration_ms": round(c["total_ms"] / n, 2) if n else 0.0,
        }

    def latest(self, limit: int = 20, agent: str | None = None) -> list[AgentExecutionRecord]:
        recs = [r for r in reversed(self.recent) if agent is None or r.agent == agent]
        return recs[:limit]


@dataclass
class AgentRunContext:
    principal: Principal
    services: ServiceContainer
    plugins: PluginManager
    metrics: AgentMetrics
    memory: dict[str, Any] = field(default_factory=dict)  # conversation working memory (Redis-backed)
    conversation_id: int | None = None
    recorder: AgentRecorder | None = None
    llm: Any = None  # LLMProvider
    extras: dict[str, Any] = field(default_factory=dict)


class AgentRun:
    """Per-execution handle; enforces the iteration budget and records tool calls."""

    def __init__(self, agent: BaseAgent, ctx: AgentRunContext) -> None:
        self.agent = agent
        self.ctx = ctx
        self.iterations = 0
        self.calls: list[ToolCallRecord] = []

    async def call(self, plugin_id: str, action: str, payload: dict[str, Any] | None = None) -> PluginResult:
        spec = self.agent.spec
        self.iterations += 1
        if self.iterations > spec.max_iterations:
            raise AgentLimitExceeded(f"{spec.name} exceeded {spec.max_iterations} tool iterations")
        pctx = PluginContext(
            principal=self.ctx.principal,
            services=self.ctx.services,
            agent=spec.name,
            agent_allowed=spec.tools,
            conversation_id=self.ctx.conversation_id,
            extras={"plugin_manager": self.ctx.plugins, "agent_metrics": self.ctx.metrics, **self.ctx.extras},
        )
        res = await self.ctx.plugins.execute(plugin_id, action, payload, pctx)
        self.calls.append(
            ToolCallRecord(plugin=plugin_id, action=action, success=res.success, duration_ms=res.duration_ms, error=res.error)
        )
        return res


class BaseAgent(ABC):
    spec: AgentSpec

    @property
    def name(self) -> str:
        return self.spec.name

    def can_use(self, plugin_id: str, action: str) -> bool:
        return f"{plugin_id}.{action}" in self.spec.tools or f"{plugin_id}.*" in self.spec.tools

    async def run(self, task: AgentTask, ctx: AgentRunContext) -> AgentResult:
        run = AgentRun(self, ctx)
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(self.handle(task, ctx, run), self.spec.timeout_s)
        except TimeoutError:
            result = AgentResult(
                success=False, summary="That took too long — please try again.", error=f"{self.name} timed out after {self.spec.timeout_s}s"
            )
        except AgentLimitExceeded as exc:
            result = AgentResult(success=False, summary="I couldn't finish that request safely.", error=str(exc))
        except Exception as exc:
            log.exception("agent_failed", extra={"agent": self.name})
            result = AgentResult(success=False, summary="Something went wrong while handling that.", error=f"{type(exc).__name__}: {exc}")
        result.agent = self.name
        result.intent = task.intent
        result.tool_calls = run.calls
        result.iterations = run.iterations
        result.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        rec = AgentExecutionRecord(
            id=uuid.uuid4().hex,
            agent=self.name,
            intent=task.intent,
            success=result.success,
            duration_ms=result.duration_ms,
            iterations=run.iterations,
            tool_calls=len(run.calls),
            error=result.error,
            started_at=started,
            conversation_id=ctx.conversation_id,
            user_id=ctx.principal.user_id,
        )
        ctx.metrics.add(rec)
        if ctx.recorder is not None:
            try:
                await ctx.recorder.record(rec, run.calls)
            except Exception:  # pragma: no cover - tracing must never break the request
                log.warning("agent_trace_persist_failed", extra={"agent": self.name})
        log.info(
            "agent_executed",
            extra={"agent": self.name, "intent": task.intent, "ok": result.success, "ms": result.duration_ms, "tools": len(run.calls)},
        )
        return result

    @abstractmethod
    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult: ...


def fmt_inr(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
    # Indian digit grouping: 1,23,456
    whole, _, frac = s.replace(",", "").partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"₹{whole}" + (f".{frac}" if frac else "")
