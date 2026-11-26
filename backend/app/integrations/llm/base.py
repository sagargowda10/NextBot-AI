"""LLM provider interface. The pipeline never depends on a specific vendor."""

from __future__ import annotations

from typing import Any, Protocol

from app.agents.intent import IntentResult


class LLMProvider(Protocol):
    name: str
    is_mock: bool

    async def classify(self, message: str, history: list[dict[str, str]], memory: dict[str, Any]) -> IntentResult:
        """Return the intent and extracted entities (structured output / function calling)."""

    async def compose(self, message: str, intent: str, agent_outputs: list[dict[str, Any]]) -> str | None:
        """Write the final reply from agent outputs only. None → use the deterministic summary."""

    async def grounded_answer(self, question: str, contexts: list[dict[str, Any]]) -> str | None:
        """Answer strictly from retrieved contexts. None → use the extractive fallback."""
