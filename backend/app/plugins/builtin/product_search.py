"""Plugin 1 — Product Search: keyword + attribute filters, specifications, semantic search."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError
from app.plugins.base import BasePlugin, PluginContext, action
from app.schemas.catalog import ProductFilter


class ProductIdIn(BaseModel):
    product_id: int = Field(gt=0)


class SemanticIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(5, ge=1, le=20)


class ProductSearchPlugin(BasePlugin):
    plugin_id = "product_search"
    name = "Product Search"
    version = "1.2.0"
    description = "Catalogue search with category, price, brand, size and colour filters plus semantic search."
    default_config = {"default_limit": 10, "relax_filters_when_empty": True}

    def validate_configuration(self, config: dict) -> list[str]:
        lim = config.get("default_limit", 10)
        return [] if isinstance(lim, int) and 1 <= lim <= 50 else ["default_limit must be 1-50"]

    @action("search", ProductFilter, "catalog:read", "Search products with structured filters")
    async def search(self, p: ProductFilter, ctx: PluginContext) -> dict:
        results = await ctx.services.products.search(p)
        relaxed: list[str] = []
        if not results and self.config.get("relax_filters_when_empty"):
            for field in ("size", "colour", "brand"):
                if getattr(p, field):
                    relaxed.append(field)
                    p = p.model_copy(update={field: None})
                    results = await ctx.services.products.search(p)
                    if results:
                        break
        return {"items": [r.model_dump(mode="json") for r in results], "count": len(results), "relaxed_filters": relaxed}

    @action("get_details", ProductIdIn, "catalog:read", "Full specifications for one product")
    async def get_details(self, p: ProductIdIn, ctx: PluginContext) -> dict:
        product = await ctx.services.products.get(p.product_id)
        if product is None:
            raise NotFoundError(f"Product {p.product_id} not found")
        return product.model_dump(mode="json")

    @action("semantic_search", SemanticIn, "catalog:read", "Natural-language product search over embeddings")
    async def semantic_search(self, p: SemanticIn, ctx: PluginContext) -> dict:
        results = await ctx.services.products.semantic_search(p.query, p.limit)
        return {"items": [r.model_dump(mode="json") for r in results], "count": len(results)}
