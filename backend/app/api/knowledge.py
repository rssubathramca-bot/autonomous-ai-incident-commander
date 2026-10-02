from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentMetadata
from ..db.session import get_db
from ..knowledge.embeddings import get_embedding_provider
from ..knowledge.schemas import (
    ChunkResult,
    DocumentDetail,
    DocumentListItem,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from ..knowledge.service import (
    KnowledgeIndexError,
    index_knowledge_documents,
    search_knowledge_chunks,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _utc_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _metadata_dict(metadata: KnowledgeDocumentMetadata) -> dict[str, Any]:
    return {
        "document_id": metadata.document_id,
        "document_type": metadata.document.document_type,
        "title": metadata.document.title,
        "service": metadata.service,
        "source": metadata.document.source,
        "version": metadata.version,
        "created_at": _utc_datetime(metadata.document_created_at),
        "tags": metadata.tags,
        "synthetic": metadata.synthetic,
    }


def _list_item(
    db: Session,
    metadata: KnowledgeDocumentMetadata,
) -> DocumentListItem:
    count = db.scalar(
        select(func.count(KnowledgeChunk.id)).where(
            KnowledgeChunk.knowledge_document_id == metadata.knowledge_document_id
        )
    )
    return DocumentListItem(**_metadata_dict(metadata), chunk_count=count or 0)


def _chunk_result(chunk: KnowledgeChunk) -> ChunkResult:
    details = chunk.chunk_metadata
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        document_id=details["document_id"],
        document_title=details["document_title"],
        document_type=details["document_type"],
        service=details["service"],
        source=details["source"],
        text=chunk.text,
        metadata=details,
    )


@router.post(
    "/index",
    response_model=IndexResponse,
    status_code=status.HTTP_200_OK,
)
def index_knowledge(db: Session = Depends(get_db)) -> IndexResponse:
    provider = get_embedding_provider()
    try:
        document_count, chunk_count = index_knowledge_documents(db, provider)
        db.commit()
    except Exception as error:
        db.rollback()
        logger.exception("Knowledge indexing failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge indexing failed; check the local embedding model and documents.",
        ) from error
    return IndexResponse(
        documents_indexed=document_count,
        chunks_indexed=chunk_count,
        embedding_model=provider.model_name,
    )


@router.post("/search", response_model=SearchResponse)
def search_knowledge(
    data: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    provider = get_embedding_provider()
    try:
        matches = search_knowledge_chunks(
            db,
            provider,
            query=data.query,
            top_k=data.top_k,
        )
    except KnowledgeIndexError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        logger.exception("Knowledge search failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local knowledge search is unavailable.",
        ) from error

    results = [
        SearchResult(
            **_chunk_result(chunk).model_dump(),
            title=chunk.chunk_metadata["title"],
            similarity_score=round(score, 6),
        )
        for chunk, score in matches
    ]
    return SearchResponse(query=data.query, results=results)


@router.get("/documents", response_model=list[DocumentListItem])
def list_knowledge_documents(
    db: Session = Depends(get_db),
) -> list[DocumentListItem]:
    metadata_rows = db.scalars(
        select(KnowledgeDocumentMetadata)
        .join(KnowledgeDocument)
        .order_by(KnowledgeDocumentMetadata.document_id)
    ).all()
    return [_list_item(db, metadata) for metadata in metadata_rows]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
)
def get_knowledge_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentDetail:
    metadata = db.scalar(
        select(KnowledgeDocumentMetadata).where(
            KnowledgeDocumentMetadata.document_id == document_id
        )
    )
    if metadata is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")

    document = metadata.document
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.knowledge_document_id == document.id)
        .order_by(KnowledgeChunk.chunk_index)
    ).all()
    return DocumentDetail(
        **_list_item(db, metadata).model_dump(),
        content=document.content,
        chunks=[_chunk_result(chunk) for chunk in chunks],
    )
