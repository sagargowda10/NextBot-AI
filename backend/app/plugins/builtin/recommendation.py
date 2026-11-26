"""Plugin 2 — Recommendation: personalised, similar, frequently-bought, budget, related."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, PluginContext, action


class PersonalizedIn(BaseModel):
    category: str | None = None
    budget: Decimal | None = Field(None, gt=0)
    limit: int = Field(5, ge=1, le=20)


class ProductLimitIn(BaseModel):
    product_id: int = Field(gt=0)
    limit: int = Field(4, ge=1, le=20)


class BudgetIn(BaseModel):
    category: str | None = None
    budget: Decimal = Field(gt=0)
    limit: int = Field(5, ge=1, le=20)


class CategoryIn(BaseModel):
    category: str | None = None


def _dump(items: list) -> dict:
    return {"items": [i.model_dump(mode="json") for i in items], "count": len(items)}


class RecommendationPlugin(BasePlugin):
    plugin_id = "recommendation"
    name = "Recommendation"
    version = "1.1.0"
    description = "Personalised, similar, frequently-bought-together and budget-based recommendations."
    default_config = {"max_results": 10}

    @action("personalized", PersonalizedIn, "catalog:read", "Recommendations from the caller's purchase history")
    async def personalized(self, p: PersonalizedIn, ctx: PluginContext) -> dict:
        uid = ctx.principal.user_id or 0  # always the authenticated user, never a payload field
        return _dump(await ctx.services.recommendations.personalized(uid, p.category, p.budget, p.limit))

    @action("similar", ProductLimitIn, "catalog:read", "Products similar to a given product")
    async def similar(self, p: ProductLimitIn, ctx: PluginContext) -> dict:
        return _dump(await ctx.services.recommendations.similar(p.product_id, p.limit))

    @action("frequently_bought", ProductLimitIn, "catalog:read", "Frequently bought together")
    async def frequently_bought(self, p: ProductLimitIn, ctx: PluginContext) -> dict:
        return _dump(await ctx.services.recommendations.frequently_bought(p.product_id, p.limit))

    @action("budget", BudgetIn, "catalog:read", "Best picks within a budget")
    async def budget(self, p: BudgetIn, ctx: PluginContext) -> dict:
        return _dump(await ctx.services.recommendations.budget_picks(p.category, p.budget, p.limit))

    @action("related", ProductLimitIn, "catalog:read", "Related products (bought-together first, then similar)")
    async def related(self, p: ProductLimitIn, ctx: PluginContext) -> dict:
        rec = ctx.services.recommendations
        items = await rec.frequently_bought(p.product_id, p.limit)
        if len(items) < p.limit:
            seen = {i.id for i in items} | {p.product_id}
            items += [s for s in await rec.similar(p.product_id, p.limit) if s.id not in seen][: p.limit - len(items)]
        return _dump(items)

    @action("customer_budget", CategoryIn, "catalog:read", "Infer the caller's budget from profile or history")
    async def customer_budget(self, p: CategoryIn, ctx: PluginContext) -> dict:
        b = await ctx.services.recommendations.customer_budget(ctx.principal.user_id or 0, p.category)
        return {"budget": str(b) if b is not None else None}
