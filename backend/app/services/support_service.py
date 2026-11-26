from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state import AppState
from app.models.ai import Conversation
from app.models.platform import Notification
from app.schemas.platform import GroundedAnswer
from app.security.permissions import Principal

KB_CATEGORIES = ["returns", "shipping", "payments", "warranty", "store", "orders", "account", "general"]

FAQS = [
    {"q": "What is the return window?", "a": "10 days from delivery for most items."},
    {"q": "Is shipping free?", "a": "Yes, on orders of ₹999 or more after discounts; otherwise ₹79."},
    {"q": "My payment failed but money was deducted", "a": "Banks reverse failed debits within 5–7 working days."},
    {"q": "Can I cancel after packing?", "a": "No — cancel before packing, or request a return after delivery."},
]


class SupportService:
    def __init__(self, session: AsyncSession, state: AppState) -> None:
        self.session, self.state = session, state

    async def answer(self, question: str, category: str | None = None) -> GroundedAnswer:
        filters = {"category": category} if category else {"category": KB_CATEGORIES}  # never answer policy from product blurbs
        return await self.state.rag.answer(question, llm=self.state.llm, filters=filters)

    async def faqs(self) -> list[dict[str, str]]:
        return FAQS

    async def escalate(self, principal: Principal, conversation_id: int | None, summary: str) -> dict[str, Any]:
        ticket = f"SUP-{conversation_id or 0:05d}-{secrets.token_hex(2).upper()}"
        if conversation_id:
            conv = await self.session.get(Conversation, conversation_id)
            if conv is not None and conv.user_id == principal.user_id:
                conv.status = "ESCALATED"
        self.session.add(
            Notification(
                user_id=None,
                channel="INTERNAL",
                template="support_escalation",
                recipient="support-queue",
                subject=f"Escalation {ticket} from {principal.email}",
                body=summary[:2000],
                status="QUEUED",
                meta={"ticket": ticket, "conversation_id": conversation_id, "user_id": principal.user_id},
            )
        )
        await self.session.flush()
        return {"ticket": ticket, "status": "OPEN"}
