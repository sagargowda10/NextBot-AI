from __future__ import annotations

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state import AppState
from app.database.session import get_session
from app.schemas.common import PageParams
from app.services.container import build_container
from app.services.contracts import ServiceContainer


def get_state(request: Request) -> AppState:
    return request.app.state.nb  # type: ignore[no-any-return]


def get_services(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> ServiceContainer:
    return build_container(session, state)


def page_params(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> PageParams:
    return PageParams(page=page, size=size)
