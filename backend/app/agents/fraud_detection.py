"""Agent 10 — Fraud Detection Agent: explainable risk scores; recommends review, never auto-rejects."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent


class FraudDetectionAgent(BaseAgent):
    spec = AgentSpec(
        name="fraud_detection",
        display_name="Fraud Detection Agent",
        description="Scores orders and payments for risk with human-readable reasons and recommends manual review.",
        tools=frozenset({"fraud_detection.*"}),
        max_iterations=2,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent != "assess_checkout":
            return AgentResult(success=False, error=f"unsupported intent {task.intent}")
        res = await run.call("fraud_detection", "assess_order", {})
        if not res.success:
            # fail open for scoring outages, but leave a trace: the order still gets reviewed downstream if needed
            ctx.memory["risk"] = {"score": None, "recommend_manual_review": False, "unavailable": True}
            return AgentResult(success=False, summary="", error=res.error)
        ctx.memory["risk"] = res.data
        note = "" if res.data["level"] == "LOW" else f"Risk {res.data['level']} ({res.data['score']}): {res.data['explanation']}"
        return AgentResult(success=True, summary=note, data={"risk": res.data}, requires_approval=bool(res.data["recommend_manual_review"]))
