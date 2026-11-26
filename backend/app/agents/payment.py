"""Agent 6 — Payment Agent: fraud-checked payment initiation, status, failure handling."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr


class PaymentAgent(BaseAgent):
    spec = AgentSpec(
        name="payment",
        display_name="Payment Agent",
        description="Initiates payments (mock gateway in demo), checks status, handles failures and coordinates refunds.",
        tools=frozenset({"payment.initiate", "payment.verify", "payment.history", "payment.refund", "fraud_detection.assess_payment"}),
        max_iterations=4,
        read_only=False,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent == "pay":
            return await self._pay(task, ctx, run)
        if task.intent == "payment_issue":
            return await self._status(run)
        return AgentResult(success=False, error=f"unsupported intent {task.intent}")

    async def _pay(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        order_id = ctx.memory.get("last_order_id")
        if not order_id:
            return AgentResult(success=False, halt=True, summary="There's no order to pay for.", error="no order")
        if (ctx.memory.get("risk") or {}).get("recommend_manual_review"):
            return AgentResult(
                success=True,
                halt=True,
                requires_approval=True,
                summary="For your security, this order is held for a quick manual review before payment. "
                "We'll notify you as soon as it's cleared — no money has been taken.",
            )
        risk = await run.call("fraud_detection", "assess_payment", {"order_id": order_id})
        if risk.success and risk.data.get("recommend_manual_review"):
            return AgentResult(
                success=True,
                halt=True,
                requires_approval=True,
                data={"risk": risk.data},
                summary="This payment needs a quick manual review. No money has been taken.",
            )
        attempt = int(ctx.memory.get(f"pay_attempts_{order_id}", 0)) + 1
        ctx.memory[f"pay_attempts_{order_id}"] = attempt
        method = task.params.get("payment_method", "mock_upi")
        res = await run.call(
            "payment", "initiate", {"order_id": order_id, "method": method, "idempotency_key": f"chat-{order_id}-{attempt}"}
        )
        if not res.success:
            return AgentResult(success=False, halt=True, summary=f"Payment could not be started: {res.error}", error=res.error)
        pay = res.data
        if pay["status"] != "SUCCEEDED":
            return AgentResult(
                success=False,
                halt=True,
                data={"payment": pay},
                summary=f"Payment failed ({pay.get('failure_reason') or 'declined'}). Your items stay reserved — "
                "say “place my order” to retry.",
                error="payment_failed",
            )
        sim = " (simulated — demo gateway)" if pay.get("is_simulated") else ""
        return AgentResult(
            success=True,
            data={"payment": pay},
            summary=f"Payment of {fmt_inr(pay['amount'])} succeeded{sim}. Ref {pay.get('provider_reference')}.",
        )

    async def _status(self, run: AgentRun) -> AgentResult:
        res = await run.call("payment", "history", {"limit": 3})
        if not res.success or not res.data["items"]:
            return AgentResult(success=True, summary="I don't see any payments on your account yet.")
        p = res.data["items"][0]
        msg = {
            "SUCCEEDED": "went through successfully",
            "FAILED": f"failed ({p.get('failure_reason') or 'declined by bank'}) — "
            "if money was debited, banks auto-reverse failed UPI/card debits within 5–7 working days",
            "INITIATED": "is still pending confirmation from the gateway",
            "REFUNDED": "was refunded",
        }.get(p["status"], p["status"].lower())
        return AgentResult(
            success=True, data={"payment": p}, summary=f"Your latest payment of {fmt_inr(p['amount'])} (order #{p['order_id']}) {msg}."
        )
