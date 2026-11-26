"""Agent 9 — Logistics Agent: shipment creation, tracking, delivery estimates."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent


class LogisticsAgent(BaseAgent):
    spec = AgentSpec(
        name="logistics",
        display_name="Logistics Agent",
        description="Creates shipments, tracks deliveries and estimates delivery dates by PIN code.",
        tools=frozenset({"shipping.create_shipment", "shipping.track", "shipping.estimate"}),
        max_iterations=3,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        match task.intent:
            case "delivery_estimate":
                return await self._estimate(task, run)
            case "create_shipment":
                return await self._create(ctx, run)
            case "track_order":
                return await self._track(ctx, run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _estimate(self, task: AgentTask, run: AgentRun) -> AgentResult:
        payload = {"pincode": task.params["pincode"]} if task.params.get("pincode") else {}
        res = await run.call("shipping", "estimate", payload)
        if not res.success:
            return AgentResult(success=False, summary="I couldn't estimate delivery.", error=res.error)
        return AgentResult(success=res.data["serviceable"], summary=res.data["message"], data={"estimate": res.data})

    async def _create(self, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        order_id = ctx.memory.get("last_order_id")
        if not order_id:
            return AgentResult(success=False, error="no order")
        res = await run.call("shipping", "create_shipment", {"order_id": order_id})
        if not res.success:
            return AgentResult(success=False, summary="Shipment will be created shortly.", error=res.error)
        s = res.data
        eta = f", expected by {s['estimated_delivery']}" if s.get("estimated_delivery") else ""
        return AgentResult(success=True, data={"shipment": s}, summary=f"Shipment {s['tracking_number']} booked with {s['carrier']}{eta}.")

    async def _track(self, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        order_id = ctx.memory.get("last_order_id")
        if not order_id:
            return AgentResult(success=False, error="no order")
        res = await run.call("shipping", "track", {"order_id": order_id})
        if not res.success:
            return AgentResult(success=True, summary="It hasn't been handed to the courier yet.", data={"shipment": None})
        s = res.data
        last = s["events"][-1] if s.get("events") else None
        where = (
            f" — last update: {last['note'] or last['status']}" + (f" at {last['location']}" if last and last.get("location") else "")
            if last
            else ""
        )
        eta = f" Estimated delivery: {s['estimated_delivery']}." if s.get("estimated_delivery") and s["status"] != "DELIVERED" else ""
        return AgentResult(
            success=True,
            data={"shipment": s},
            summary=f"Tracking {s['tracking_number']} ({s['carrier']}): {s['status'].replace('_', ' ').lower()}{where}.{eta}",
        )
