from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentRunContext, AgentTask
from app.api.deps import get_state
from app.core.exceptions import NotFoundError
from app.core.state import AppState
from app.database.session import get_session
from app.models.ai import Conversation
from app.orchestration.orchestrator import ChatOrchestrator, SessionAgentRecorder
from app.schemas.platform import AgentExecuteRequest, ChatRequest, ChatResponse, ConversationOut
from app.security.dependencies import get_principal, rate_limit, require
from app.security.permissions import Principal
from app.services.container import build_container

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat", "chat_rate_limit_per_minute"))])
async def chat(
    req: ChatRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
    state: AppState = Depends(get_state),
) -> ChatResponse:
    """Send a message to the Supervisor Agent. Works fully offline in demo mode (AI_PROVIDER=mock)."""
    return await ChatOrchestrator(session, state).chat(principal, req)


@router.post("/agent/execute", dependencies=[Depends(require("agents:execute"))])
async def execute_agent(
    req: AgentExecuteRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Admin/debug: run one specialised agent directly with a given intent and params."""
    agent = state.agents.get(req.agent)
    if agent is None or agent is state.agents.supervisor:
        raise NotFoundError(f"Unknown specialised agent {req.agent!r}")
    ctx = AgentRunContext(
        principal=principal,
        services=build_container(session, state),
        plugins=state.plugins,
        metrics=state.metrics,
        recorder=SessionAgentRecorder(session),
        llm=state.llm,
    )
    res = await agent.run(AgentTask(intent=req.intent, params=req.params), ctx)
    return res.model_dump(mode="json")


@router.get("/conversations", response_model=list[ConversationOut])
async def conversations(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)
) -> list[ConversationOut]:
    rows = await ChatOrchestrator(session, state).list_conversations(principal)
    return [
        ConversationOut(id=c.id, title=c.title, channel=c.channel, status=c.status, created_at=c.created_at, updated_at=c.updated_at)
        for c in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def conversation(
    conversation_id: int, principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> ConversationOut:
    c = await session.get(Conversation, conversation_id)
    if c is None or (c.user_id != principal.user_id and not principal.has("support:manage")):
        raise NotFoundError("Conversation not found")
    msgs = [
        {"id": m.id, "role": m.role, "content": m.content, "intent": m.intent, "meta": m.meta, "created_at": m.created_at.isoformat()}
        for m in c.messages
    ]
    return ConversationOut(
        id=c.id, title=c.title, channel=c.channel, status=c.status, created_at=c.created_at, updated_at=c.updated_at, messages=msgs
    )
