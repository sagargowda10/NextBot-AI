"""Agent 3 — Product Intelligence Agent: specs, comparisons, personalised & budget recommendations."""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr
from app.agents.shopping import pick_from_memory, remember_products

DEFAULT_BUDGETS = {"smartphones": 25000, "laptops": 60000, "audio": 5000, "footwear": 4000, "wearables": 8000}


class ProductIntelligenceAgent(BaseAgent):
    spec = AgentSpec(
        name="product_intelligence",
        display_name="Product Intelligence Agent",
        description="Natural-language search, specifications, comparisons and personalised/budget recommendations.",
        tools=frozenset({"product_search.get_details", "product_search.semantic_search", "recommendation.*"}),
        max_iterations=6,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent == "recommend":
            return await self._recommend(task, ctx, run)
        if task.intent == "product_details":
            return await self._details(task, ctx, run)
        if task.intent == "compare_products":
            return await self._compare(task, ctx, run)
        if task.intent == "semantic_search":
            res = await run.call("product_search", "semantic_search", {"query": task.message, "limit": 5})
            items = res.data["items"] if res.success else []
            remember_products(ctx, items)
            return AgentResult(success=res.success, products=items, summary=f"Found {len(items)} related products.", error=res.error)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _recommend(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        category = task.params.get("category")
        budget = task.params.get("max_price")
        source = "your stated budget"
        if budget is None:
            res = await run.call("recommendation", "customer_budget", {"category": category})
            if res.success and res.data.get("budget"):
                budget, source = float(res.data["budget"]), "your profile and purchase history"
            else:
                budget, source = DEFAULT_BUDGETS.get(category or "", 20000), "a typical budget for this category"
        res = await run.call("recommendation", "budget", {"category": category, "budget": budget, "limit": 4})
        items: list[dict[str, Any]] = res.data["items"] if res.success else []
        if not items:
            res = await run.call("recommendation", "personalized", {"category": category, "limit": 4})
            items = res.data["items"] if res.success else []
        if not items:
            return AgentResult(success=True, summary="I couldn't find a good match yet — tell me your budget and I'll try again.")
        remember_products(ctx, items)
        top = items[0]
        lines = [f"{i + 1}. {p['name']} — {fmt_inr(p['price'])}" for i, p in enumerate(items)]
        rating = f" (⭐ {top['rating']})" if top.get("rating") else ""
        summary = (
            f"Based on {source} (~{fmt_inr(budget)}), my top pick is **{top['name']}** at "
            f"{fmt_inr(top['price'])}{rating}.\n" + "\n".join(lines)
        )
        return AgentResult(
            success=True,
            summary=summary,
            products=items,
            data={"budget": budget, "budget_source": source, "category": category},
            suggestions=["Add the first product to my cart", "Compare the first two"],
        )

    async def _details(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        product = pick_from_memory(ctx, task.params.get("ordinal", 1))
        if product is None:
            return AgentResult(success=False, summary="Which product would you like details for? Search first.", error="no product")
        res = await run.call("product_search", "get_details", {"product_id": product["id"]})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't load that product.", error=res.error)
        d = res.data
        specs = "\n".join(f"• {k}: {v}" for k, v in list(d.get("specifications", {}).items())[:8])
        return AgentResult(
            success=True,
            products=[d],
            data={"product": d},
            summary=f"**{d['name']}** by {d['brand']} — {fmt_inr(d['price'])}\n{d.get('description', '')[:240]}\n{specs}",
        )

    async def _compare(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        items = (ctx.memory.get("last_products") or [])[:2]
        if len(items) < 2:
            return AgentResult(
                success=False, summary="Search for products first, then ask me to compare the first two.", error="need 2 products"
            )
        details = []
        for p in items:
            r = await run.call("product_search", "get_details", {"product_id": p["id"]})
            if r.success:
                details.append(r.data)
        if len(details) < 2:
            return AgentResult(success=False, summary="I couldn't load both products.", error="details failed")
        a, b = details
        keys = [k for k in a.get("specifications", {}) if k in b.get("specifications", {})][:6]
        rows = [f"• Price: {fmt_inr(a['price'])} vs {fmt_inr(b['price'])}", f"• Rating: {a.get('rating')} vs {b.get('rating')}"]
        rows += [f"• {k}: {a['specifications'][k]} vs {b['specifications'][k]}" for k in keys]
        cheaper = a if float(a["price"]) <= float(b["price"]) else b
        return AgentResult(
            success=True,
            products=details,
            data={"comparison": {"a": a["id"], "b": b["id"], "attributes": keys}},
            summary=f"**{a['name']}** vs **{b['name']}**\n" + "\n".join(rows) + f"\n{cheaper['name']} is the better value.",
        )
