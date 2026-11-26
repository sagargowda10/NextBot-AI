"""Builds the per-request ServiceContainer (one DB session = one unit of work)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state import AppState
from app.database.session import session_factory
from app.services.analytics_service import AnalyticsService
from app.services.approval_service import ApprovalService
from app.services.cart_service import CartService
from app.services.catalog_service import ProductService, RecommendationService
from app.services.contracts import ServiceContainer
from app.services.inventory_service import InventoryService
from app.services.notification_service import NotificationService
from app.services.order_service import OrderService, RiskDataService
from app.services.payment_service import PaymentService
from app.services.return_service import ReturnService
from app.services.shipment_service import ShipmentService
from app.services.support_service import SupportService


def build_container(session: AsyncSession, state: AppState) -> ServiceContainer:
    return ServiceContainer(
        products=ProductService(session, state),
        recommendations=RecommendationService(session, state),
        inventory=InventoryService(session, state),
        cart=CartService(session, state),
        orders=OrderService(session, state),
        payments=PaymentService(session, state),
        shipments=ShipmentService(session, state),
        returns=ReturnService(session, state),
        support=SupportService(session, state),
        notifications=NotificationService(session, state),
        analytics=AnalyticsService(session, state),
        risk=RiskDataService(session, state),
        approvals=ApprovalService(session, state),
    )


def container_factory(state: AppState):  # type: ignore[no-untyped-def]
    """Async context manager factory used by MCP and event consumers (each call = own transaction)."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[ServiceContainer]:
        async with session_factory()() as session:
            try:
                yield build_container(session, state)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return factory
