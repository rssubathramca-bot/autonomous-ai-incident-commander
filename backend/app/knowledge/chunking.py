from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from .documents import LoadedDocument


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    chunk_index: int
    text: str
    metadata: dict[str, Any]


def chunk_document(
    document: LoadedDocument,
    *,
    chunk_size_words: int | None = None,
    overlap_words: int | None = None,
) -> list[DocumentChunk]:
    chunk_size = (
        int(os.getenv("KNOWLEDGE_CHUNK_SIZE_WORDS", "180"))
        if chunk_size_words is None
        else chunk_size_words
    )
    overlap = (
        int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP_WORDS", "30"))
        if overlap_words is None
        else overlap_words
    )
    if chunk_size < 1:
        raise ValueError("Chunk size must be at least one word.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")

    words = document.data.content.split()
    if not words:
        return []

    metadata = document.data.metadata.model_dump(mode="json")
    step = chunk_size - overlap
    chunks: list[DocumentChunk] = []
    for chunk_index, start in enumerate(range(0, len(words), step)):
        text = " ".join(words[start : start + chunk_size])
        if not text:
            continue
        chunk_id = _chunk_id(metadata["document_id"], chunk_index, text)
        chunk_metadata = {
            **metadata,
            "document_title": metadata["title"],
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
        }
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                text=text,
                metadata=chunk_metadata,
            )
        )
        if start + chunk_size >= len(words):
            break
    return chunks


def _chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{document_id}:{chunk_index:03d}:{digest}"
