"""Agent 12 — Notification Agent: order, payment, shipment and return updates over email/WhatsApp."""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent, fmt_inr


class NotificationAgent(BaseAgent):
    spec = AgentSpec(
        name="notification",
        display_name="Notification Agent",
        description="Sends order, payment, shipment and return updates on the customer's channels (email, WhatsApp).",
        tools=frozenset({"email.send", "whatsapp.send_template"}),
        max_iterations=4,
    )

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        template = task.params.get("template") or {
            "checkout": "order_confirmation",
            "return_request": "return_update",
            "cancel_order": "shipment_update",
        }.get(task.intent, "generic")
        context: dict[str, Any] = {
            "name": ctx.principal.name or "there",
            "order_number": ctx.memory.get("last_order_number", ""),
            "total": ctx.memory.get("last_order_total", ""),
            **task.params.get("context", {}),
        }
        if context.get("total"):
            context["total"] = fmt_inr(context["total"])
        sent: list[str] = []
        simulated = False
        key = f"{template}:{context['order_number']}" if context.get("order_number") else None
        target = {"user_id": task.params["user_id"]} if task.params.get("user_id") else {}  # honoured only for staff/system callers
        email = await run.call("email", "send", {"template": template, "context": context, "dedupe_key": key, **target})
        if email.success:
            sent.append("email")
            simulated = simulated or bool(email.data.get("simulated"))
        wa = await run.call("whatsapp", "send_template", {"template": template, "context": context, "dedupe_key": key, **target})
        if wa.success:
            sent.append("WhatsApp")
            simulated = simulated or bool(wa.data.get("simulated"))
        if not sent:
            return AgentResult(success=False, summary="", error=email.error or wa.error)
        note = " (demo mode: recorded, not actually sent)" if simulated else ""
        return AgentResult(
            success=True, data={"channels": sent, "template": template}, summary=f"Confirmation sent via {' and '.join(sent)}{note}."
        )
