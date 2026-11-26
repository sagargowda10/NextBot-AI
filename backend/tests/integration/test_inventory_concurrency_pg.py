"""Oversell protection under real concurrency on PostgreSQL (Testcontainers).

Twenty concurrent transactions try to reserve the last 3 units of a variant; exactly 3 may win.
Requires Docker; skipped otherwise.
"""

import asyncio
import importlib.util
import shutil

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.containers, pytest.mark.anyio]

if importlib.util.find_spec("testcontainers") is None or shutil.which("docker") is None:
    pytest.skip("Docker/testcontainers not available", allow_module_level=True)


async def test_concurrent_reservations_never_oversell():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer

    from app.database.base import Base
    from app.models.catalog import Brand, Product, ProductCategory, ProductVariant
    from app.models.inventory import Inventory, Warehouse
    from app.repositories.inventory import InventoryRepository

    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url, pool_size=25)
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as s, s.begin():
            b, c, w = (
                Brand(name="B", slug="b"),
                ProductCategory(name="C", slug="c"),
                Warehouse(code="W", name="W", city="X", pincode="560001"),
            )
            s.add_all([b, c, w])
            await s.flush()
            p = Product(name="P", slug="p", brand_id=b.id, category_id=c.id, price=100, mrp=100)
            s.add(p)
            await s.flush()
            v = ProductVariant(product_id=p.id, sku="SKU-1")
            s.add(v)
            await s.flush()
            inv = Inventory(variant_id=v.id, warehouse_id=w.id, quantity=3, reserved=0)
            s.add(inv)
        inv_id = inv.id

        async def attempt() -> bool:
            async with sessions() as s, s.begin():
                return await InventoryRepository(s).try_reserve(inv_id, 1)

        results = await asyncio.gather(*(attempt() for _ in range(20)))
        async with sessions() as s:
            row = await s.get(Inventory, inv_id)
        assert sum(results) == 3 and row.reserved == 3 and row.quantity == 3
        await engine.dispose()
