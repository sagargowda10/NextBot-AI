"""Agent 2 — Shopping Agent: search & filter, cart operations, related products."""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr

FILTER_KEYS = ("query", "category", "brand", "min_price", "max_price", "size", "colour", "sort")
SORT_LABEL = {"price_asc": "lowest price first", "price_desc": "highest price first", "rating": "top rated first", "newest": "newest first"}
SORT_LEAD = {"price_asc": "The lowest-priced", "price_desc": "The most expensive", "rating": "The top-rated", "newest": "The newest"}


def remember_products(ctx: AgentRunContext, products: list[dict[str, Any]], filters: dict[str, Any] | None = None) -> None:
    ctx.memory["last_products"] = [
        {"id": p["id"], "name": p["name"], "price": p["price"], "variants": p.get("variants", [])} for p in products[:8]
    ]
    if filters is not None:
        ctx.memory["last_filters"] = {k: v for k, v in filters.items() if k in ("size", "colour")}


def pick_from_memory(ctx: AgentRunContext, ordinal: Any) -> dict[str, Any] | None:
    items = ctx.memory.get("last_products") or []
    if not items:
        return None
    if ordinal == "cheapest":
        return min(items, key=lambda p: float(p["price"]))
    idx = int(ordinal or 1)
    idx = len(items) if idx == -1 else idx
    return items[idx - 1] if 1 <= idx <= len(items) else None


def choose_variant(product: dict[str, Any], prefs: dict[str, Any]) -> dict[str, Any] | None:
    variants = product.get("variants") or []

    def ok(v: dict[str, Any]) -> bool:
        return all(not prefs.get(k) or str(v.get(k) or "").lower() == str(prefs[k]).lower() for k in ("size", "colour"))

    for pool in ([v for v in variants if ok(v)], variants):
        in_stock = [v for v in pool if int(v.get("stock_available", 0)) > 0]
        if in_stock:
            return in_stock[0]
    return None


