"""Plugin 6 — Shipping: shipments, tracking, ETA estimates. Mock courier; Shiprocket-ready adapter."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError
from app.plugins.base import BasePlugin, HealthStatus, PluginContext, action


class OrderIdIn(BaseModel):
    order_id: int = Field(gt=0)


class EstimateIn(BaseModel):
    pincode: str | None = Field(None, pattern=r"^[1-9][0-9]{5}$")


class AdvanceIn(BaseModel):
    shipment_id: int = Field(gt=0)
    status: str = Field(pattern=r"^(PACKED|SHIPPED|OUT_FOR_DELIVERY|DELIVERED)$")
    location: str | None = None


class ShippingPlugin(BasePlugin):
    plugin_id = "shipping"
    name = "Shipping"
    version = "1.1.0"
    description = "Shipment creation, tracking and delivery estimates. Mock courier locally; Shiprocket adapter needs credentials."
    default_config = {"provider": "mock", "shiprocket_email": None, "shiprocket_password": None}
    secret_keys = frozenset({"shiprocket_password"})

    @property
    def mode(self) -> str:
        return "mock" if self.config.get("provider") == "mock" else "live"

    def validate_configuration(self, config: dict) -> list[str]:
        if config.get("provider") == "shiprocket" and not (config.get("shiprocket_email") and config.get("shiprocket_password")):
            return ["shiprocket requires SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD"]
        return [] if config.get("provider") in ("mock", "shiprocket") else ["provider must be mock or shiprocket"]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"provider={self.config.get('provider')} ({self.mode})")

    @action("create_shipment", OrderIdIn, "order:own", "Create a shipment for a confirmed order (idempotent)")
    async def create_shipment(self, p: OrderIdIn, ctx: PluginContext) -> dict:
        await ctx.services.orders.get(ctx.principal, p.order_id)  # ownership check
        return (await ctx.services.shipments.create_for_order(p.order_id)).model_dump(mode="json")

    @action("track", OrderIdIn, "shipment:own", "Tracking timeline for an order")
    async def track(self, p: OrderIdIn, ctx: PluginContext) -> dict:
        shipment = await ctx.services.shipments.track(ctx.principal, p.order_id)
        if shipment is None:
            raise NotFoundError("No shipment has been created for this order yet.")
        return shipment.model_dump(mode="json")

    @action("estimate", EstimateIn, "catalog:read", "Delivery estimate for a PIN code (defaults to the caller's address)")
    async def estimate(self, p: EstimateIn, ctx: PluginContext) -> dict:
        pin = p.pincode
        if pin is None and ctx.principal.user_id:
            pin = await ctx.services.shipments.default_pincode(ctx.principal.user_id)
        return (await ctx.services.shipments.estimate(pin or "")).model_dump(mode="json")

    @action("advance", AdvanceIn, "shipment:manage", "Move a shipment to its next status (courier webhook / admin)")
    async def advance(self, p: AdvanceIn, ctx: PluginContext) -> dict:
        return (await ctx.services.shipments.advance(p.shipment_id, p.status, p.location)).model_dump(mode="json")
