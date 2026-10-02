from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentMetadata(KnowledgeSchema):
    document_id: str = Field(min_length=1, max_length=120)
    document_type: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    created_at: datetime
    tags: list[str] = Field(default_factory=list, max_length=30)
    synthetic: Literal[True]


class KnowledgeFile(KnowledgeSchema):
    metadata: DocumentMetadata
    content: str = Field(min_length=20, max_length=100_000)


class SearchRequest(KnowledgeSchema):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query must contain non-whitespace text.")
        return cleaned


class DocumentListItem(KnowledgeSchema):
    document_id: str
    document_type: str
    title: str
    service: str
    source: str
    version: str
    created_at: datetime
    tags: list[str]
    synthetic: bool
    chunk_count: int


class ChunkResult(KnowledgeSchema):
    chunk_id: str
    document_id: str
    document_title: str
    document_type: str
    service: str
    source: str
    text: str
    metadata: dict[str, Any]


class DocumentDetail(DocumentListItem):
    content: str
    chunks: list[ChunkResult]


class SearchResult(ChunkResult):
    title: str
    similarity_score: float


class SearchResponse(KnowledgeSchema):
    query: str
    results: list[SearchResult]


class IndexResponse(KnowledgeSchema):
    documents_indexed: int
    chunks_indexed: int
    embedding_model: str
