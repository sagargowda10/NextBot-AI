import pytest

from app.rag.embeddings import FallbackEmbedder, HashingEmbedder

pytestmark = pytest.mark.anyio


class Broken:
    dim, name = 384, "openai"

    async def embed(self, texts):
        raise RuntimeError("insufficient_quota")


class Flaky:
    """Works once, then fails (e.g. credit runs out after indexing)."""

    dim, name = 384, "openai"

    def __init__(self):
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("insufficient_quota")
        return [[1.0] + [0.0] * 383 for _ in texts]


async def test_switches_to_local_embedder_when_openai_never_worked():
    e = FallbackEmbedder(Broken(), HashingEmbedder(384))
    vecs = await e.embed(["return policy"])  # startup indexing must not crash
    assert len(vecs[0]) == 384 and e.using_fallback and e.name == "hashing-v1" and e.fallback_reason == "RuntimeError"
    assert await e.embed(["return policy"]) == vecs  # queries stay in the same (local) vector space


async def test_does_not_mix_vector_spaces_after_openai_succeeded():
    e = FallbackEmbedder(Flaky(), HashingEmbedder(384))
    await e.embed(["indexed with openai"])
    with pytest.raises(RuntimeError):
        await e.embed(["query"])
    assert not e.using_fallback
