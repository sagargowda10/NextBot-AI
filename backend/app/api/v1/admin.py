from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state, page_params
from app.api.v1.plugins import plugin_out
from app.core.state import AppState
from app.database.session import get_session
from app.models.ai import AgentExecution
from app.models.platform import AuditLog
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.commerce import OrderOut
from app.schemas.common import Page, PageParams
from app.schemas.platform import AgentExecutionOut, AgentInfoOut, ApprovalDecision, ApprovalOut, NotificationOut, PluginOut
from app.security.dependencies import get_principal, rate_limit, require
from app.security.permissions import Principal
from app.services.approval_service import ApprovalService
from app.services.auth_service import user_out
from app.services.notification_service import NotificationService
from app.services.order_service import OrderService
from app.services.research_service import ResearchService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/admin", tags=["Administration"])
staff = Depends(require("admin:read"))


@router.get("/users", response_model=Page[UserOut], dependencies=[staff])
async def users(p: PageParams = Depends(page_params), session: AsyncSession = Depends(get_session)) -> Page[UserOut]:
    rows = (await session.scalars(select(User).order_by(User.id).offset(p.offset).limit(p.size))).all()
    total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    return Page(items=[user_out(u) for u in rows], total=total, page=p.page, size=p.size)


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ResearchRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    use_web: bool = True
    include_store: str = Field("auto", pattern="^(auto|always|never)$")
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


@router.get("/research/status", dependencies=[Depends(require("research:use"))])
async def research_status(state: AppState = Depends(get_state)) -> dict[str, Any]:
    s = state.settings
    return {
        "provider": state.research.name if state.research else "mock",
        "model": state.research.model if state.research else None,
        "daily_limit": s.research_daily_limit,
        "per_minute": s.research_rate_limit_per_minute,
    }


@router.post(
    "/research",
    dependencies=[Depends(require("research:use")), Depends(rate_limit("research", "research_rate_limit_per_minute"))],
)
async def research(
    body: ResearchRequest,
    principal: Principal = Depends(get_principal),
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Admin-only AI research: ChatGPT with live web search + citations, optionally grounded in store analytics."""
    history = [t.model_dump() for t in body.history]
    return await ResearchService(session, state).ask(principal, body.question.strip(), history, body.use_web, body.include_store)


@router.get("/workflows/n8n", dependencies=[Depends(require("order:read_all"))])
async def n8n_status(state: AppState = Depends(get_state), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Is the n8n integration configured, and how have deliveries gone since the backend started?"""
    svc = WorkflowService(session, state.n8n, state.settings.n8n_editor_url)
    recent = [d.__dict__ for d in list(state.n8n.recent)[:20]] if state.n8n else []
    return {**svc.n8n_status(), "recent": recent}


@router.get("/orders/{order_id}/workflow", dependencies=[Depends(require("order:read_all"))])
async def order_workflow(
    order_id: int, state: AppState = Depends(get_state), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """n8n-style execution trace of one order: agents, payment, events, courier, notifications, returns, approvals."""
    return await WorkflowService(session, state.n8n, state.settings.n8n_editor_url).for_order(order_id)


@router.get("/orders", response_model=Page[OrderOut], dependencies=[Depends(require("order:read_all"))])
async def all_orders(
    status: str | None = None,
    p: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_session),
    state: AppState = Depends(get_state),
) -> Page[OrderOut]:
    items, total = await OrderService(session, state).list_all(p.offset, p.size, status)
    return Page(items=items, total=total, page=p.page, size=p.size)


@router.get("/agents", response_model=list[AgentInfoOut], dependencies=[staff])
async def agents(state: AppState = Depends(get_state)) -> list[AgentInfoOut]:
    out = []
    for a in state.agents.all():
        s = state.metrics.stats(a.name)
        out.append(
            AgentInfoOut(
                name=a.name,
                display_name=a.spec.display_name,
                description=a.spec.description,
                is_supervisor=a is state.agents.supervisor,
                allowed_tools=sorted(a.spec.tools),
                max_iterations=a.spec.max_iterations,
                timeout_s=a.spec.timeout_s,
                **s,
            )
        )  # type: ignore[arg-type]
    return out


@router.get("/agents/executions", response_model=list[AgentExecutionOut], dependencies=[staff])
async def agent_executions(
    agent: str | None = None, limit: int = Query(50, le=200), session: AsyncSession = Depends(get_session)
) -> list[AgentExecutionOut]:
    stmt = select(AgentExecution).order_by(AgentExecution.started_at.desc()).limit(limit)
    if agent:
        stmt = stmt.where(AgentExecution.agent == agent)
    return [
        AgentExecutionOut(
            id=e.id,
            agent=e.agent,
            intent=e.intent,
            success=e.success,
            duration_ms=e.duration_ms,
            iterations=e.iterations,
            tool_calls=e.tool_calls,
            error=e.error,
            conversation_id=e.conversation_id,
            started_at=e.started_at,
        )
        for e in (await session.scalars(stmt)).all()
    ]


@router.get("/plugins", response_model=list[PluginOut], dependencies=[staff])
async def plugins(state: AppState = Depends(get_state)) -> list[PluginOut]:
    return [plugin_out(r) for r in state.plugins.list()]


@router.get("/approvals", response_model=list[ApprovalOut], dependencies=[Depends(require("approvals:review"))])
async def approvals(
    status: str | None = Query(None, pattern="^(PENDING|APPROVED|REJECTED|EXECUTED|FAILED)$"),
    session: AsyncSession = Depends(get_session),
    state: AppState = Depends(get_state),
) -> list[ApprovalOut]:
    return await ApprovalService(session, state).list(status)


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
async def decide(
    approval_id: int,
    body: ApprovalDecision,
    principal: Principal = Depends(require("approvals:review")),
    session: AsyncSession = Depends(get_session),
    state: AppState = Depends(get_state),
) -> ApprovalOut:
    return await ApprovalService(session, state).decide(principal, approval_id, body.approve, body.note)


@router.get("/notifications", response_model=list[NotificationOut], dependencies=[Depends(require("support:manage"))])
async def notifications(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> list[NotificationOut]:
    return await NotificationService(session, state).for_user(None)


@router.get("/audit", dependencies=[staff])
async def audit_log(limit: int = Query(100, le=500), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))).all()
    return [
        {
            "id": r.id,
            "actor": r.actor_email,
            "action": r.action,
            "resource": f"{r.resource_type}:{r.resource_id}",
            "details": r.details,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/traces", dependencies=[staff])
async def traces(limit: int = Query(20, le=100), state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    return await state.traces.recent(None, limit)
