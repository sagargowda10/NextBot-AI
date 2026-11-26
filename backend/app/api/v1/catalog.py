"""Products and cart."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_state, page_params
from app.core.exceptions import NotFoundError
from app.core.state import AppState
from app.database.session import get_session
from app.schemas.catalog import BrandOut, CategoryOut, ProductCreate, ProductDetail, ProductFilter, ProductSummary, ProductUpdate
from app.schemas.commerce import CartItemAdd, CartItemUpdate, CartOut
from app.schemas.common import Page, PageParams
from app.security.dependencies import get_principal, require
from app.security.permissions import Principal
from app.services.cart_service import CartService
from app.services.catalog_service import ProductService

products = APIRouter(prefix="/products", tags=["Products"])
cart = APIRouter(prefix="/cart", tags=["Cart"])


def svc(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> ProductService:
    return ProductService(session, state)


def filters(
    q: str | None = Query(None, max_length=200),
    category: str | None = None,
    brand: str | None = None,
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    # NOTE: `size` is reserved for page size (see page_params). The product/variant size filter is `variant_size`.
    variant_size: str | None = Query(None, max_length=20),
    colour: str | None = None,
    in_stock: bool = False,
    sort: str = Query("relevance", pattern="^(relevance|price_asc|price_desc|rating|newest)$"),
    p: PageParams = Depends(page_params),
) -> ProductFilter:
    return ProductFilter(
        query=q,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        size=variant_size,
        colour=colour,
        in_stock_only=in_stock,
        sort=sort,
        limit=p.size,
        offset=p.offset,
    )


@products.get("", response_model=Page[ProductSummary])
async def list_products(f: ProductFilter = Depends(filters), s: ProductService = Depends(svc)) -> Page[ProductSummary]:
    items = await s.search(f)
    return Page(items=items, total=await s.count(f), page=f.offset // f.limit + 1, size=f.limit)


@products.get("/search", response_model=Page[ProductSummary])
async def search_products(
    f: ProductFilter = Depends(filters), semantic: bool = False, s: ProductService = Depends(svc)
) -> Page[ProductSummary]:
    if semantic and f.query:
        items = await s.semantic_search(f.query, f.limit)
        return Page(items=items, total=len(items), page=1, size=f.limit)
    return await list_products(f, s)


@products.get("/categories", response_model=list[CategoryOut])
async def categories(s: ProductService = Depends(svc)) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in await s.categories()]


@products.get("/brands", response_model=list[BrandOut])
async def brands(s: ProductService = Depends(svc)) -> list[BrandOut]:
    return [BrandOut.model_validate(b) for b in await s.brands()]


@products.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, s: ProductService = Depends(svc)) -> ProductDetail:
    p = await s.get(product_id)
    if p is None:
        raise NotFoundError("Product not found")
    return p


@products.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require("catalog:write"))])
async def create_product(body: ProductCreate, s: ProductService = Depends(svc)) -> ProductDetail:
    return await s.create(body)


@products.put("/{product_id}", response_model=ProductDetail, dependencies=[Depends(require("catalog:write"))])
async def update_product(product_id: int, body: ProductUpdate, s: ProductService = Depends(svc)) -> ProductDetail:
    return await s.update(product_id, body)


@products.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require("catalog:write"))])
async def delete_product(product_id: int, s: ProductService = Depends(svc)) -> None:
    await s.deactivate(product_id)  # soft delete keeps order history intact


def cart_svc(session: AsyncSession = Depends(get_session), state: AppState = Depends(get_state)) -> CartService:
    return CartService(session, state)


@cart.get("", response_model=CartOut)
async def get_cart(principal: Principal = Depends(require("cart:write")), c: CartService = Depends(cart_svc)) -> CartOut:
    return await c.get(principal.user_id or 0)


@cart.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
async def add_item(body: CartItemAdd, principal: Principal = Depends(require("cart:write")), c: CartService = Depends(cart_svc)) -> CartOut:
    return await c.add(principal.user_id or 0, body.variant_id, body.quantity)


@cart.put("/items/{item_id}", response_model=CartOut)
async def update_item(
    item_id: int, body: CartItemUpdate, principal: Principal = Depends(require("cart:write")), c: CartService = Depends(cart_svc)
) -> CartOut:
    return await c.update(principal.user_id or 0, item_id, body.quantity)


@cart.delete("/items/{item_id}", response_model=CartOut)
async def remove_item(item_id: int, principal: Principal = Depends(require("cart:write")), c: CartService = Depends(cart_svc)) -> CartOut:
    return await c.remove(principal.user_id or 0, item_id)


@cart.post("/coupon", response_model=CartOut)
async def apply_coupon(
    code: str | None = None, principal: Principal = Depends(get_principal), c: CartService = Depends(cart_svc)
) -> CartOut:
    return await c.apply_coupon(principal.user_id or 0, code)
