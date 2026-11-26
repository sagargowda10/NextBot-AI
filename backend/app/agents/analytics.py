"""Agent 11 — Analytics Agent: sales, product performance, inventory insights, platform metrics."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr

STAFF_ONLY = "Business analytics are available to admin users only."


class AnalyticsAgent(BaseAgent):
    spec = AgentSpec(
        name="analytics",
        display_name="Analytics Agent",
        description="Calculates sales and order statistics, top products, inventory insights and AI/plugin execution metrics.",
        tools=frozenset({"analytics.*"}),
        max_iterations=3,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        match task.intent:
            case "sales_report":
                return await self._sales(task, run)
            case "plugin_status":
                return await self._plugins(run)
            case "agent_executions":
                return await self._agents(run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    @staticmethod
    def _denied(res) -> AgentResult | None:  # type: ignore[no-untyped-def]
        if not res.success:
            msg = STAFF_ONLY if res.error_code == "forbidden" else "I couldn't load analytics right now."
            return AgentResult(success=False, summary=msg, error=res.error)
        return None

    async def _sales(self, task: AgentTask, run: AgentRun) -> AgentResult:
        period = task.params.get("period") or "this month"
        res = await run.call("analytics", "sales_summary", {"period": period})
        if (d := self._denied(res)) is not None:
            return d
        s = res.data
        top = await run.call("analytics", "product_performance", {"limit": 3})
        top_items = top.data["items"] if top.success else []
        top_txt = ("\nTop sellers: " + ", ".join(f"{t['name']} ({t['units']} units)" for t in top_items)) if top_items else ""
        return AgentResult(
            success=True,
            data={"sales": s, "top_products": top_items},
            summary=f"Sales {period}: {fmt_inr(s['revenue'])} from {s['orders']} paid orders "
            f"(average order {fmt_inr(s['average_order_value'])}).{top_txt}",
        )

    async def _plugins(self, run: AgentRun) -> AgentResult:
        res = await run.call("analytics", "plugin_status", {})
        if (d := self._denied(res)) is not None:
            return d
        sm = res.data["summary"]
        lines = [f"• {p['name']} v{p['version']} — {p['status']} ({p['mode']}), {p['executions']} runs" for p in res.data["plugins"]]
        return AgentResult(
            success=True,
            data=res.data,
            summary=f"{sm['enabled']}/{sm['total']} plugins enabled, {sm['failed']} failed, "
            f"{sm['executions']} executions so far:\n" + "\n".join(lines),
        )

    async def _agents(self, run: AgentRun) -> AgentResult:
        res = await run.call("analytics", "agent_metrics", {"limit": 10})
        if (d := self._denied(res)) is not None:
            return d
        recent = res.data["recent"]
        if not recent:
            return AgentResult(success=True, summary="No agent executions recorded yet.", data=res.data)
        lines = [
            f"• {r['agent']} — {r['intent']} — {'✅' if r['success'] else '❌'} {r['duration_ms']:.0f} ms, {r['tool_calls']} tool call(s)"
            for r in recent
        ]
        return AgentResult(success=True, data=res.data, summary="Recent AI agent executions:\n" + "\n".join(lines))
