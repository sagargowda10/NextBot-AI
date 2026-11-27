"""Embedding providers.

`HashingEmbedder` is a deterministic, dependency-free embedding (signed feature hashing of
stemmed unigrams + bigrams, L2-normalised). It is not a neural model, but it gives real vector
similarity search for demo mode and tests. `OpenAIEmbedder` uses text-embedding-3-small with the
`dimensions` parameter so both providers produce vectors of the same size for pgvector.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Protocol

_STOP = frozenset(
    "a an and are as at be by can do does for from have how i in is it me my of on or our "
    "the this to was what when where which who will with you your we us".split()
)
_TOKEN = re.compile(r"[a-z0-9₹]+")


def _stem(tok: str) -> str:
    for suf in ("ing", "ies", "ed", "es", "s"):
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class Embedder(Protocol):
    dim: int
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        toks = tokenize(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for f in feats:
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign * (1.5 if "_" in f else 1.0)
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str, model: str, dim: int = 384) -> None:
        from openai import AsyncOpenAI

        self.client: Any = AsyncOpenAI(api_key=api_key, timeout=20)
        self.model, self.dim = model, dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=self.model, input=texts, dimensions=self.dim)
        return [d.embedding for d in resp.data]


class FallbackEmbedder:
    """OpenAI embeddings with a safe fallback to the local HashingEmbedder.

    If OpenAI fails *before it has ever succeeded* (no credit, revoked key, offline), switch permanently to the
    local embedder so the app still starts and indexing + queries stay in the same vector space. Once OpenAI vectors
    are stored, a later failure is raised instead: mixing vector spaces would silently return wrong documents.
    """

    def __init__(self, primary: Embedder, fallback: Embedder) -> None:
        self.primary, self.fallback = primary, fallback
        self.dim = primary.dim
        self.using_fallback = False
        self.primary_ok = False
        self.fallback_reason: str | None = None

    @property
    def name(self) -> str:
        return self.fallback.name if self.using_fallback else self.primary.name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.using_fallback:
            return await self.fallback.embed(texts)
        try:
            vecs = await self.primary.embed(texts)
        except Exception as exc:
            if self.primary_ok:
                raise
            self.using_fallback, self.fallback_reason = True, type(exc).__name__
            from app.core.logging import get_logger

            get_logger("rag").warning("openai_embeddings_unavailable_using_local", extra={"error": self.fallback_reason})
            return await self.fallback.embed(texts)
        self.primary_ok = True
        return vecs


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
