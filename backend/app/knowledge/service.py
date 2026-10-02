from __future__ import annotations

import math
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
)
from .chunking import DocumentChunk, chunk_document
from .documents import load_knowledge_documents
from .embeddings import EmbeddingProvider


class KnowledgeIndexError(RuntimeError):
    pass


def index_knowledge_documents(
    db: Session,
    embedding_provider: EmbeddingProvider,
) -> tuple[int, int]:
    documents = load_knowledge_documents()
    chunk_groups: list[tuple[object, list[DocumentChunk]]] = [
        (document, chunk_document(document)) for document in documents
    ]
    flattened_chunks = [
        chunk for _, chunks in chunk_groups for chunk in chunks
    ]
    if not flattened_chunks:
        raise KnowledgeIndexError("Knowledge documents produced no indexable chunks.")

    vectors = embedding_provider.embed_documents(
        [chunk.text for chunk in flattened_chunks]
    )
    if len(vectors) != len(flattened_chunks):
        raise KnowledgeIndexError("Embedding provider returned an incomplete index.")
    vector_dimensions = {len(vector) for vector in vectors}
    if len(vector_dimensions) != 1 or not next(iter(vector_dimensions)):
        raise KnowledgeIndexError("Embedding provider returned invalid vector dimensions.")

    vector_by_chunk_id = {
        chunk.chunk_id: vector
        for chunk, vector in zip(flattened_chunks, vectors, strict=True)
    }

    for loaded_document, chunks in chunk_groups:
        metadata = loaded_document.data.metadata
        stored_metadata = db.scalar(
            select(KnowledgeDocumentMetadata).where(
                KnowledgeDocumentMetadata.document_id == metadata.document_id
            )
        )
        if stored_metadata is None:
            document = KnowledgeDocument(
                title=metadata.title,
                document_type=metadata.document_type,
                source=metadata.source,
                content=loaded_document.data.content,
            )
            db.add(document)
            db.flush()
            stored_metadata = KnowledgeDocumentMetadata(
                knowledge_document_id=document.id,
                document_id=metadata.document_id,
                service=metadata.service,
                version=metadata.version,
                document_created_at=metadata.created_at,
                tags=metadata.tags,
                synthetic=True,
            )
            db.add(stored_metadata)
        else:
            document = db.get(KnowledgeDocument, stored_metadata.knowledge_document_id)
            if document is None:
                raise KnowledgeIndexError(
                    f"Metadata points to missing document {metadata.document_id}."
                )
            document.title = metadata.title
            document.document_type = metadata.document_type
            document.source = metadata.source
            document.content = loaded_document.data.content
            stored_metadata.service = metadata.service
            stored_metadata.version = metadata.version
            stored_metadata.document_created_at = metadata.created_at
            stored_metadata.tags = metadata.tags
            stored_metadata.synthetic = True

        db.flush()
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_document_id == document.id
            )
        )
        for chunk in chunks:
            db.add(
                KnowledgeChunk(
                    knowledge_document_id=document.id,
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    embedding=vector_by_chunk_id[chunk.chunk_id],
                    embedding_model=embedding_provider.model_name,
                    chunk_metadata=chunk.metadata,
                )
            )
    db.flush()
    return len(documents), len(flattened_chunks)


def search_knowledge_chunks(
    db: Session,
    embedding_provider: EmbeddingProvider,
    query: str,
    top_k: int,
) -> list[tuple[KnowledgeChunk, float]]:
    query_vector = embedding_provider.embed_query(query)
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.embedding_model == embedding_provider.model_name)
        .order_by(KnowledgeChunk.chunk_id)
    ).all()
    if not chunks:
        raise KnowledgeIndexError(
            "The knowledge base is not indexed for the configured embedding model."
        )

    scored = [
        (chunk, cosine_similarity(query_vector, chunk.embedding))
        for chunk in chunks
    ]
    scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
    # Prefer evidence breadth in the initial small corpus: a long document should
    # not occupy several top-K slots while other relevant sources go unseen.
    diversified: list[tuple[KnowledgeChunk, float]] = []
    seen_documents: set[str] = set()
    for chunk, score in scored:
        document_id = str(chunk.chunk_metadata["document_id"])
        if document_id in seen_documents:
            continue
        seen_documents.add(document_id)
        diversified.append((chunk, score))
        if len(diversified) == top_k:
            break
    return diversified


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise KnowledgeIndexError("Query and indexed embedding dimensions do not match.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True))
    return score / (left_norm * right_norm)
