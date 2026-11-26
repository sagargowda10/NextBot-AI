import math

import pytest

from app.rag.chunker import split_text
from app.rag.embeddings import HashingEmbedder, cosine
from app.rag.pipeline import FALLBACK, RagPipeline, load_markdown_docs
from app.rag.vector_store import InMemoryVectorStore

pytestmark = pytest.mark.anyio


def test_chunker_glues_headings_respects_size_and_overlaps():
    text = "<!-- category: x -->\n# Title\n\n## A\n\n" + ("Sentence number one is here. " * 40) + "\n\n## B\n\nShort tail paragraph here."
    chunks = split_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 2 and not any(c.strip().startswith("<!--") for c in chunks)
    assert chunks[0].startswith("# Title\n## A")
    assert all(len(c) <= 300 + 60 for c in chunks)
    assert chunks[1][:20] in chunks[0] or chunks[1].split()[0] in chunks[0]  # overlap carried over
    with pytest.raises(ValueError):
        split_text("x", chunk_size=10, overlap=10)


async def test_hashing_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder(384)
    [a, b, c] = await e.embed(["return policy window", "return policy window", "gaming laptop RAM"])
    assert a == b and math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    assert cosine(a, b) > 0.99 and cosine(a, c) < 0.3


async def pipeline() -> RagPipeline:
    p = RagPipeline(HashingEmbedder(384), InMemoryVectorStore(), chunk_size=600, overlap=80, top_k=4, min_score=0.10)
    n = await p.index(load_markdown_docs())
    assert n >= 7
    return p


@pytest.mark.parametrize(
    "question,expected_doc,fact",
    [
        ("What is your return policy?", "return-policy", "10 days"),
        ("My payment failed but money was deducted", "payment-faq", "5 to 7 working days"),
        ("What warranty do laptops have?", "warranty", "one-year"),
        ("Is shipping free?", "shipping-policy", "₹999"),
        ("Can I cancel my order after it is packed?", "order-cancellation", "packed"),
    ],
)
async def test_retrieval_and_grounded_answer(question, expected_doc, fact):
    p = await pipeline()
    ans = await p.answer(question)
    assert ans.grounded and ans.sources[0]["id"].startswith(expected_doc)
    assert fact in ans.answer and "[1]" in ans.answer


async def test_metadata_filtering():
    p = await pipeline()
    hits = await p.retrieve("refund timelines", filters={"category": "payments"})
    assert hits and {h.chunk.metadata["category"] for h in hits} == {"payments"}


async def test_unknown_question_returns_fallback_not_invention():
    p = await pipeline()
    ans = await p.answer("What is the melting point of tungsten carbide?")
    assert not ans.grounded and ans.answer == FALLBACK and ans.sources == []
