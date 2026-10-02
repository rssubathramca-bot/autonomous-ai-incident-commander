from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingProvider(Protocol):
    """Replaceable interface for local or future approved embedding providers."""

    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    """Runs the BGE sentence-embedding model locally on CPU."""

    def __init__(
        self,
        model_name: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "KNOWLEDGE_EMBEDDING_MODEL",
            DEFAULT_MODEL,
        )
        configured_cache = cache_dir or os.getenv(
            "KNOWLEDGE_EMBEDDING_CACHE",
            str(Path.cwd() / ".cache" / "fastembed"),
        )
        self.cache_dir = Path(configured_cache).expanduser()
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
                threads=max(1, min(os.cpu_count() or 1, 4)),
                providers=["CPUExecutionProvider"],
            )
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [
            [float(value) for value in vector]
            for vector in self._get_model().embed(texts)
        ]
        self._validate_vectors(vectors, expected_count=len(texts))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([f"{QUERY_PREFIX}{text.strip()}"])
        if not vectors:
            raise ValueError("Embedding provider returned no query vector.")
        return vectors[0]

    @staticmethod
    def _validate_vectors(
        vectors: list[list[float]],
        *,
        expected_count: int,
    ) -> None:
        if len(vectors) != expected_count:
            raise ValueError("Embedding provider returned an unexpected vector count.")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) > 1 or any(not vector for vector in vectors):
            raise ValueError("Embedding provider returned inconsistent vector dimensions.")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("Embedding provider returned a non-finite vector value.")


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    return FastEmbedProvider()
