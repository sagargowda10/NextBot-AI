"""Plugin 3 — Inventory: availability, warehouse stock, reservations, adjustments, low-stock alerts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, PluginContext, action


class VariantIdsIn(BaseModel):
    variant_ids: list[int] = Field(min_length=1, max_length=50)


class ProductIdsIn(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=50)


class ThresholdIn(BaseModel):
    threshold: int | None = Field(None, ge=0, le=1000)


class AdjustIn(BaseModel):
    inventory_id: int = Field(gt=0)
    delta: int = Field(ge=-10000, le=10000)
    reason: str = Field(min_length=3, max_length=200)


class OrderIdIn(BaseModel):
    order_id: int = Field(gt=0)


class InventoryPlugin(BasePlugin):
    plugin_id = "inventory"
    name = "Inventory"
    version = "1.3.0"
    description = "Stock availability per variant and warehouse, oversell-safe reservations and low-stock alerts."
    default_config = {"low_stock_threshold": 5}

    def validate_configuration(self, config: dict) -> list[str]:
        t = config.get("low_stock_threshold")
        return [] if isinstance(t, int) and t >= 0 else ["low_stock_threshold must be a non-negative integer"]

    @action("availability", VariantIdsIn, "catalog:read", "Available units for variants")
    async def availability(self, p: VariantIdsIn, ctx: PluginContext) -> dict:
        levels = await ctx.services.inventory.availability(p.variant_ids)
        return {"items": [lv.model_dump(mode="json") for lv in levels]}

    @action("product_stock", ProductIdsIn, "catalog:read", "Stock across all variants/warehouses of products")
    async def product_stock(self, p: ProductIdsIn, ctx: PluginContext) -> dict:
        levels = await ctx.services.inventory.for_products(p.product_ids)
        return {"items": [lv.model_dump(mode="json") for lv in levels]}

    @action("low_stock", ThresholdIn, "inventory:read", "Variants at or below the low-stock threshold")
    async def low_stock(self, p: ThresholdIn, ctx: PluginContext) -> dict:
        threshold = p.threshold if p.threshold is not None else int(self.config["low_stock_threshold"])
        levels = await ctx.services.inventory.low_stock(threshold)
        return {"threshold": threshold, "items": [lv.model_dump(mode="json") for lv in levels], "count": len(levels)}

    @action("adjust", AdjustIn, "inventory:write", "Adjust on-hand stock (large changes need approval)")
    async def adjust(self, p: AdjustIn, ctx: PluginContext) -> dict:
        res = await ctx.services.inventory.adjust(ctx.principal, p.inventory_id, p.delta, p.reason)
        return res.model_dump(mode="json")

    @action("reserve", OrderIdIn, "inventory:reserve", "Reserve stock for an order (system use)")
    async def reserve(self, p: OrderIdIn, ctx: PluginContext) -> dict:
        return {"reserved": await ctx.services.inventory.reserve_for_order(p.order_id)}

    @action("release", OrderIdIn, "inventory:reserve", "Release an order's reservation (system use)")
    async def release(self, p: OrderIdIn, ctx: PluginContext) -> dict:
        return {"released": await ctx.services.inventory.release_for_order(p.order_id)}
