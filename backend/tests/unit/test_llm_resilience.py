"""A hanging/unreachable AI provider must never freeze chat: fail fast, cool down, fall back to rules."""

import pytest

from app.agents.intent import RuleBasedIntentParser
from app.integrations.llm.openai_provider import OpenAIProvider

pytestmark = pytest.mark.anyio


class APITimeoutError(Exception):  # same class name the openai SDK raises
    pass


class Completions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        raise APITimeoutError("timed out")


class FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": Completions()})()


def provider(name: str = "gemini") -> OpenAIProvider:
    p = OpenAIProvider.__new__(OpenAIProvider)  # skip the real SDK client
    p.client, p.name, p.model, p.fallback, p._down_until = FakeClient(), name, "m", RuleBasedIntentParser(), 0.0
    return p


async def test_timeout_falls_back_to_rules_and_cools_down():
    p = provider()
    r1 = await p.classify("cheapest laptop", [], {})
    assert r1.intent == "product_search" and r1.entities["sort"] == "price_asc"  # rules answered
    calls = p.client.chat.completions.calls
    assert len(calls) == 1 and calls[0]["timeout"] == 8 and calls[0]["reasoning_effort"] == "low"
    await p.classify("track my order", [], {})
    assert await p.general_answer("hi", []) is None and await p.compose("m", "faq", []) is None
    assert len(calls) == 1  # cooling down: no more waiting on the provider


async def test_openai_does_not_get_gemini_only_params():
    p = provider("openai")
    await p.classify("hello", [], {})
    assert "reasoning_effort" not in p.client.chat.completions.calls[0]
