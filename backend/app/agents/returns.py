"""Agent 7 — Return and Refund Agent: eligibility, return records, refund coordination, approvals."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr


class ReturnRefundAgent(BaseAgent):
    spec = AgentSpec(
        name="return_refund",
        display_name="Return and Refund Agent",
        description=(
            "Checks return eligibility and windows, creates return records, coordinates refunds and requests approval when required."
        ),
        tools=frozenset({"order_management.return_request", "order_management.return_list", "order_management.latest"}),
        max_iterations=4,
        read_only=False,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent == "return_request":
            return await self._request(task, ctx, run)
        if task.intent == "return_status":
            return await self._status(run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _request(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        reason = task.params.get("reason") or "Customer requested via chat"
        res = await run.call("order_management", "return_request", {"reason": reason})
        if not res.success:
            return AgentResult(success=False, halt=True, summary=f"I can't start a return: {res.error}", error=res.error)
        r = res.data
        ctx.memory["last_order_id"] = r["order_id"]
        if not r.get("eligible", True):
            return AgentResult(
                success=False,
                halt=True,
                data={"return": r},
                summary=f"Order {r.get('order_number')} isn't eligible: {r['eligibility_message']}",
                error="not_eligible",
            )
        if r["status"] == "PENDING_APPROVAL":
            return AgentResult(
                success=True,
                requires_approval=True,
                data={"return": r},
                summary=f"Return #{r['id']} for {r.get('order_number')} is registered. Because the refund "
                f"({fmt_inr(r['refund_amount'])}) is above our auto-approval limit, a team member will "
                "approve it shortly. Pickup is scheduled after approval.",
            )
        return AgentResult(
            success=True,
            data={"return": r},
            summary=f"Return #{r['id']} for {r.get('order_number')} is approved. A pickup will be scheduled in 1–2 days; "
            f"your refund of {fmt_inr(r['refund_amount'])} is issued once the item is received.",
        )

    async def _status(self, run: AgentRun) -> AgentResult:
        res = await run.call("order_management", "return_list", {})
        items = res.data["items"] if res.success else []
        if not items:
            return AgentResult(success=True, summary="You don't have any return requests.")
        r = items[0]
        return AgentResult(
            success=True,
            data={"return": r},
            summary=f"Return #{r['id']} for {r.get('order_number')} is {r['status'].replace('_', ' ').lower()} "
            f"(refund {fmt_inr(r['refund_amount'])}).",
        )
