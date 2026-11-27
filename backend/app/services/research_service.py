"""Admin AI Research assistant: web-search answers with citations, optionally grounded in live store numbers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimited
from app.core.state import AppState
from app.integrations.llm.research import ResearchResult
from app.security.permissions import Principal
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import audit

STORE_HINT = re.compile(
    r"\b(our|my|store|shop|nextbot|sales?|revenue|orders?|returns?|refunds?|stock|inventory|customers?|products?|aov|best.?sell)",
    re.I,
)


def openai_problem(exc: Exception) -> str:
    kind = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if kind == "AuthenticationError" or status == 401:
        return "OpenAI rejected the API key (revoked or mistyped). Create a new key and update OPENAI_API_KEY in .env."
    if kind == "RateLimitError" or status == 429:
        return "OpenAI refused the request: no credit left or rate limit hit. Add credits at platform.openai.com -> Billing."
    if kind in ("NotFoundError", "BadRequestError") or status in (400, 404):
        return "OpenAI didn't accept the model name. Check OPENAI_MODEL / OPENAI_RESEARCH_MODEL in .env."
    return f"OpenAI request failed ({kind}). Showing store data only."


class ResearchService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def store_snapshot(self) -> dict[str, Any]:
        a = AnalyticsService(self.session, self.state)
        month = await a.sales_summary("last 30 days")
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "sales_last_30_days": {
                "revenue_inr": str(month.revenue),
                "orders": month.orders,
                "average_order_value_inr": str(month.average_order_value),
                "by_day": month.by_day[-14:],
            },
            "orders_by_status": (await a.order_stats())["by_status"],
            "top_products": await a.product_performance(5),
            "inventory": await a.inventory_insights(int(self.state.settings.low_stock_threshold)),
        }

    async def ask(
        self, principal: Principal, question: str, history: list[dict[str, str]], use_web: bool, include_store: str
    ) -> dict[str, Any]:
        s = self.state.settings
        day = datetime.now(UTC).strftime("%Y%m%d")
        used = await self.state.cache.incr_window(f"research:day:{principal.user_id}:{day}", 86400)
        if used > s.research_daily_limit:
            raise RateLimited(f"Daily research limit reached ({s.research_daily_limit} questions)")

        want_store = include_store == "always" or (include_store == "auto" and bool(STORE_HINT.search(question)))
        snapshot = await self.store_snapshot() if want_store else None
        client = self.state.research
        if client is None:
            result = self._demo_answer(question, snapshot)
            provider = "mock"
        else:
            try:
                result = await client.ask(question, history, json.dumps(snapshot, default=str) if snapshot else None, use_web)
                provider = client.name
            except Exception as exc:  # no credit / revoked key / outage: answer from store data and say why
                result = self._demo_answer(question, snapshot)
                result.notice = openai_problem(exc)
                provider = "mock"
        await audit(
            self.session, principal, "research.ask", "research", None,
            {"chars": len(question), "web": result.web_used, "store": bool(snapshot), "provider": provider},
        )  # fmt: skip
        return {
            "answer": result.text or "No answer was returned.",
            "citations": result.citations,
            "sources": result.sources,
            "web_used": result.web_used,
            "store_used": bool(snapshot),
            "provider": provider,
            "model": result.model,
            "notice": result.notice,
            "remaining_today": max(0, s.research_daily_limit - used),
        }

    @staticmethod
    def _demo_answer(question: str, snap: dict[str, Any] | None) -> ResearchResult:
        notice = "Demo mode: set OPENAI_API_KEY to enable ChatGPT answers with live web search."
        if not snap:
            return ResearchResult(
                text="**Web research needs an OpenAI API key.**\n"
                "- This answer comes from demo mode, so nothing was searched.\n"
                "- Add `OPENAI_API_KEY` to `.env` and restart the backend to get web answers with sources.\n"
                "- Questions about your store (sales, orders, stock, returns) already work in demo mode.",
                model="demo",
                notice=notice,
            )
        m, inv = snap["sales_last_30_days"], snap["inventory"]
        top = ", ".join(f"{p['name']} ({p['units']} units)" for p in snap["top_products"][:3]) or "no sales yet"
        status = ", ".join(f"{k.replace('_', ' ').lower()}: {v}" for k, v in snap["orders_by_status"].items()) or "none"
        return ResearchResult(
            text=f"**Store snapshot (last 30 days) from the NextBot database.**\n"
            f"- Revenue: ₹{m['revenue_inr']} from {m['orders']} paid orders (average ₹{m['average_order_value_inr']}).\n"
            f"- Orders by status: {status}.\n"
            f"- Top sellers: {top}.\n"
            f"- Inventory: {inv['units_on_hand']} units on hand, {inv['low_stock']} low-stock and {inv['out_of_stock']} "
            f"out-of-stock SKU locations.\n"
            f"- Demo mode can't interpret the question ('{question[:80]}') - add an OpenAI key for a written analysis.",
            model="demo",
            notice=notice,
        )
