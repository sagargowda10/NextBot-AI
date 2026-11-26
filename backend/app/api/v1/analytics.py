from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state
from app.core.state import AppState
from app.database.session import get_session
from app.schemas.platform import DashboardOut, SalesSummary
from app.security.dependencies import require
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])

PERIOD = Query("this month", pattern=r"^(today|yesterday|this week|last week|this month|last month|last 7 days|last 30 days|this year)$")


def svc(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> AnalyticsService:
    return AnalyticsService(session, state)


@router.get("/dashboard", response_model=DashboardOut, dependencies=[Depends(require("analytics:read"))])
async def dashboard(s: AnalyticsService = Depends(svc)) -> DashboardOut:
    return await s.dashboard()


@router.get("/sales", response_model=SalesSummary, dependencies=[Depends(require("analytics:read"))])
async def sales(period: str = PERIOD, s: AnalyticsService = Depends(svc)) -> SalesSummary:
    return await s.sales_summary(period)


@router.get("/products", dependencies=[Depends(require("analytics:read"))])
async def products(limit: int = Query(10, le=100), s: AnalyticsService = Depends(svc)) -> list[dict[str, Any]]:
    return await s.product_performance(limit)


@router.get("/inventory", dependencies=[Depends(require("analytics:inventory"))])
async def inventory(threshold: int = Query(5, ge=0), s: AnalyticsService = Depends(svc)) -> dict[str, Any]:
    return await s.inventory_insights(threshold)
