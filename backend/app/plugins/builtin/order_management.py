"""Plugin 5 — Order Management: cart → checkout → order lifecycle → returns."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError
from app.plugins.base import BasePlugin, NoInput, PluginContext, action
from app.schemas.commerce import CheckoutRequest


class CartAddIn(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: int = Field(1, ge=1, le=10)


class CartUpdateIn(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(ge=0, le=10)


class CartItemIn(BaseModel):
    item_id: int = Field(gt=0)


class CheckoutIn(CheckoutRequest):
    risk_score: int | None = Field(None, ge=0, le=100)


class OrderIdIn(BaseModel):
    order_id: int = Field(gt=0)


class LatestIn(BaseModel):
    status: str | None = None


class HistoryIn(BaseModel):
    limit: int = Field(10, ge=1, le=50)


class CancelIn(BaseModel):
    order_id: int = Field(gt=0)
    reason: str = Field("Changed my mind", max_length=300)


class ReturnIn(BaseModel):
    order_id: int | None = Field(None, gt=0)
    reason: str = Field("Not as expected", min_length=3, max_length=500)


class OrderManagementPlugin(BasePlugin):
    plugin_id = "order_management"
    name = "Order Management"
    version = "1.4.0"
    description = "Shopping cart, checkout, order retrieval/history/cancellation and return requests."
    default_config = {"max_cart_quantity": 10}

    # ---- cart
    @action("cart_get", NoInput, "cart:write", "The caller's cart with totals")
    async def cart_get(self, p: NoInput, ctx: PluginContext) -> dict:
        return (await ctx.services.cart.get(ctx.principal.user_id or 0)).model_dump(mode="json")

    @action("cart_add", CartAddIn, "cart:write", "Add a variant to the cart (stock-validated)")
    async def cart_add(self, p: CartAddIn, ctx: PluginContext) -> dict:
        return (await ctx.services.cart.add(ctx.principal.user_id or 0, p.variant_id, p.quantity)).model_dump(mode="json")

    @action("cart_update", CartUpdateIn, "cart:write", "Change quantity (0 removes)")
    async def cart_update(self, p: CartUpdateIn, ctx: PluginContext) -> dict:
        return (await ctx.services.cart.update(ctx.principal.user_id or 0, p.item_id, p.quantity)).model_dump(mode="json")

    @action("cart_remove", CartItemIn, "cart:write", "Remove an item from the cart")
    async def cart_remove(self, p: CartItemIn, ctx: PluginContext) -> dict:
        return (await ctx.services.cart.remove(ctx.principal.user_id or 0, p.item_id)).model_dump(mode="json")

    # ---- orders
    @action("checkout", CheckoutIn, "order:own", "Validate cart, reserve stock and create an order")
    async def checkout(self, p: CheckoutIn, ctx: PluginContext) -> dict:
        req = CheckoutRequest(**p.model_dump(exclude={"risk_score"}))
        return (await ctx.services.orders.checkout(ctx.principal, req, risk_score=p.risk_score)).model_dump(mode="json")

    @action("get", OrderIdIn, "order:own", "One order (ownership enforced)")
    async def get(self, p: OrderIdIn, ctx: PluginContext) -> dict:
        return (await ctx.services.orders.get(ctx.principal, p.order_id)).model_dump(mode="json")

    @action("latest", LatestIn, "order:own", "The caller's most recent order")
    async def latest(self, p: LatestIn, ctx: PluginContext) -> dict:
        order = await ctx.services.orders.latest(ctx.principal, p.status)
        if order is None:
            raise NotFoundError("You don't have any orders yet.")
        return order.model_dump(mode="json")

    @action("history", HistoryIn, "order:own", "The caller's order history")
    async def history(self, p: HistoryIn, ctx: PluginContext) -> dict:
        orders = await ctx.services.orders.history(ctx.principal, p.limit)
        return {"items": [o.model_dump(mode="json") for o in orders], "count": len(orders)}

    @action("cancel", CancelIn, "order:own", "Cancel an eligible order (large orders need approval)")
    async def cancel(self, p: CancelIn, ctx: PluginContext) -> dict:
        return await ctx.services.orders.cancel(ctx.principal, p.order_id, p.reason, agent=ctx.agent)

    # ---- returns
    @action("return_request", ReturnIn, "return:own", "Request a return (eligibility + approval workflow)")
    async def return_request(self, p: ReturnIn, ctx: PluginContext) -> dict:
        return (await ctx.services.returns.request(ctx.principal, p.order_id, p.reason, agent=ctx.agent)).model_dump(mode="json")

    @action("return_list", NoInput, "return:own", "The caller's return requests")
    async def return_list(self, p: NoInput, ctx: PluginContext) -> dict:
        items = await ctx.services.returns.list(ctx.principal)
        return {"items": [i.model_dump(mode="json") for i in items]}
