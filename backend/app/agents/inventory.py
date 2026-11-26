"""Agent 4 — Inventory Agent: availability, warehouse stock, low-stock alerts."""

from __future__ import annotations

from collections import defaultdict

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent


class InventoryAgent(BaseAgent):
    spec = AgentSpec(
        name="inventory",
        display_name="Inventory Agent",
        description="Checks stock per variant and warehouse, prevents overselling and raises low-stock alerts.",
        tools=frozenset({"inventory.availability", "inventory.product_stock", "inventory.low_stock", "inventory.adjust"}),
        max_iterations=4,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent == "low_stock":
            return await self._low_stock(task, run)
        if task.intent in ("check_results", "inventory_check"):
            return await self._check_results(ctx, run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _check_results(self, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        products = ctx.memory.get("last_products") or []
        if not products:
            return AgentResult(success=True, summary="", data={"availability": {}})
        res = await run.call("inventory", "product_stock", {"product_ids": [p["id"] for p in products]})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't check stock right now.", error=res.error)
        avail: dict[int, int] = defaultdict(int)
        for lv in res.data["items"]:
            avail[lv["product_id"]] += lv["available"]
        prefs = ctx.memory.get("last_filters") or {}
        in_stock = [p["name"] for p in products if avail.get(p["id"], 0) > 0]
        low = [p["name"] for p in products if 0 < avail.get(p["id"], 0) <= 5]
        out = [p["name"] for p in products if avail.get(p["id"], 0) == 0]
        parts = [f"{len(in_stock)} of {len(products)} are in stock" + (f" (size {prefs['size']} checked)" if prefs.get("size") else "")]
        if low:
            parts.append("only a few left of " + ", ".join(low[:2]))
        if out:
            parts.append("out of stock: " + ", ".join(out[:2]))
        return AgentResult(
            success=True, summary="Stock: " + "; ".join(parts) + ".", data={"availability": {str(k): v for k, v in avail.items()}}
        )

    async def _low_stock(self, task: AgentTask, run: AgentRun) -> AgentResult:
        res = await run.call("inventory", "low_stock", {})
        if not res.success:
            if res.error_code == "forbidden":
                return AgentResult(
                    success=False, summary="Inventory reports are available to inventory managers and admins only.", error=res.error
                )
            return AgentResult(success=False, summary="I couldn't load inventory levels.", error=res.error)
        items = res.data["items"]
        if not items:
            return AgentResult(success=True, summary=f"No variants are at or below {res.data['threshold']} units. 🎉", data=res.data)
        lines = [
            f"• {i['product_name']} ({i['sku']}) — {i['available']} available" + (f" @ {i['warehouse']}" if i.get("warehouse") else "")
            for i in items[:10]
        ]
        return AgentResult(
            success=True,
            data=res.data,
            summary=f"{len(items)} variant(s) at or below {res.data['threshold']} units:\n" + "\n".join(lines),
            suggestions=["Show me this month's sales"],
        )
