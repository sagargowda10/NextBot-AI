from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalStatus, ReturnStatus, Role
from app.core.state import AppState
from app.models.ai import AgentExecution
from app.models.catalog import Product, ProductVariant
from app.models.commerce import Order, OrderItem, ReturnRequest
from app.models.inventory import Inventory
from app.models.platform import ApprovalRequest
from app.models.user import Role as RoleModel
from app.models.user import User, user_roles
from app.schemas.platform import DashboardOut, SalesSummary
from app.services.order_service import PAID_STATUSES


def period_range(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    match period:
        case "today":
            return day, now
        case "yesterday":
            return day - timedelta(days=1), day
        case "this week":
            return day - timedelta(days=day.weekday()), now
        case "last week":
            start = day - timedelta(days=day.weekday() + 7)
            return start, start + timedelta(days=7)
        case "last month":
            prev = (month - timedelta(days=1)).replace(day=1)
            return prev, month
        case "last 7 days":
            return now - timedelta(days=7), now
        case "last 30 days":
            return now - timedelta(days=30), now
        case "this year":
            return day.replace(month=1, day=1), now
    return month, now


class AnalyticsService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def _paid_orders(self, start: datetime, end: datetime) -> list[Order]:
        stmt = select(Order).where(Order.status.in_(PAID_STATUSES), Order.confirmed_at >= start, Order.confirmed_at < end)
        return list((await self.session.scalars(stmt)).all())

    async def sales_summary(self, period: str) -> SalesSummary:
        start, end = period_range(period)
        orders = await self._paid_orders(start, end)
        revenue = sum((o.total for o in orders), Decimal("0"))
        by_day: dict[str, list[Decimal]] = defaultdict(list)
        for o in orders:
            by_day[(o.confirmed_at or o.created_at).date().isoformat()].append(o.total)
        series = [{"date": d, "revenue": str(sum(v, Decimal("0"))), "orders": len(v)} for d, v in sorted(by_day.items())]
        aov = (revenue / len(orders)).quantize(Decimal("0.01")) if orders else Decimal("0")
        return SalesSummary(
            period=period, start=start, end=end, revenue=revenue, orders=len(orders), average_order_value=aov, by_day=series
        )

    async def product_performance(self, limit: int) -> list[dict[str, Any]]:
        stmt = (
            select(OrderItem.product_id, OrderItem.product_name, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total))
            .join(Order)
            .where(Order.status.in_(PAID_STATUSES))
            .group_by(OrderItem.product_id, OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        return [
            {"product_id": pid, "name": name, "units": int(u or 0), "revenue": str(r or 0)}
            for pid, name, u, r in (await self.session.execute(stmt)).all()
        ]

    async def inventory_insights(self, threshold: int) -> dict[str, Any]:
        rows = (
            await self.session.execute(
                select(Inventory.quantity, Inventory.reserved, Product.price)
                .join(ProductVariant, Inventory.variant_id == ProductVariant.id)
                .join(Product, ProductVariant.product_id == Product.id)
            )
        ).all()
        units = sum(q for q, _, _ in rows)
        value = sum((Decimal(q) * p for q, _, p in rows), Decimal("0"))
        return {
            "sku_locations": len(rows),
            "units_on_hand": units,
            "units_reserved": sum(r for _, r, _ in rows),
            "stock_value": str(value),
            "low_stock": sum(1 for q, r, _ in rows if 0 < q - r <= threshold),
            "out_of_stock": sum(1 for q, r, _ in rows if q - r <= 0),
        }

    async def order_stats(self) -> dict[str, Any]:
        rows = (await self.session.execute(select(Order.status, func.count()).group_by(Order.status))).all()
        by_status = {s: int(n) for s, n in rows}
        return {"total": sum(by_status.values()), "by_status": by_status}

    async def dashboard(self) -> DashboardOut:
        now = datetime.now(UTC)
        month = await self.sales_summary("last 30 days")
        customers = await self.session.scalar(
            select(func.count()).select_from(User).join(user_roles).join(RoleModel).where(RoleModel.name == Role.CUSTOMER)
        )
        inv = await self.inventory_insights(int(getattr(self.state.settings, "low_stock_threshold", 5)))
        open_returns = await self.session.scalar(
            select(func.count())
            .select_from(ReturnRequest)
            .where(ReturnRequest.status.in_([ReturnStatus.REQUESTED, ReturnStatus.PENDING_APPROVAL, ReturnStatus.APPROVED]))
        )
        pending = await self.session.scalar(
            select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == ApprovalStatus.PENDING)
        )
        execs = (
            await self.session.execute(
                select(func.count(), func.sum(case((AgentExecution.success.is_(True), 1), else_=0))).where(
                    AgentExecution.started_at >= now - timedelta(hours=24)
                )
            )
        ).one()
        total_execs, ok_execs = int(execs[0] or 0), int(execs[1] or 0)
        summary = self.state.plugins.summary()
        return DashboardOut(
            revenue_30d=month.revenue,
            orders_30d=month.orders,
            customers=int(customers or 0),
            products=int(await self.session.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))) or 0),
            low_stock_items=inv["low_stock"],
            open_returns=int(open_returns or 0),
            pending_approvals=int(pending or 0),
            plugins_enabled=summary["enabled"],
            plugins_total=summary["total"],
            agent_executions_24h=total_execs,
            agent_success_rate=round(ok_execs / total_execs * 100, 1) if total_execs else 0.0,
            top_products=await self.product_performance(5),
            sales_by_day=month.by_day,
            orders_by_status=(await self.order_stats())["by_status"],
        )
