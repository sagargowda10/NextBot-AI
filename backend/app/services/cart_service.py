from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, OutOfStockError, ValidationFailed
from app.core.state import AppState
from app.domain.pricing import CouponRule, LineInput, calculate_totals
from app.models.catalog import Coupon, ProductVariant
from app.models.commerce import CartItem, ShoppingCart
from app.repositories.inventory import InventoryRepository
from app.schemas.commerce import CartItemOut, CartOut

MAX_QTY = 10


def coupon_rule(c: Coupon) -> CouponRule:
    return CouponRule(
        code=c.code,
        discount_type=c.discount_type,
        value=c.value,
        min_order_value=c.min_order_value,
        max_discount=c.max_discount,
        active=c.active and (c.usage_limit is None or c.used_count < c.usage_limit),
        expires_at=c.expires_at,
    )


class CartService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state
        self.inv = InventoryRepository(session)

    async def _cart(self, user_id: int) -> ShoppingCart:
        cart = await self.session.scalar(select(ShoppingCart).where(ShoppingCart.user_id == user_id))
        if cart is None:
            cart = ShoppingCart(user_id=user_id, items=[])
            self.session.add(cart)
            await self.session.flush()
        return cart

    async def coupon(self, code: str | None) -> Coupon | None:
        if not code:
            return None
        return await self.session.scalar(select(Coupon).where(Coupon.code == code.upper()))

    async def _out(self, cart: ShoppingCart) -> CartOut:
        await self.session.refresh(cart, ["items"])
        items = []
        for it in cart.items:
            v = it.variant
            price = v.effective_price
            items.append(
                CartItemOut(
                    id=it.id,
                    variant_id=v.id,
                    product_id=v.product_id,
                    product_name=v.product.name,
                    sku=v.sku,
                    size=v.size,
                    colour=v.colour,
                    unit_price=price,
                    quantity=it.quantity,
                    line_total=price * it.quantity,
                    image_url=v.product.images[0].url if v.product.images else None,
                )
            )
        c = await self.coupon(cart.coupon_code)
        t = calculate_totals([LineInput(i.unit_price, i.quantity) for i in items], coupon_rule(c) if c else None)
        return CartOut(
            id=cart.id,
            items=items,
            subtotal=t.subtotal,
            discount=t.discount,
            tax=t.tax,
            shipping=t.shipping,
            total=t.total,
            coupon_code=t.coupon_code,
            coupon_error=t.coupon_error if cart.coupon_code else None,
        )

    async def get(self, user_id: int) -> CartOut:
        return await self._out(await self._cart(user_id))

    async def _check_stock(self, variant_id: int, qty: int) -> None:
        avail = (await self.inv.available_by_variant([variant_id])).get(variant_id, 0)
        if avail < qty:
            raise OutOfStockError(f"Only {avail} unit(s) available", details={"available": avail})

    async def add(self, user_id: int, variant_id: int, quantity: int) -> CartOut:
        variant = await self.session.get(ProductVariant, variant_id)
        if variant is None or not variant.is_active or not variant.product.is_active:
            raise NotFoundError("Product variant not found")
        cart = await self._cart(user_id)
        existing = next((i for i in cart.items if i.variant_id == variant_id), None)
        new_qty = (existing.quantity if existing else 0) + quantity
        if new_qty > MAX_QTY:
            raise ValidationFailed(f"Maximum {MAX_QTY} units per item")
        await self._check_stock(variant_id, new_qty)
        if existing:
            existing.quantity = new_qty
        else:
            self.session.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=quantity))
        await self.session.flush()
        return await self._out(cart)

    async def update(self, user_id: int, item_id: int, quantity: int) -> CartOut:
        cart = await self._cart(user_id)
        item = next((i for i in cart.items if i.id == item_id), None)
        if item is None:
            raise NotFoundError("Cart item not found")
        if quantity == 0:
            await self.session.delete(item)
        else:
            await self._check_stock(item.variant_id, quantity)
            item.quantity = quantity
        await self.session.flush()
        return await self._out(cart)

    async def remove(self, user_id: int, item_id: int) -> CartOut:
        return await self.update(user_id, item_id, 0)

    async def apply_coupon(self, user_id: int, code: str | None) -> CartOut:
        cart = await self._cart(user_id)
        if code and await self.coupon(code) is None:
            raise ValidationFailed("Unknown coupon code")
        cart.coupon_code = code.upper() if code else None
        await self.session.flush()
        return await self._out(cart)

    async def clear(self, user_id: int) -> None:
        cart = await self._cart(user_id)
        for it in list(cart.items):
            await self.session.delete(it)
        cart.coupon_code = None
        await self.session.flush()

    async def total(self, user_id: int) -> Decimal:
        return (await self.get(user_id)).total
