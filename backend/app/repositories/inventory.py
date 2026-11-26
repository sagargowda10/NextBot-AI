"""Inventory persistence with atomic, oversell-proof stock operations."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import ProductVariant
from app.models.inventory import Inventory, Warehouse


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rows_for_variants(self, variant_ids: list[int]) -> list[Inventory]:
        if not variant_ids:
            return []
        stmt = (
            select(Inventory)
            .join(Warehouse)
            .where(Inventory.variant_id.in_(variant_ids))
            .order_by(Inventory.variant_id, Warehouse.priority)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.scalars(stmt)).all())

    async def rows_for_products(self, product_ids: list[int]) -> list[Inventory]:
        stmt = (
            select(Inventory)
            .join(ProductVariant, Inventory.variant_id == ProductVariant.id)
            .where(ProductVariant.product_id.in_(product_ids))
            .order_by(ProductVariant.product_id, Inventory.variant_id)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.scalars(stmt)).all())

    async def available_by_variant(self, variant_ids: list[int]) -> dict[int, int]:
        if not variant_ids:
            return {}
        stmt = (
            select(Inventory.variant_id, func.sum(Inventory.quantity - Inventory.reserved))
            .where(Inventory.variant_id.in_(variant_ids))
            .group_by(Inventory.variant_id)
        )
        out: dict[int, int] = defaultdict(int)
        for vid, avail in (await self.session.execute(stmt)).all():
            out[int(vid)] = int(avail or 0)
        return out

    async def low_stock(self, threshold: int) -> list[Inventory]:
        stmt = (
            select(Inventory)
            .where(Inventory.quantity - Inventory.reserved <= threshold)
            .order_by((Inventory.quantity - Inventory.reserved).asc())
            .limit(100)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.scalars(stmt)).all())

    async def try_reserve(self, inventory_id: int, qty: int) -> bool:
        """Atomic conditional UPDATE: succeeds only if enough unreserved stock exists right now.

        Two concurrent checkouts for the last unit both issue this statement; the database
        serialises the row update, so exactly one sees rowcount == 1.
        """
        res = await self.session.execute(
            update(Inventory)
            .where(Inventory.id == inventory_id, Inventory.quantity - Inventory.reserved >= qty)
            .values(reserved=Inventory.reserved + qty)
            .execution_options(synchronize_session=False)
        )
        return bool(res.rowcount == 1)  # type: ignore[attr-defined]

    async def release(self, variant_id: int, warehouse_id: int, qty: int) -> None:
        await self.session.execute(
            update(Inventory)
            .where(Inventory.variant_id == variant_id, Inventory.warehouse_id == warehouse_id, Inventory.reserved >= qty)
            .values(reserved=Inventory.reserved - qty)
            .execution_options(synchronize_session=False)
        )

    async def commit_sale(self, variant_id: int, warehouse_id: int, qty: int) -> None:
        """Payment captured: reserved units leave the building."""
        await self.session.execute(
            update(Inventory)
            .where(
                Inventory.variant_id == variant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.reserved >= qty,
                Inventory.quantity >= qty,
            )
            .values(quantity=Inventory.quantity - qty, reserved=Inventory.reserved - qty)
            .execution_options(synchronize_session=False)
        )

    async def restock(self, variant_id: int, warehouse_id: int, qty: int) -> None:
        await self.session.execute(
            update(Inventory)
            .where(Inventory.variant_id == variant_id, Inventory.warehouse_id == warehouse_id)
            .values(quantity=Inventory.quantity + qty)
            .execution_options(synchronize_session=False)
        )
