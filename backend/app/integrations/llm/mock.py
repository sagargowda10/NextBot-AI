"""Mock AI provider — deterministic, offline, free. Used when AI_PROVIDER=mock (demo mode)."""

from __future__ import annotations

from typing import Any

from app.agents.intent import IntentResult, RuleBasedIntentParser


class MockLLMProvider:
    name = "mock"
    is_mock = True

    def __init__(self) -> None:
        self.parser = RuleBasedIntentParser()

    async def classify(self, message: str, history: list[dict[str, str]], memory: dict[str, Any]) -> IntentResult:
        return self.parser.parse(message)

    async def compose(self, message: str, intent: str, agent_outputs: list[dict[str, Any]]) -> str | None:
        return None  # supervisor stitches agent summaries deterministically

    async def grounded_answer(self, question: str, contexts: list[dict[str, Any]]) -> str | None:
        return None  # RAG pipeline uses extractive answering from the retrieved chunks
