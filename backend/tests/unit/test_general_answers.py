"""Open (non-store) questions: answered by the configured model; store answers still come from agents/RAG."""

import pytest

from app.agents.intent import IntentResult, RuleBasedIntentParser
from app.integrations.llm.openai_provider import provider_name
from tests.unit.harness import make_harness

pytestmark = pytest.mark.anyio


class FakeGemini:
    name, is_mock = "gemini", False

    def __init__(self) -> None:
        self.rules = RuleBasedIntentParser()
        self.general_calls: list[str] = []

    async def classify(self, message, history, memory):
        if "photosynthesis" in message.lower():
            return IntentResult(intent="general", entities={}, confidence=0.9)
        return self.rules.parse(message)

    async def compose(self, message, intent, outputs):
        return "COMPOSED"  # would overwrite agent text; general answers must bypass it

    async def grounded_answer(self, question, contexts):
        return None if "return" in question.lower() else "NO_ANSWER"  # like the real model reading irrelevant chunks

    async def general_answer(self, question, history):
        self.general_calls.append(question)
        return "**Photosynthesis turns light into chemical energy.**\n- Happens in chloroplasts\n- Produces oxygen"


async def test_general_question_answered_by_model_as_bullets():
    h, _ = await make_harness()
    h.llm = FakeGemini()
    res = await h.chat("Explain photosynthesis simply")
    assert res.success and res.summary.startswith("**Photosynthesis") and "\n- " in res.summary
    assert res.data["intent"] == "general" and h.llm.general_calls == ["Explain photosynthesis simply"]


async def test_unknown_question_falls_back_to_model_when_not_in_knowledge_base():
    h, _ = await make_harness()
    h.llm = FakeGemini()
    res = await h.chat("What is the capital of France?")  # rules -> faq, KB has no answer -> model
    assert h.llm.general_calls and "Photosynthesis" in res.summary


async def test_store_policy_still_grounded_in_knowledge_base():
    h, _ = await make_harness()
    h.llm = FakeGemini()
    res = await h.chat("What is your return policy?")
    assert "10 days" in res.summary or res.summary == "COMPOSED"  # grounded path, model not asked for general text
    assert h.llm.general_calls == []


async def test_demo_mode_does_not_invent_answers():
    h, _ = await make_harness()  # MockLLMProvider
    res = await h.chat("Who wrote the Indian national anthem?")
    assert "Photosynthesis" not in res.summary and res.data.get("intent") in ("faq", "unknown")


def test_provider_names():
    assert provider_name(None) == "openai"
    assert provider_name("https://generativelanguage.googleapis.com/v1beta/openai/") == "gemini"
    assert provider_name("https://api.groq.com/openai/v1") == "groq"
    assert provider_name("http://host.docker.internal:11434/v1") == "ollama"


async def test_rag_treats_model_no_answer_as_not_grounded():
    """Weak keyword hits must not turn into irrelevant 'answers' when the model says the docs don't cover it."""
    from app.rag.embeddings import HashingEmbedder
    from app.rag.pipeline import KnowledgeDoc, RagPipeline
    from app.rag.vector_store import InMemoryVectorStore

    rag = RagPipeline(HashingEmbedder(384), InMemoryVectorStore(), top_k=2, min_score=0.0)
    await rag.index([KnowledgeDoc("store", "Store information", "store", "NextBot is an Indian online store in Bengaluru.", "kb/s.md")])
    ans = await rag.answer("Who wrote the Indian national anthem?", llm=FakeGemini())
    assert ans.grounded is False and ans.sources == []
