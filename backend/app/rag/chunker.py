"""Markdown-aware text chunking with overlap.

Headings are glued to the paragraph that follows them (so a chunk never consists of a lone
heading), paragraphs are packed into ~`chunk_size`-character windows across section boundaries,
oversized paragraphs are split on sentence boundaries, and consecutive chunks share `overlap`
characters of context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_HEADING = re.compile(r"#{1,6} .+")


@dataclass
class Chunk:
    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


def _blocks(text: str) -> list[str]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    raw = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    merged: list[str] = []
    pending = ""
    for b in raw:
        if _HEADING.fullmatch(b):
            pending = f"{pending}\n{b}".strip()
            continue
        merged.append(f"{pending}\n{b}".strip() if pending else b)
        pending = ""
    if pending:
        merged.append(pending)
    return merged


def split_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be larger than overlap")
    pieces: list[str] = []
    for block in _blocks(text):
        while len(block) > chunk_size:
            cut = block.rfind(". ", 0, chunk_size)
            cut = cut + 1 if cut > chunk_size // 2 else chunk_size
            pieces.append(block[:cut].strip())
            block = block[max(0, cut - overlap) :].strip()
        pieces.append(block)
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > chunk_size:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            tail = tail.split(" ", 1)[-1] if " " in tail else ""
            buf = f"{tail}\n\n{piece}".strip() if tail else piece
        else:
            buf = f"{buf}\n\n{piece}" if buf else piece
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) > 20]


def chunk_document(text: str, metadata: dict[str, Any], chunk_size: int = 600, overlap: int = 80) -> list[Chunk]:
    return [Chunk(text=t, index=i, metadata=dict(metadata)) for i, t in enumerate(split_text(text, chunk_size, overlap))]
