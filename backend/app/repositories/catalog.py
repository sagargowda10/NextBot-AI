from __future__ import annotations

from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select

from app.models.catalog import Brand, Product, ProductCategory, ProductVariant
from app.models.inventory import Inventory
from app.repositories.base import Repository
from app.schemas.catalog import ProductFilter


class ProductRepository(Repository[Product]):
    model = Product

    def _filtered(self, f: ProductFilter) -> Select[tuple[Product]]:
        stmt = select(Product).where(Product.is_active.is_(True))
        if f.category:
            stmt = stmt.join(ProductCategory, Product.category_id == ProductCategory.id).where(ProductCategory.slug == f.category)
        if f.brand:
            stmt = stmt.join(Brand, Product.brand_id == Brand.id).where(func.lower(Brand.slug) == f.brand)
        if f.min_price is not None:
            stmt = stmt.where(Product.price >= f.min_price)
        if f.max_price is not None:
            stmt = stmt.where(Product.price <= f.max_price)
        if f.query:
            for word in f.query.lower().split()[:6]:  # bound parameters only — no SQL injection surface
                like = f"%{word}%"
                stmt = stmt.where(
                    or_(
                        func.lower(Product.name).like(like), func.lower(Product.tags).like(like), func.lower(Product.description).like(like)
                    )
                )
        if f.size or f.colour:
            conds = [ProductVariant.product_id == Product.id, ProductVariant.is_active.is_(True)]
            if f.size:
                conds.append(func.lower(ProductVariant.size) == f.size.lower())
            if f.colour:
                conds.append(func.lower(ProductVariant.colour) == f.colour.lower())
            stmt = stmt.where(exists().where(and_(*conds)))
        if f.in_stock_only:
            stmt = stmt.where(
                exists().where(
                    and_(
                        ProductVariant.product_id == Product.id,
                        Inventory.variant_id == ProductVariant.id,
                        Inventory.quantity - Inventory.reserved > 0,
                    )
                )
            )
        orders: dict[str, list[Any]] = {
            "price_asc": [Product.price.asc()],
            "price_desc": [Product.price.desc()],
            "newest": [Product.created_at.desc()],
            "rating": [Product.rating.desc()],
            "relevance": [Product.rating.desc(), Product.rating_count.desc()],
        }
        order = orders[f.sort]
        return stmt.order_by(*order, Product.id)

    async def search(self, f: ProductFilter) -> list[Product]:
        stmt = self._filtered(f).offset(f.offset).limit(f.limit)
        return list((await self.session.scalars(stmt)).unique().all())

    async def count_matching(self, f: ProductFilter) -> int:
        sub = self._filtered(f).with_only_columns(Product.id).order_by(None).subquery()
        return int(await self.session.scalar(select(func.count()).select_from(sub)) or 0)

    async def by_ids(self, ids: list[int]) -> list[Product]:
        if not ids:
            return []
        rows = list((await self.session.scalars(select(Product).where(Product.id.in_(ids)))).all())
        order = {pid: i for i, pid in enumerate(ids)}
        return sorted(rows, key=lambda p: order.get(p.id, 0))

    async def in_category(
        self, category_id: int, exclude: int | None = None, limit: int = 10, max_price: float | None = None
    ) -> list[Product]:
        stmt = select(Product).where(Product.category_id == category_id, Product.is_active.is_(True))
        if exclude:
            stmt = stmt.where(Product.id != exclude)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)
        stmt = stmt.order_by(Product.rating.desc(), Product.id).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def category_by_slug(self, slug: str) -> ProductCategory | None:
        return await self.session.scalar(select(ProductCategory).where(ProductCategory.slug == slug))
