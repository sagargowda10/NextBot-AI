"""Supervisor control flow as a LangGraph `StateGraph`.

    START → guard ──blocked──▶ synthesize → END
              │
              ▼
           classify → route → execute_group ──more groups──┐
                                   ▲                       │
                                   └───────────────────────┘
                                   │ done / halted
                                   ▼
                               synthesize → END

If `langgraph` is not installed (e.g. a minimal CI image), `FallbackGraph` runs the *same node
functions* with the same edges, so behaviour is identical and fully testable.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypedDict

from app.agents.base import AgentResult, AgentRunContext, AgentTask
from app.core.logging import get_logger
from app.security.prompt_guard import inspect_message

if TYPE_CHECKING:
    from app.agents.supervisor import PlanStep, SupervisorAgent

log = get_logger("orchestration")


class SupervisorState(TypedDict, total=False):
    message: str
    ctx: AgentRunContext
    forced_intent: str | None
    blocked: bool
    guard_flags: list[str]
    intent: str
    entities: dict[str, Any]
    steps: list[Any]  # list[PlanStep]
    group_index: int
    results: list[AgentResult]
    halted: bool
    reply: str


def build_nodes(sup: SupervisorAgent) -> dict[str, Any]:
    async def guard(state: SupervisorState) -> SupervisorState:
        g = inspect_message(state["message"])
        if g.flags:
            log.warning("prompt_guard_flagged", extra={"flags": g.flags})
        if not g.allowed:
            return {"blocked": True, "guard_flags": g.flags, "intent": "blocked", "reply": g.refusal or "", "results": []}
        return {"blocked": False, "guard_flags": g.flags, "message": g.sanitized}

    async def classify(state: SupervisorState) -> SupervisorState:
        ctx = state["ctx"]
        if state.get("forced_intent"):
            from app.agents.intent import extract_entities

            return {"intent": state["forced_intent"] or "unknown", "entities": extract_entities(state["message"])}
        res = await ctx.llm.classify(state["message"], ctx.extras.get("history", []), ctx.memory)
        return {"intent": res.intent, "entities": res.entities}

    async def route(state: SupervisorState) -> SupervisorState:
        intent = state["intent"]
        steps = [] if intent == "greeting" else sup.plan(intent)
        state["ctx"].memory["last_intent"] = intent
        return {"steps": steps, "group_index": 0, "results": [], "halted": False}

    async def execute_group(state: SupervisorState) -> SupervisorState:
        ctx, steps, idx = state["ctx"], state["steps"], state["group_index"]
        groups = sorted({s.group for s in steps})
        current = groups[idx]
        results = list(state.get("results", []))
        params, message = state.get("entities", {}), state["message"]
        runnable = [s for s in steps if s.group == current and (s.when is None or s.when(ctx.memory, params, results))]
        agents = [sup.agents[s.agent] for s in runnable]

        async def run_step(step: PlanStep) -> AgentResult:
            task = AgentTask(intent=step.intent, params={**params, **step.params}, message=message)
            return await sup.agents[step.agent].run(task, ctx)

        if len(runnable) > 1 and all(a.spec.read_only for a in agents):
            outs = list(await asyncio.gather(*(run_step(s) for s in runnable)))  # safe parallel
        else:
            outs = [await run_step(s) for s in runnable]  # sequential (writes involved)
        halted = False
        for step, out in zip(runnable, outs, strict=True):
            results.append(out)
            if out.halt or (step.critical and not out.success):
                halted = True
        return {"results": results, "group_index": idx + 1, "halted": halted}

    async def synthesize(state: SupervisorState) -> SupervisorState:
        if state.get("blocked"):
            return {"reply": state.get("reply", "")}
        if state.get("intent") == "greeting":
            from app.agents.supervisor import GREETING

            return {"reply": GREETING}
        results = state.get("results", [])
        ctx = state["ctx"]
        reply = None
        if ctx.llm is not None and not getattr(ctx.llm, "is_mock", True) and not any(r.data.get("general") for r in results):
            outputs = [{"agent": r.agent, "success": r.success, "summary": r.summary, "data": r.data, "error": r.error} for r in results]
            reply = await ctx.llm.compose(state["message"], state.get("intent", ""), outputs)
        return {"reply": reply or sup.compose(results)}

    return {"guard": guard, "classify": classify, "route": route, "execute_group": execute_group, "synthesize": synthesize}


def after_guard(state: SupervisorState) -> str:
    return "synthesize" if state.get("blocked") else "classify"


def after_route(state: SupervisorState) -> str:
    return "execute_group" if state.get("steps") else "synthesize"


def after_execute(state: SupervisorState) -> str:
    total_groups = len({s.group for s in state.get("steps", [])})
    if state.get("halted") or state.get("group_index", 0) >= total_groups:
        return "synthesize"
    return "execute_group"


class FallbackGraph:
    """Minimal executor with LangGraph-compatible `ainvoke` semantics (state merge per node)."""

    def __init__(self, nodes: dict[str, Any]) -> None:
        self.nodes = nodes
        self.edges = {
            "guard": after_guard,
            "classify": lambda s: "route",
            "route": after_route,
            "execute_group": after_execute,
            "synthesize": lambda s: "__end__",
        }

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current, steps = "guard", 0
        while current != "__end__":
            steps += 1
            if steps > 50:  # recursion limit, as in LangGraph
                raise RuntimeError("graph recursion limit reached")
            state = {**state, **(await self.nodes[current](state))}
            current = self.edges[current](state)
        return state


def build_supervisor_graph(sup: SupervisorAgent) -> Any:
    nodes = build_nodes(sup)
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        log.info("langgraph_not_installed_using_fallback_graph")
        return FallbackGraph(nodes)
    g = StateGraph(SupervisorState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", after_guard, {"synthesize": "synthesize", "classify": "classify"})
    g.add_edge("classify", "route")
    g.add_conditional_edges("route", after_route, {"execute_group": "execute_group", "synthesize": "synthesize"})
    g.add_conditional_edges("execute_group", after_execute, {"execute_group": "execute_group", "synthesize": "synthesize"})
    g.add_edge("synthesize", END)
    return g.compile()