class ShoppingAgent(BaseAgent):
    spec = AgentSpec(
        name="shopping",
        display_name="Shopping Agent",
        description="Understands shopping needs, searches and filters products, manages the cart and suggests related items.",
        tools=frozenset(
            {
                "product_search.search",
                "recommendation.related",
                "order_management.cart_get",
                "order_management.cart_add",
                "order_management.cart_update",
                "order_management.cart_remove",
            }
        ),
        max_iterations=6,
        read_only=False,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        handler = {
            "product_search": self._search,
            "add_to_cart": self._add,
            "view_cart": self._view,
            "remove_from_cart": self._remove,
        }.get(task.intent)
        if handler is None:
            return AgentResult(success=False, error=f"unsupported intent {task.intent}")
        return await handler(task, ctx, run)

    async def _search(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        filters = {k: task.params[k] for k in FILTER_KEYS if task.params.get(k) is not None}
        filters["limit"] = 6
        res = await run.call("product_search", "search", filters)
        if not res.success:
            return AgentResult(success=False, summary="I couldn't search the catalogue right now.", error=res.error)
        items: list[dict[str, Any]] = res.data["items"]
        relaxed = res.data.get("relaxed_filters") or []
        if not items:
            return AgentResult(
                success=True,
                summary="I couldn't find products matching that. Try widening the budget or removing a filter.",
                data={"count": 0, "filters": filters},
                suggestions=["Show me all footwear", "Find a laptop under ₹80,000"],
            )
        remember_products(ctx, items, filters)
        desc = ", ".join(str(filters[k]) for k in ("colour", "query", "category") if filters.get(k))
        lines = [
            f"{i + 1}. {p['name']} — {fmt_inr(p['price'])}" + (f" (⭐ {p['rating']})" if p.get("rating") else "")
            for i, p in enumerate(items)
        ]
        summary = (
            f"I found {len(items)} {desc or 'products'}"
            + (f" under {fmt_inr(filters['max_price'])}" if filters.get("max_price") else "")
            + ":\n"
            + "\n".join(lines)
        )
        if filters.get("sort") in SORT_LABEL:
            top = items[0]
            what = filters.get("category", "product").replace("-", " ").rstrip("s") or "product"
            summary = (
                f"{SORT_LEAD[filters['sort']]} {what} is {top['name']} at {fmt_inr(top['price'])}.\n"
                f"Sorted {SORT_LABEL[filters['sort']]}:\n" + "\n".join(lines)
            )
        if relaxed:
            summary += f"\n(No exact match, so I relaxed the {', '.join(relaxed)} filter.)"
        related = await run.call("recommendation", "related", {"product_id": items[0]["id"], "limit": 3})
        related_items = related.data["items"] if related.success else []
        return AgentResult(
            success=True,
            summary=summary,
            products=items,
            data={
                "count": len(items),
                "filters": filters,
                "relaxed_filters": relaxed,
                "related": [{"id": r["id"], "name": r["name"], "price": r["price"]} for r in related_items],
            },
            suggestions=["Add the first product to my cart", "Compare the first two", "Check delivery to 560001"],
        )

    async def _add(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        product = pick_from_memory(ctx, task.params.get("ordinal", 1))
        if product is None:
            return AgentResult(
                success=False,
                summary="Which product? Search for something first and then say e.g. “add the first one”.",
                error="no product in conversation memory",
            )
        prefs = {**(ctx.memory.get("last_filters") or {}), **{k: task.params[k] for k in ("size", "colour") if task.params.get(k)}}
        variant = choose_variant(product, prefs)
        if variant is None:
            return AgentResult(success=False, summary=f"Sorry, {product['name']} is out of stock right now.", error="out_of_stock")
        res = await run.call("order_management", "cart_add", {"variant_id": variant["id"], "quantity": int(task.params.get("quantity", 1))})
        if not res.success:
            return AgentResult(success=False, summary=f"I couldn't add {product['name']}: {res.error}", error=res.error)
        cart = res.data
        variant_desc = " / ".join(str(variant[k]) for k in ("colour", "size") if variant.get(k))
        return AgentResult(
            success=True,
            summary=f"Added {product['name']}{f' ({variant_desc})' if variant_desc else ''} to your cart. "
            f"Cart: {len(cart['items'])} item(s), total {fmt_inr(cart['total'])}.",
            data={"cart": cart, "added_variant_id": variant["id"]},
            suggestions=["Place my order", "Show my cart"],
        )

    async def _view(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        res = await run.call("order_management", "cart_get", {})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't load your cart.", error=res.error)
        cart = res.data
        if not cart["items"]:
            return AgentResult(success=True, summary="Your cart is empty.", data={"cart": cart})
        lines = [f"• {i['product_name']} x{i['quantity']} — {fmt_inr(i['line_total'])}" for i in cart["items"]]
        ctx.memory["last_cart_items"] = [i["id"] for i in cart["items"]]
        return AgentResult(
            success=True,
            summary="Your cart:\n" + "\n".join(lines) + f"\nTotal: {fmt_inr(cart['total'])}",
            data={"cart": cart},
            suggestions=["Place my order"],
        )

    async def _remove(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        cart = await run.call("order_management", "cart_get", {})
        if not cart.success or not cart.data["items"]:
            return AgentResult(success=True, summary="Your cart is already empty.")
        items = cart.data["items"]
        idx = int(task.params.get("ordinal", 1)) if task.params.get("ordinal") not in (None, "cheapest") else 1
        idx = len(items) if idx == -1 else idx
        if not 1 <= idx <= len(items):
            return AgentResult(success=False, summary=f"Your cart has {len(items)} item(s).", error="bad ordinal")
        target = items[idx - 1]
        res = await run.call("order_management", "cart_remove", {"item_id": target["id"]})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't update your cart.", error=res.error)
        return AgentResult(
            success=True,
            summary=f"Removed {target['product_name']}. Cart total is now {fmt_inr(res.data['total'])}.",
            data={"cart": res.data},
        )
