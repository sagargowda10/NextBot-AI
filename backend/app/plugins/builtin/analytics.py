"""Plugin 10 — Analytics: sales, orders, product performance, inventory, agent and plugin metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, NoInput, PluginContext, action

PERIODS = r"^(today|yesterday|this week|last week|this month|last month|last 7 days|last 30 days|this year)$"


class PeriodIn(BaseModel):
    period: str = Field("this month", pattern=PERIODS)


class LimitIn(BaseModel):
    limit: int = Field(10, ge=1, le=100)


class ThresholdIn(BaseModel):
    threshold: int = Field(5, ge=0, le=1000)


class AnalyticsPlugin(BasePlugin):
    plugin_id = "analytics"
    name = "Analytics"
    version = "1.2.0"
    description = "Revenue and order reports, product performance, inventory analytics and AI agent/plugin execution metrics."

    @action("sales_summary", PeriodIn, "analytics:read", "Revenue, orders and AOV for a period")
    async def sales_summary(self, p: PeriodIn, ctx: PluginContext) -> dict:
        return (await ctx.services.analytics.sales_summary(p.period)).model_dump(mode="json")

    @action("order_report", NoInput, "analytics:read", "Order counts by status")
    async def order_report(self, p: NoInput, ctx: PluginContext) -> dict:
        return await ctx.services.analytics.order_stats()

    @action("product_performance", LimitIn, "analytics:read", "Top-selling products")
    async def product_performance(self, p: LimitIn, ctx: PluginContext) -> dict:
        return {"items": await ctx.services.analytics.product_performance(p.limit)}

    @action("inventory_analytics", ThresholdIn, "analytics:inventory", "Stock value, low-stock and out-of-stock counts")
    async def inventory_analytics(self, p: ThresholdIn, ctx: PluginContext) -> dict:
        return await ctx.services.analytics.inventory_insights(p.threshold)

    @action("agent_metrics", LimitIn, "analytics:read", "Recent AI agent executions and per-agent stats")
    async def agent_metrics(self, p: LimitIn, ctx: PluginContext) -> dict:
        metrics = ctx.extras.get("agent_metrics")
        if metrics is None:
            return {"recent": [], "per_agent": {}}
        recent = [
            {
                "agent": r.agent,
                "intent": r.intent,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "tool_calls": r.tool_calls,
                "error": r.error,
                "started_at": r.started_at.isoformat(),
            }
            for r in metrics.latest(p.limit)
        ]
        return {"recent": recent, "per_agent": {name: metrics.stats(name) for name in list(metrics.counts)}}

    @action("plugin_status", NoInput, "analytics:read", "Status, health and execution stats of every plugin")
    async def plugin_status(self, p: NoInput, ctx: PluginContext) -> dict:
        pm = ctx.extras.get("plugin_manager")
        if pm is None:
            return {"plugins": [], "summary": {}}
        plugins = [
            {
                "id": r.plugin.plugin_id,
                "name": r.plugin.name,
                "version": r.plugin.version,
                "status": r.status.value,
                "mode": r.plugin.mode,
                "healthy": bool(r.health and r.health.healthy),
                "executions": r.stats.executions,
                "failures": r.stats.failures,
                "avg_ms": r.stats.avg_duration_ms,
            }
            for r in pm.list()
        ]
        return {"plugins": plugins, "summary": pm.summary()}
