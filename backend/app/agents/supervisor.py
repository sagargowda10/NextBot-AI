"""Agent 1 — Supervisor Agent.

Receives the customer message, classifies intent (LLM or rules), selects specialised agents via a
policy-controlled plan, executes plan groups (sequential groups; safe parallelism inside a group
when every agent in it is read-only), handles failures, and composes the final response.
The control flow itself is a LangGraph state machine (see `app/orchestration/graph.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import AgentResult, AgentRun, AgentRunContext, AgentSpec, AgentTask, BaseAgent

Cond = Callable[[dict[str, Any], dict[str, Any], list[AgentResult]], bool]


@dataclass(frozen=True)
class PlanStep:
    agent: str
    intent: str
    group: int = 0
    critical: bool = True
    when: Cond | None = None
    params: dict[str, Any] = field(default_factory=dict)


def _has_products(_m: dict[str, Any], _p: dict[str, Any], results: list[AgentResult]) -> bool:
    return bool(results) and results[0].success and bool(results[0].products)


def _wants_delivery(_m: dict[str, Any], p: dict[str, Any], results: list[AgentResult]) -> bool:
    return bool(p.get("wants_delivery") or p.get("pincode")) and _has_products(_m, p, results)


def _prev_ok_no_approval(_m: dict[str, Any], _p: dict[str, Any], results: list[AgentResult]) -> bool:
    return bool(results) and results[-1].success and not results[-1].requires_approval


def _payment_ok(_m: dict[str, Any], _p: dict[str, Any], results: list[AgentResult]) -> bool:
    return any(r.agent == "payment" and r.success and "payment" in r.data for r in results)


PLANS: dict[str, list[PlanStep]] = {
    "product_search": [
        PlanStep("shopping", "product_search"),
        PlanStep("inventory", "check_results", 1, False, _has_products),
        PlanStep("logistics", "delivery_estimate", 1, False, _wants_delivery),
    ],
    "recommend": [PlanStep("product_intelligence", "recommend"), PlanStep("inventory", "check_results", 1, False, _has_products)],
    "product_details": [PlanStep("product_intelligence", "product_details")],
    "compare_products": [PlanStep("product_intelligence", "compare_products")],
    "add_to_cart": [PlanStep("shopping", "add_to_cart")],
    "view_cart": [PlanStep("shopping", "view_cart")],
    "remove_from_cart": [PlanStep("shopping", "remove_from_cart")],
    "checkout": [
        PlanStep("fraud_detection", "assess_checkout", 0, False),
        PlanStep("order_management", "checkout", 1),
        PlanStep("payment", "pay", 2),
        PlanStep("logistics", "create_shipment", 3, False, _payment_ok),
        PlanStep("notification", "checkout", 4, False, _payment_ok),
    ],
    "track_order": [PlanStep("order_management", "track_order"), PlanStep("logistics", "track_order", 1, False)],
    "order_history": [PlanStep("order_management", "order_history")],
    "cancel_order": [PlanStep("order_management", "cancel_order")],
    "return_request": [
        PlanStep("return_refund", "return_request"),
        PlanStep(
            "notification",
            "return_request",
            1,
            False,
            _prev_ok_no_approval,
            {"template": "return_update", "context": {"status": "approved", "message": "A pickup will be scheduled in 1-2 days."}},
        ),
    ],
    "return_status": [PlanStep("return_refund", "return_status")],
    "faq": [PlanStep("customer_support", "faq")],
    "unknown": [PlanStep("customer_support", "faq")],
    "escalate": [PlanStep("customer_support", "escalate")],
    "payment_issue": [PlanStep("payment", "payment_issue"), PlanStep("customer_support", "faq", 1, False)],
    "delivery_estimate": [PlanStep("logistics", "delivery_estimate")],
    "low_stock": [PlanStep("inventory", "low_stock")],
    "inventory_check": [PlanStep("inventory", "inventory_check")],
    "sales_report": [PlanStep("analytics", "sales_report")],
    "plugin_status": [PlanStep("analytics", "plugin_status")],
    "agent_executions": [PlanStep("analytics", "agent_executions")],
}

GREETING = (
    "Hi! I'm NextBot, your AI shopping assistant. I can find products, compare them, manage your cart, "
    "place and track orders, handle returns and answer store-policy questions."
)
DEFAULT_SUGGESTIONS = [
    "Find me a laptop under ₹60,000",
    "Show me black running shoes in size 9",
    "Track my latest order",
    "What is your return policy?",
]


class SupervisorAgent(BaseAgent):
    spec = AgentSpec(
        name="supervisor",
        display_name="Supervisor Agent",
        description="Classifies intent, plans and delegates to specialised agents (sequential or safe-parallel), "
        "handles failures and composes the final answer. Has no direct tool access.",
        tools=frozenset(),
        max_iterations=8,  # max plan steps per message
        timeout_s=30.0,
    )

    def __init__(self, agents: dict[str, BaseAgent]) -> None:
        self.agents = agents
        from app.orchestration.graph import build_supervisor_graph

        self.graph = build_supervisor_graph(self)

    def plan(self, intent: str) -> list[PlanStep]:
        steps = PLANS.get(intent, PLANS["unknown"])
        return steps[: self.spec.max_iterations]

    async def handle(self, task: AgentTask, ctx: AgentRunContext, run: AgentRun) -> AgentResult:
        state = await self.graph.ainvoke(
            {
                "message": task.message,
                "ctx": ctx,
                "results": [],
                "group_index": 0,
                "halted": False,
                "forced_intent": task.params.get("forced_intent"),
            }
        )
        results: list[AgentResult] = state.get("results", [])
        return AgentResult(
            success=all(r.success for r in results) if results else True,
            summary=state.get("reply", ""),
            data={
                "intent": state.get("intent", "unknown"),
                "entities": state.get("entities", {}),
                "steps": [r.model_dump() for r in results],
                "blocked": state.get("blocked", False),
            },
            products=next((r.products for r in results if r.products), []),
            sources=[s for r in results for s in r.sources],
            suggestions=next(
                (r.suggestions for r in reversed(results) if r.suggestions),
                DEFAULT_SUGGESTIONS if state.get("intent") in ("greeting", "unknown") else [],
            ),
            requires_approval=any(r.requires_approval for r in results),
        )

    @staticmethod
    def compose(results: list[AgentResult]) -> str:
        parts = [r.summary.strip() for r in results if r.summary and r.summary.strip()]
        return "\n\n".join(parts) if parts else "Sorry, I couldn't complete that. Could you rephrase?"
