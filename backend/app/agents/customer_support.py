"""Agent 8 — Customer Support Agent: RAG answers with sources, escalation to humans."""

from __future__ import annotations

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent


class CustomerSupportAgent(BaseAgent):
    spec = AgentSpec(
        name="customer_support",
        display_name="Customer Support Agent",
        description="Answers FAQs and policy questions from the knowledge base (RAG with sources) and escalates unresolved queries.",
        tools=frozenset({"customer_support.*", "email.send", "whatsapp.send_template"}),
        max_iterations=4,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        if task.intent == "escalate":
            return await self._escalate(task, ctx, run)
        return await self._answer(task, run)

    async def _answer(self, task: AgentTask, run: AgentRun) -> AgentResult:
        res = await run.call("customer_support", "answer", {"question": task.message or "help"})
        if not res.success:
            return AgentResult(success=False, summary="I couldn't reach our help centre right now.", error=res.error)
        ans = res.data
        if not ans.get("grounded"):
            return AgentResult(
                success=True,
                summary=ans["answer"],
                data={"grounded": False},
                suggestions=["Talk to a human", "What is your return policy?"],
            )
        return AgentResult(
            success=True, summary=ans["answer"], sources=ans.get("sources", []), data={"grounded": True, "max_score": ans.get("max_score")}
        )

    async def _escalate(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        res = await run.call("customer_support", "escalate", {"summary": task.message or "Customer asked for a human"})
        if not res.success:
            return AgentResult(
                success=False, summary="I couldn't create a support ticket. Please email support@nextbot.local.", error=res.error
            )
        ticket = res.data.get("ticket")
        await run.call("email", "send", {"template": "support_escalation", "context": {"name": ctx.principal.name, "ticket": ticket}})
        return AgentResult(
            success=True,
            data=res.data,
            summary=f"I've passed this to our support team (ticket {ticket}). A specialist will reply within 4 working hours.",
        )
