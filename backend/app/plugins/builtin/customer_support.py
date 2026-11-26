"""Plugin 7 — Customer Support: RAG answers over the knowledge base, FAQs, human escalation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.plugins.base import BasePlugin, NoInput, PluginContext, action


class AnswerIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    category: str | None = Field(None, max_length=40)


class EscalateIn(BaseModel):
    summary: str = Field(min_length=3, max_length=1000)


class CustomerSupportPlugin(BasePlugin):
    plugin_id = "customer_support"
    name = "Customer Support"
    version = "1.2.0"
    description = "Grounded answers from the knowledge base (RAG) with sources, FAQs and escalation to human support."
    default_config = {"escalation_email": "support@nextbot.local"}

    @action("answer", AnswerIn, "support:use", "Answer a question from the knowledge base with sources")
    async def answer(self, p: AnswerIn, ctx: PluginContext) -> dict:
        return (await ctx.services.support.answer(p.question, p.category)).model_dump(mode="json")

    @action("faqs", NoInput, "support:use", "Frequently asked questions")
    async def faqs(self, p: NoInput, ctx: PluginContext) -> dict:
        return {"items": await ctx.services.support.faqs()}

    @action("escalate", EscalateIn, "support:use", "Hand the conversation to a human support agent")
    async def escalate(self, p: EscalateIn, ctx: PluginContext) -> dict:
        return await ctx.services.support.escalate(ctx.principal, ctx.conversation_id, p.summary)
