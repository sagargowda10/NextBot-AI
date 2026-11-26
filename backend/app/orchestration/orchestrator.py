"""Chat orchestration: authenticated conversation → Supervisor graph → persisted messages + traces."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.base import AgentExecutionRecord, AgentRunContext, AgentTask, ToolCallRecord
from app.core.exceptions import NotFoundError
from app.core.state import AppState
from app.models.ai import AgentExecution, AgentToolExecution, Conversation, ConversationMessage
from app.models.platform import Plugin, PluginExecution
from app.plugins.manager import ExecutionRecord
from app.schemas.platform import AgentStep, ChatRequest, ChatResponse
from app.security.permissions import Principal
from app.services.container import build_container

MEMORY_TTL_S = 2 * 60 * 60
UI_KEYS = ("cart", "order", "payment", "shipment", "return", "estimate", "sales", "top_products", "plugins", "summary", "recent", "risk")


def merge_step_data(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose the structured bits the chat UI renders (cart, order, shipment...)."""
    merged: dict[str, Any] = {}
    for step in steps:
        for k in UI_KEYS:
            if k in (step.get("data") or {}):
                merged[k] = step["data"][k]
    return merged


class SessionAgentRecorder:
    """Writes agent traces into the request's unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, rec: AgentExecutionRecord, tools: list[ToolCallRecord]) -> None:
        self.session.add(
            AgentExecution(
                id=rec.id,
                agent=rec.agent,
                intent=rec.intent,
                success=rec.success,
                duration_ms=rec.duration_ms,
                iterations=rec.iterations,
                tool_calls=rec.tool_calls,
                error=(rec.error or "")[:500] or None,
                conversation_id=rec.conversation_id,
                user_id=rec.user_id,
                started_at=rec.started_at,
                tools=[
                    AgentToolExecution(
                        plugin_id=t.plugin,
                        action=t.action,
                        success=t.success,
                        duration_ms=t.duration_ms,
                        error=(t.error or "")[:500] or None,
                    )
                    for t in tools
                ],
            )
        )


class DbPluginExecutionSink:
    """Buffers plugin execution records and writes them in batches (one short transaction per flush),
    so tracing never competes with the request's own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], max_buffer: int = 5000) -> None:
        self.sessions = sessions
        self.buffer: list[ExecutionRecord] = []
        self.max_buffer = max_buffer

    async def record(self, rec: ExecutionRecord) -> None:
        if len(self.buffer) < self.max_buffer:
            self.buffer.append(rec)

    async def flush(self) -> int:
        batch, self.buffer = self.buffer, []
        if not batch:
            return 0
        async with self.sessions() as s, s.begin():
            for rec in batch:
                s.add(
                    PluginExecution(
                        id=rec.id,
                        plugin_id=rec.plugin_id,
                        action=rec.action,
                        agent=rec.agent,
                        user_id=rec.user_id,
                        conversation_id=rec.conversation_id,
                        success=rec.success,
                        duration_ms=rec.duration_ms,
                        error=(rec.error or "")[:500] or None,
                        started_at=rec.started_at,
                    )
                )
                row = await s.get(Plugin, rec.plugin_id)
                if row is not None:
                    row.executions += 1
                    row.successes += int(rec.success)
                    row.failures += int(not rec.success)
                    row.total_duration_ms += rec.duration_ms
                    row.last_execution_at = rec.started_at
        return len(batch)


class ChatOrchestrator:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def _conversation(self, principal: Principal, req: ChatRequest) -> Conversation:
        if req.conversation_id:
            conv = await self.session.get(Conversation, req.conversation_id)
            if conv is None or conv.user_id != principal.user_id:
                raise NotFoundError("Conversation not found")
            return conv
        conv = Conversation(user_id=principal.user_id, title=req.message[:60], channel=req.channel, messages=[])
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def chat(self, principal: Principal, req: ChatRequest) -> ChatResponse:
        conv = await self._conversation(principal, req)
        history = [{"role": m.role, "content": m.content} for m in conv.messages[-10:]]
        mem_key = f"conv:{conv.id}:memory"
        memory: dict[str, Any] = await self.state.cache.get_json(mem_key) or {}
        ctx = AgentRunContext(
            principal=principal,
            services=build_container(self.session, self.state),
            plugins=self.state.plugins,
            metrics=self.state.metrics,
            memory=memory,
            conversation_id=conv.id,
            recorder=SessionAgentRecorder(self.session),
            llm=self.state.llm,
            extras={"history": history},
        )
        result = await self.state.agents.supervisor.run(AgentTask(intent="chat", message=req.message), ctx)
        intent = result.data.get("intent", "unknown")
        steps = [
            AgentStep(
                agent=s["agent"],
                success=s["success"],
                summary=s["summary"][:300],
                duration_ms=s["duration_ms"],
                tools=[f"{t['plugin']}.{t['action']}" for t in s["tool_calls"]],
            )
            for s in result.data.get("steps", [])
        ]
        self.session.add(ConversationMessage(conversation_id=conv.id, role="user", content=req.message, intent=intent))
        self.session.add(
            ConversationMessage(
                conversation_id=conv.id,
                role="assistant",
                content=result.summary,
                intent=intent,
                meta={
                    "agents": [s.agent for s in steps],
                    "products": [p["id"] for p in result.products],
                    "sources": [s.get("id") for s in result.sources],
                },
            )
        )
        await self.state.cache.set_json(mem_key, memory, MEMORY_TTL_S)
        await self.state.traces.save_turn(
            {
                "conversation_id": conv.id,
                "user_id": principal.user_id,
                "message": req.message,
                "intent": intent,
                "entities": result.data.get("entities", {}),
                "steps": [s.model_dump() for s in steps],
                "blocked": result.data.get("blocked", False),
            }
        )
        return ChatResponse(
            conversation_id=conv.id,
            reply=result.summary,
            intent=intent,
            products=result.products,
            agents=steps,
            sources=result.sources,
            suggestions=result.suggestions,
            requires_approval=result.requires_approval,
            data=merge_step_data(result.data.get("steps", [])),
            demo_mode=bool(self.state.settings.demo_mode),
            ai_provider=getattr(self.state.llm, "name", "mock"),
        )

    async def list_conversations(self, principal: Principal) -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.user_id == principal.user_id).order_by(Conversation.updated_at.desc()).limit(30)
        return list((await self.session.scalars(stmt)).all())
