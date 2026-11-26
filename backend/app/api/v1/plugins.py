from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state
from app.core.state import AppState
from app.database.session import get_session
from app.models.platform import PluginConfiguration
from app.plugins.manager import PluginManager, PluginRegistration
from app.schemas.platform import PluginActionInfo, PluginConfigUpdate, PluginExecutionOut, PluginOut, PluginStatsOut
from app.security.dependencies import require
from app.security.permissions import Principal
from app.services.audit_service import audit

router = APIRouter(prefix="/plugins", tags=["Plugins"])
admin = Depends(require("plugins:manage"))


def plugin_out(reg: PluginRegistration) -> PluginOut:
    p, s = reg.plugin, reg.stats
    return PluginOut(
        id=p.plugin_id,
        name=p.name,
        version=p.version,
        description=p.description,
        status=reg.status.value,
        health=("HEALTHY" if reg.health and reg.health.healthy else "UNHEALTHY") if reg.health else "UNKNOWN",
        requires_credentials=bool(p.requires_credentials),
        mode=p.mode,
        registered_at=reg.registered_at,
        actions=[PluginActionInfo(name=a.name, description=a.description, permission=a.permission) for a in p.actions().values()],
        stats=PluginStatsOut(
            executions=s.executions,
            successes=s.successes,
            failures=s.failures,
            avg_duration_ms=s.avg_duration_ms,
            last_execution_at=s.last_execution_at,
            last_error=s.last_error,
        ),
        config=PluginManager.masked_config(reg),
    )


@router.get("", response_model=list[PluginOut], dependencies=[admin])
async def list_plugins(state: AppState = Depends(get_state)) -> list[PluginOut]:
    return [plugin_out(r) for r in state.plugins.list()]


@router.get("/summary", dependencies=[admin])
async def summary(state: AppState = Depends(get_state)) -> dict:
    return state.plugins.summary()


@router.get("/{plugin_id}", response_model=PluginOut, dependencies=[admin])
async def get_plugin(plugin_id: str, state: AppState = Depends(get_state)) -> PluginOut:
    reg = state.plugins.get(plugin_id)
    await state.plugins.health(plugin_id)
    return plugin_out(reg)


@router.post("/{plugin_id}/enable", response_model=PluginOut)
async def enable(
    plugin_id: str,
    principal: Principal = Depends(require("plugins:manage")),
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    reg = await state.plugins.enable(plugin_id)
    await audit(session, principal, "plugin.enable", "plugin", plugin_id, {"status": reg.status.value})
    await _persist_status(session, reg)
    return plugin_out(reg)


@router.post("/{plugin_id}/disable", response_model=PluginOut)
async def disable(
    plugin_id: str,
    principal: Principal = Depends(require("plugins:manage")),
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    reg = await state.plugins.disable(plugin_id)
    await audit(session, principal, "plugin.disable", "plugin", plugin_id)
    await _persist_status(session, reg)
    return plugin_out(reg)


@router.put("/{plugin_id}/config", response_model=PluginOut)
async def configure(
    plugin_id: str,
    body: PluginConfigUpdate,
    principal: Principal = Depends(require("plugins:manage")),
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    """Update non-secret settings. Secret keys are rejected — set them as environment variables."""
    reg = await state.plugins.configure(plugin_id, body.values)
    row = await session.scalar(select(PluginConfiguration).where(PluginConfiguration.plugin_id == plugin_id))
    if row is None:
        row = PluginConfiguration(plugin_id=plugin_id, values={})
        session.add(row)
    row.values = {**(row.values or {}), **body.values}
    row.updated_by = principal.user_id
    await audit(session, principal, "plugin.configure", "plugin", plugin_id, {"keys": sorted(body.values)})
    return plugin_out(reg)


@router.get("/{plugin_id}/executions", response_model=list[PluginExecutionOut], dependencies=[admin])
async def executions(
    plugin_id: str, failed_only: bool = False, limit: int = Query(50, le=200), state: AppState = Depends(get_state)
) -> list[PluginExecutionOut]:
    state.plugins.get(plugin_id)  # 404 if unknown
    return [
        PluginExecutionOut(
            id=r.id,
            plugin_id=r.plugin_id,
            action=r.action,
            agent=r.agent,
            user_id=r.user_id,
            success=r.success,
            duration_ms=r.duration_ms,
            error=r.error,
            started_at=r.started_at,
        )
        for r in state.plugins.executions(plugin_id, limit, failed_only)
    ]


async def _persist_status(session: AsyncSession, reg: PluginRegistration) -> None:
    from app.models.platform import Plugin

    row = await session.get(Plugin, reg.plugin.plugin_id)
    if row is not None:
        row.status, row.desired_enabled = reg.status.value, reg.desired_enabled
