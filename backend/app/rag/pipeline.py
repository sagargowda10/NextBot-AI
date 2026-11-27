"""RAG pipeline: load → chunk → embed → store → retrieve → generate grounded answer with sources.

Grounding rule: if the best retrieved chunk scores below `min_score`, we return a fallback that
says we don't know and offers a human — we never invent policy text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rag.chunker import chunk_document
from app.rag.embeddings import Embedder, tokenize
from app.rag.vector_store import ScoredChunk, StoredChunk, VectorStore
from app.schemas.platform import GroundedAnswer

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
FALLBACK = (
    "I couldn't find a reliable answer to that in our help centre, so I don't want to guess. "
    "I can connect you with a support specialist — just say “talk to a human”."
)


NO_ANSWER = "NO_ANSWER"  # sentinel a real LLM returns when retrieved documents do not contain the answer


@dataclass
class KnowledgeDoc:
    doc_id: str
    title: str
    category: str
    content: str
    source: str


def load_markdown_docs(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeDoc]:
    docs = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.M)
        meta = re.search(r"^<!--\s*category:\s*([a-z\-]+)\s*-->", text, re.M)
        docs.append(
            KnowledgeDoc(
                doc_id=path.stem,
                title=title_match.group(1).strip() if title_match else path.stem,
                category=meta.group(1) if meta else "general",
                content=text,
                source=f"kb/{path.name}",
            )
        )
    return docs


class RagPipeline:
    def __init__(
        self, embedder: Embedder, store: VectorStore, *, chunk_size: int = 600, overlap: int = 80, top_k: int = 4, min_score: float = 0.10
    ) -> None:
        self.embedder, self.store = embedder, store
        self.chunk_size, self.overlap, self.top_k, self.min_score = chunk_size, overlap, top_k, min_score

    async def index(self, docs: list[KnowledgeDoc]) -> int:
        chunks: list[StoredChunk] = []
        for d in docs:
            parts = chunk_document(d.content, {"category": d.category, "source": d.source}, self.chunk_size, self.overlap)
            vecs = await self.embedder.embed([f"{d.title}\n{c.text}" for c in parts])
            chunks += [
                StoredChunk(
                    id=f"{d.doc_id}:{c.index}",
                    document_id=d.doc_id,
                    title=d.title,
                    content=c.text,
                    embedding=v,
                    metadata={**c.metadata, "chunk_index": c.index},
                )
                for c, v in zip(parts, vecs, strict=True)
            ]
        await self.store.upsert(chunks)
        return len(chunks)

    async def retrieve(self, question: str, k: int | None = None, filters: dict[str, Any] | None = None) -> list[ScoredChunk]:
        """Vector search, then a light lexical re-rank that rewards query terms in the document title."""
        k = k or self.top_k
        [qvec] = await self.embedder.embed([question])
        candidates = await self.store.search(qvec, k * 3, filters)
        q = set(tokenize(question))
        for c in candidates:
            title = set(tokenize(c.chunk.title))
            if q and title:
                c.score += 0.15 * len(q & title) / len(q)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:k]

    async def answer(self, question: str, *, llm: Any = None, filters: dict[str, Any] | None = None) -> GroundedAnswer:
        hits = await self.retrieve(question, filters=filters)
        best = hits[0].score if hits else 0.0
        relevant = [h for h in hits if h.score >= self.min_score]
        if not relevant:
            return GroundedAnswer(answer=FALLBACK, sources=[], grounded=False, max_score=round(best, 3))
        sources = [
            {
                "id": h.chunk.id,
                "title": h.chunk.title,
                "source": h.chunk.metadata.get("source"),
                "score": round(h.score, 3),
                "excerpt": h.chunk.content[:220],
            }
            for h in relevant
        ]
        text = None
        if llm is not None and not getattr(llm, "is_mock", True):
            text = await llm.grounded_answer(question, [{"title": h.chunk.title, "content": h.chunk.content} for h in relevant])
            if text == NO_ANSWER:  # the model read the retrieved documents and they don't answer the question
                return GroundedAnswer(answer=FALLBACK, sources=[], grounded=False, max_score=round(best, 3))
        if text is None:
            text = extractive_answer(question, relevant)
        return GroundedAnswer(answer=text, sources=sources, grounded=True, max_score=round(best, 3))


def extractive_answer(question: str, hits: list[ScoredChunk], max_sentences: int = 4) -> str:
    """Pick the sentences that overlap most with the question, keep document order, cite sources."""
    q = set(tokenize(question))
    candidates: list[tuple[float, int, int, str]] = []
    for doc_rank, h in enumerate(hits[:3]):
        body = re.sub(r"^#+\s.*$", "", h.chunk.content, flags=re.M)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        sentences = [
            s.strip(" -*\n") for s in re.split(r"(?<=[.!?])\s+|\n[-*] ", body) if len(s.strip()) > 25 and s.strip(" -*\n")[:1].isupper()
        ]  # skip overlap fragments
        for pos, s in enumerate(sentences):
            overlap = len(q & set(tokenize(s)))
            candidates.append((overlap + h.score - 0.1 * doc_rank, doc_rank, pos, s))
    best = sorted(candidates, key=lambda c: c[0], reverse=True)[:max_sentences]
    best.sort(key=lambda c: (c[1], c[2]))
    cited = []
    for _, rank, _, s in best:
        sentence = s if s.endswith((".", "!", "?")) else s + "."
        cited.append(f"{sentence} [{rank + 1}]")
    return " ".join(cited)
