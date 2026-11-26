
import asyncio
from sqlalchemy import select, func

from app.core.config import get_settings
from app.database.session import init_engine, session_factory
from app.models.catalog import Product


async def main():
    settings = get_settings()
    init_engine(settings.database_url)

    async with session_factory()() as db:
        total = await db.scalar(
            select(func.count()).select_from(Product)
        )

        active = await db.scalar(
            select(func.count()).select_from(Product)
            .where(Product.is_active.is_(True))
        )

        inactive = await db.scalar(
            select(func.count()).select_from(Product)
            .where(Product.is_active.is_(False))
        )

        print("\n===== PRODUCT DIAGNOSTICS =====")
        print("Total products:", total)
        print("Active products:", active)
        print("Inactive products:", inactive)


if __name__ == "__main__":
    asyncio.run(main())
