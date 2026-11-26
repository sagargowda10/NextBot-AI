"""Agent 5 — Order Management Agent: checkout coordination, retrieval, tracking, history, cancellation."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr


class OrderManagementAgent(BaseAgent):
    spec = AgentSpec(
        name="order_management",
        display_name="Order Management Agent",
        description="Creates orders from the cart, retrieves and tracks orders, shows history and cancels eligible orders.",
        tools=frozenset(
            {
                "order_management.checkout",
                "order_management.get",
                "order_management.latest",
                "order_management.history",
                "order_management.cancel",
                "order_management.cart_get",
            }
        ),
        max_iterations=4,
        read_only=False,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        match task.intent:
            case "checkout":
                return await self._checkout(task, ctx, run)
            case "track_order":
                return await self._latest(task, ctx, run)
            case "order_history":
                return await self._history(run)
            case "cancel_order":
                return await self._cancel(task, ctx, run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _checkout(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        risk = ctx.memory.get("risk") or {}
        payload = {"coupon_code": task.params.get("coupon_code"), "payment_method": "mock_upi", "risk_score": risk.get("score")}
        res = await run.call("order_management", "checkout", payload)
        if not res.success:
            return AgentResult(success=False, halt=True, summary=f"I couldn't place the order: {res.error}", error=res.error)
        order = res.data
        ctx.memory["last_order_id"] = order["id"]
        ctx.memory["last_order_number"] = order["order_number"]
        ctx.memory["last_order_total"] = order["total"]
        return AgentResult(
            success=True,
            data={"order": order},
            summary=f"Order **{order['order_number']}** created for {fmt_inr(order['total'])} "
            f"({len(order['items'])} item(s)); stock is reserved.",
        )

    async def _latest(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        res = await run.call("order_management", "latest", {})
        if not res.success:
            return AgentResult(success=False, halt=True, summary="You don't have any orders yet.", error=res.error)
        o = res.data
        ctx.memory["last_order_id"] = o["id"]
        ctx.memory["last_order_number"] = o["order_number"]
        return AgentResult(
            success=True,
            data={"order": o},
            summary=f"Your latest order **{o['order_number']}** ({fmt_inr(o['total'])}) is {o['status'].replace('_', ' ').lower()}.",
        )

    async def _history(self, run: AgentRun) -> AgentResult:
        res = await run.call("order_management", "history", {"limit": 5})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't load your orders.", error=res.error)
        items = res.data["items"]
        if not items:
            return AgentResult(success=True, summary="You haven't placed any orders yet.")
        lines = [f"• {o['order_number']} — {fmt_inr(o['total'])} — {o['status']}" for o in items]
        return AgentResult(success=True, data=res.data, summary="Your recent orders:\n" + "\n".join(lines))

    async def _cancel(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        latest = await run.call("order_management", "latest", {})
        if not latest.success:
            return AgentResult(success=False, summary="You don't have an order to cancel.", error=latest.error, halt=True)
        order = latest.data
        res = await run.call("order_management", "cancel", {"order_id": order["id"], "reason": task.message[:200] or "Customer request"})
        if not res.success:
            return AgentResult(
                success=False, halt=True, summary=f"Order {order['order_number']} can't be cancelled: {res.error}", error=res.error
            )
        ctx.memory["last_order_id"] = order["id"]
        if res.data.get("approval_request_id"):
            return AgentResult(
                success=True,
                requires_approval=True,
                data=res.data,
                summary=f"Cancelling {order['order_number']} needs a quick review by our team (high-value order). "
                f"Request #{res.data['approval_request_id']} is pending.",
            )
        return AgentResult(success=True, data=res.data, summary=f"Order {order['order_number']} has been cancelled and stock released.")
