"""Inventory: availability, oversell-safe reservation/release/commit, adjustments with approval."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalAction
from app.core.exceptions import NotFoundError, OutOfStockError
from app.core.state import AppState
from app.events.outbox import add_event
from app.events.schemas import EventType
from app.models.commerce import Order
from app.models.inventory import Inventory
from app.repositories.inventory import InventoryRepository
from app.schemas.commerce import InventoryAdjustResult, StockLevel
from app.security.permissions import Principal
from app.services.audit_service import audit
from app.services.mappers import stock_level


class InventoryService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.repo = InventoryRepository(session)
        self.threshold = int(getattr(state.settings, "low_stock_threshold", 5))

    async def availability(self, variant_ids: list[int]) -> list[StockLevel]:
        return [stock_level(r, self.threshold) for r in await self.repo.rows_for_variants(variant_ids)]

    async def for_products(self, product_ids: list[int]) -> list[StockLevel]:
        return [stock_level(r, self.threshold) for r in await self.repo.rows_for_products(product_ids)]

    async def low_stock(self, threshold: int) -> list[StockLevel]:
        return [stock_level(r, threshold) for r in await self.repo.low_stock(threshold)]

    async def all_levels(self, offset: int = 0, limit: int = 50) -> list[StockLevel]:
        rows = (await self.session.scalars(select(Inventory).order_by(Inventory.id).offset(offset).limit(limit))).all()
        return [stock_level(r, self.threshold) for r in rows]

    async def adjust(self, principal: Principal, inventory_id: int, delta: int, reason: str) -> InventoryAdjustResult:
        inv = await self.session.get(Inventory, inventory_id)
        if inv is None:
            raise NotFoundError(f"Inventory row {inventory_id} not found")
        if self.state.policy.inventory_adjustment_needs_approval(delta):
            from app.services.approval_service import ApprovalService

            aid = await ApprovalService(self.session, self.state).create(
                action=ApprovalAction.INVENTORY_ADJUSTMENT,
                summary=f"Adjust {inv.variant.sku} by {delta:+d}: {reason}",
                payload={"inventory_id": inventory_id, "delta": delta, "reason": reason},
                agent=None,
                user_id=principal.user_id,
            )
            return InventoryAdjustResult(applied=False, approval_request_id=aid, message="Large adjustment sent for approval")
        return await self.apply_adjustment(principal, inventory_id, delta, reason)

    async def apply_adjustment(self, principal: Principal, inventory_id: int, delta: int, reason: str) -> InventoryAdjustResult:
        inv = await self.session.get(Inventory, inventory_id, with_for_update=True)
        if inv is None:
            raise NotFoundError(f"Inventory row {inventory_id} not found")
        if inv.quantity + delta < inv.reserved:
            raise OutOfStockError("Adjustment would drop stock below reserved units")
        inv.quantity += delta
        await self.session.flush()
        await audit(self.session, principal, "inventory.adjust", "inventory", inventory_id, {"delta": delta, "reason": reason})
        return InventoryAdjustResult(applied=True, stock=stock_level(inv, self.threshold), message="Stock updated")

    async def reserve_for_order(self, order_id: int) -> bool:
        """Reserve every line, choosing warehouses by priority. All-or-nothing within the transaction."""
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("Order not found")
        for item in order.items:
            remaining = item.quantity
            for row in await self.repo.rows_for_variants([item.variant_id]):
                if row.quantity - row.reserved >= remaining and await self.repo.try_reserve(row.id, remaining):
                    item.warehouse_id = row.warehouse_id
                    remaining = 0
                    break
            if remaining:
                raise OutOfStockError(f"{item.product_name} ({item.sku}) just went out of stock", details={"variant_id": item.variant_id})
        add_event(
            self.session,
            EventType.INVENTORY_RESERVED,
            "order",
            order.id,
            {"items": [{"variant_id": i.variant_id, "qty": i.quantity, "warehouse_id": i.warehouse_id} for i in order.items]},
        )
        return True

    async def release_for_order(self, order_id: int) -> bool:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("Order not found")
        for item in order.items:
            if item.warehouse_id is not None:
                await self.repo.release(item.variant_id, item.warehouse_id, item.quantity)
        add_event(self.session, EventType.INVENTORY_RELEASED, "order", order.id, {"reason": "released"})
        return True

    async def commit_for_order(self, order: Order) -> None:
        for item in order.items:
            if item.warehouse_id is not None:
                await self.repo.commit_sale(item.variant_id, item.warehouse_id, item.quantity)

    async def restock_for_order(self, order: Order) -> None:
        for item in order.items:
            if item.warehouse_id is not None:
                await self.repo.restock(item.variant_id, item.warehouse_id, item.quantity)
