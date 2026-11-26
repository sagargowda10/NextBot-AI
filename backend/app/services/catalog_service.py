"""Product catalogue and recommendation services."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.state import AppState
from app.models.catalog import Brand, Product, ProductCategory, ProductImage, ProductVariant, Review
from app.models.commerce import Order, OrderItem
from app.models.inventory import Inventory, Warehouse
from app.models.user import CustomerProfile
from app.repositories.catalog import ProductRepository
from app.repositories.inventory import InventoryRepository
from app.schemas.catalog import ProductCreate, ProductDetail, ProductFilter, ProductSummary, ProductUpdate
from app.services.mappers import product_detail, product_summary

PAID = ("CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED")


class ProductService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.repo, self.inv = ProductRepository(session), InventoryRepository(session)

    async def _summaries(self, products: list[Product], scores: dict[int, float] | None = None) -> list[ProductSummary]:
        vids = [v.id for p in products for v in p.variants]
        avail = await self.inv.available_by_variant(vids)
        return [product_summary(p, avail, (scores or {}).get(p.id)) for p in products]

    async def search(self, filters: ProductFilter) -> list[ProductSummary]:
        # Cache the *matching product IDs* (the expensive part); prices/stock are always hydrated live.
        cache_key = "search:" + filters.model_dump_json()
        ids: list[int] | None = await self.state.cache.get_json(cache_key)
        if ids is None:
            if self.state.search_index is not None:
                try:
                    ids = await self.state.search_index.search_ids(filters)
                except Exception:  # search cluster unavailable → degrade to SQL
                    ids = None
            if ids is None:
                ids = [p.id for p in await self.repo.search(filters)]
            await self.state.cache.set_json(cache_key, ids, ttl_s=60)
        return await self._summaries(await self.repo.by_ids(ids))

    async def count(self, filters: ProductFilter) -> int:
        return await self.repo.count_matching(filters)

    async def get(self, product_id: int) -> ProductDetail | None:
        p = await self.repo.get(product_id)
        if p is None or not p.is_active:
            return None
        avail = await self.inv.available_by_variant([v.id for v in p.variants])
        reviews = int(await self.session.scalar(select(func.count()).select_from(Review).where(Review.product_id == p.id)) or 0)
        return product_detail(p, avail, reviews)

    async def semantic_search(self, query: str, limit: int = 5) -> list[ProductSummary]:
        hits = await self.state.rag.retrieve(query, k=limit, filters={"category": "product"})
        scores = {int(h.chunk.metadata["product_id"]): round(h.score, 3) for h in hits if h.chunk.metadata.get("product_id")}
        return await self._summaries(await self.repo.by_ids(list(scores)), scores)

    # ---- admin CRUD
    async def create(self, data: ProductCreate) -> ProductDetail:
        slug = data.name.lower().replace(" ", "-")
        p = Product(
            name=data.name,
            slug=slug,
            description=data.description,
            brand_id=data.brand_id,
            category_id=data.category_id,
            price=data.price,
            mrp=data.mrp,
            specifications=data.specifications,
        )
        if data.image_url:
            p.images = [ProductImage(url=data.image_url, alt=data.name)]
        self.session.add(p)
        await self.session.flush()
        wh = await self.session.scalar(select(Warehouse).order_by(Warehouse.priority).limit(1))
        for v in data.variants:
            pv = ProductVariant(product_id=p.id, sku=v.sku, size=v.size, colour=v.colour, price_override=v.price)
            self.session.add(pv)
            await self.session.flush()
            if wh is not None:
                self.session.add(Inventory(variant_id=pv.id, warehouse_id=wh.id, quantity=v.initial_stock, reserved=0))
        await self.session.flush()
        await self.session.refresh(p)
        return await self.get(p.id)  # type: ignore[return-value]

    async def update(self, product_id: int, data: ProductUpdate) -> ProductDetail:
        p = await self.repo.get_or_404(product_id, "Product")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(p, k, v)
        await self.session.flush()
        detail = await self.get(product_id)
        if detail is None:
            raise NotFoundError("Product not found")
        return detail

    async def deactivate(self, product_id: int) -> None:
        p = await self.repo.get_or_404(product_id, "Product")
        p.is_active = False

    async def categories(self) -> list[ProductCategory]:
        return list((await self.session.scalars(select(ProductCategory).order_by(ProductCategory.name))).all())

    async def brands(self) -> list[Brand]:
        return list((await self.session.scalars(select(Brand).order_by(Brand.name))).all())


class RecommendationService:
    """Content-based (same category, price proximity) + co-purchase (orders containing both items)."""

    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.products = ProductService(session, state)
        self.repo = ProductRepository(session)

    async def personalized(self, user_id: int, category: str | None, budget: Decimal | None, limit: int) -> list[ProductSummary]:
        bought = (
            select(OrderItem.category_slug, func.count())
            .join(Order)
            .where(Order.user_id == user_id, Order.status.in_(PAID))
            .group_by(OrderItem.category_slug)
            .order_by(func.count().desc())
        )
        cats = [c for c, _ in (await self.session.execute(bought)).all()]
        target = category or (cats[0] if cats else None)
        purchased = select(OrderItem.product_id).join(Order).where(Order.user_id == user_id)
        f = ProductFilter(category=target, max_price=budget, limit=limit * 2, sort="rating")
        items = [p for p in await self.products.search(f) if p.in_stock]
        owned = set((await self.session.scalars(purchased)).all())
        return [p for p in items if p.id not in owned][:limit]

    async def similar(self, product_id: int, limit: int) -> list[ProductSummary]:
        p = await self.repo.get_or_404(product_id, "Product")
        lo, hi = float(p.price) * 0.6, float(p.price) * 1.5
        cands = [c for c in await self.repo.in_category(p.category_id, exclude=p.id, limit=limit * 3) if lo <= float(c.price) <= hi]
        return await self.products._summaries(cands[:limit])

    async def frequently_bought(self, product_id: int, limit: int) -> list[ProductSummary]:
        orders_with = select(OrderItem.order_id).where(OrderItem.product_id == product_id)
        stmt = (
            select(OrderItem.product_id, func.count().label("n"))
            .where(OrderItem.order_id.in_(orders_with), OrderItem.product_id != product_id)
            .group_by(OrderItem.product_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        ids = [pid for pid, _ in (await self.session.execute(stmt)).all()]
        return await self.products._summaries(await self.repo.by_ids(ids))

    async def budget_picks(self, category: str | None, budget: Decimal, limit: int) -> list[ProductSummary]:
        f = ProductFilter(category=category, max_price=budget, min_price=budget * Decimal("0.4"), limit=limit * 2, sort="rating")
        items = [p for p in await self.products.search(f) if p.in_stock]
        return items[:limit]

    async def customer_budget(self, user_id: int, category: str | None) -> Decimal | None:
        prof = await self.session.scalar(select(CustomerProfile).where(CustomerProfile.user_id == user_id))
        if prof and category and (prof.budget_hints or {}).get(category):
            return Decimal(str(prof.budget_hints[category]))
        stmt = select(func.avg(OrderItem.unit_price)).join(Order).where(Order.user_id == user_id, Order.status.in_(PAID))
        if category:
            stmt = stmt.where(OrderItem.category_slug == category)
        avg = await self.session.scalar(stmt)
        return (Decimal(str(avg)) * Decimal("1.2")).quantize(Decimal("1")) if avg else None
