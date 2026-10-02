from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import KnowledgeChunk, KnowledgeDocumentMetadata
from backend.app.db.session import get_db
from backend.app.knowledge.chunking import chunk_document
from backend.app.knowledge.documents import load_knowledge_documents
from backend.app.knowledge.embeddings import (
    DEFAULT_MODEL,
    FastEmbedProvider,
    get_embedding_provider,
)
from backend.app.main import app


IndexedAPI = tuple[TestClient, dict, sessionmaker]


@pytest.fixture(scope="module")
def indexed_api() -> Generator[IndexedAPI, None, None]:
    # Tests use the already-cached local model; they do not need model-registry access.
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    previous_cache = os.environ.get("KNOWLEDGE_EMBEDDING_CACHE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    cache = str(Path.cwd() / ".cache" / "fastembed")
    os.environ["KNOWLEDGE_EMBEDDING_CACHE"] = cache
    get_embedding_provider.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post("/knowledge/index")
            assert response.status_code == 200, response.text
            yield client, response.json(), session_factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_embedding_provider.cache_clear()
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
        if previous_cache is None:
            os.environ.pop("KNOWLEDGE_EMBEDDING_CACHE", None)
        else:
            os.environ["KNOWLEDGE_EMBEDDING_CACHE"] = previous_cache


def test_synthetic_documents_load_with_required_metadata() -> None:
    documents = load_knowledge_documents()
    assert len(documents) == 6
    expected_ids = {
        "RUNBOOK-CHECKOUT-DB-001",
        "TROUBLESHOOT-DB-POOL-001",
        "ARCH-ECOMMERCE-001",
        "KNOWN-ERROR-DB-TIMEOUT-001",
        "DEPLOY-CHECKOUT-1842",
        "INC-873",
    }
    assert {item.data.metadata.document_id for item in documents} == expected_ids
    for item in documents:
        metadata = item.data.metadata
        assert metadata.title
        assert metadata.document_type
        assert metadata.service
        assert metadata.source.startswith("knowledge/")
        assert metadata.version
        assert metadata.created_at.tzinfo is not None
        assert metadata.tags
        assert metadata.synthetic is True
        assert len(item.data.content) >= 20


def test_chunking_is_stable_and_preserves_document_metadata() -> None:
    document = load_knowledge_documents()[0]
    first = chunk_document(document, chunk_size_words=35, overlap_words=7)
    second = chunk_document(document, chunk_size_words=35, overlap_words=7)
    assert first
    assert [chunk.chunk_id for chunk in first] == [
        chunk.chunk_id for chunk in second
    ]
    assert [chunk.text for chunk in first] == [chunk.text for chunk in second]
    for chunk in first:
        assert chunk.metadata["document_id"] == document.data.metadata.document_id
        assert chunk.metadata["document_title"] == document.data.metadata.title
        assert chunk.metadata["document_type"] == document.data.metadata.document_type
        assert chunk.metadata["service"] == document.data.metadata.service
        assert chunk.metadata["source"] == document.data.metadata.source
        assert chunk.metadata["chunk_id"] == chunk.chunk_id


def test_chunk_configuration_rejects_invalid_overlap() -> None:
    document = load_knowledge_documents()[0]
    with pytest.raises(ValueError):
        chunk_document(document, chunk_size_words=10, overlap_words=10)
    with pytest.raises(ValueError):
        chunk_document(document, chunk_size_words=0, overlap_words=0)


def test_local_embedding_provider_generates_finite_vectors() -> None:
    provider = FastEmbedProvider(
        model_name=DEFAULT_MODEL,
        cache_dir=Path.cwd() / ".cache" / "fastembed",
    )
    vectors = provider.embed_documents(
        ["checkout database connection timeout", "order service request"]
    )
    query = provider.embed_query("checkout requests wait for database connections")
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384
    assert len(query) == 384
    assert all(value == value for vector in [*vectors, query] for value in vector)


def test_index_persists_documents_chunks_and_embeddings(
    indexed_api: IndexedAPI,
) -> None:
    client, index_result, session_factory = indexed_api
    assert index_result["documents_indexed"] == 6
    assert index_result["chunks_indexed"] > 6
    assert index_result["embedding_model"] == DEFAULT_MODEL

    documents = client.get("/knowledge/documents")
    assert documents.status_code == 200
    rows = documents.json()
    assert len(rows) == 6
    assert all(row["chunk_count"] >= 1 for row in rows)

    details = client.get("/knowledge/documents/DEPLOY-CHECKOUT-1842")
    assert details.status_code == 200
    assert details.json()["version"] == "checkout-sim-1.8.42"
    assert details.json()["chunks"]

    with session_factory() as db:
        vectors = db.scalars(select(KnowledgeChunk)).all()
        metadata = db.scalars(select(KnowledgeDocumentMetadata)).all()
        assert len(vectors) == index_result["chunks_indexed"]
        assert len(metadata) == 6
        assert all(len(chunk.embedding) == 384 for chunk in vectors)
        assert all(chunk.embedding_model == DEFAULT_MODEL for chunk in vectors)
        assert all(chunk.chunk_metadata["synthetic"] is True for chunk in vectors)


def test_reindex_is_idempotent(indexed_api: IndexedAPI) -> None:
    client, original, _ = indexed_api
    before = [
        item["chunk_id"]
        for document in client.get("/knowledge/documents").json()
        for item in client.get(
            f"/knowledge/documents/{document['document_id']}"
        ).json()["chunks"]
    ]
    response = client.post("/knowledge/index")
    assert response.status_code == 200
    assert response.json()["chunks_indexed"] == original["chunks_indexed"]
    after = [
        item["chunk_id"]
        for document in client.get("/knowledge/documents").json()
        for item in client.get(
            f"/knowledge/documents/{document['document_id']}"
        ).json()["chunks"]
    ]
    assert before == after
    assert len(set(after)) == len(after)


@pytest.mark.parametrize(
    ("query", "expected_document_id"),
    [
        (
            "Checkout service is experiencing database connection timeouts after a deployment.",
            "RUNBOOK-CHECKOUT-DB-001",
        ),
        (
            "Why are checkout requests timing out while waiting for database connections?",
            "TROUBLESHOOT-DB-POOL-001",
        ),
        ("What changed during release 1842?", "DEPLOY-CHECKOUT-1842"),
        (
            "Find previous incidents involving database connection pool exhaustion.",
            "INC-873",
        ),
        (
            "How does the checkout service communicate with the order service?",
            "ARCH-ECOMMERCE-001",
        ),
    ],
)
def test_semantic_queries_retrieve_relevant_synthetic_documents(
    indexed_api: IndexedAPI,
    query: str,
    expected_document_id: str,
) -> None:
    client, _, _ = indexed_api
    response = client.post(
        "/knowledge/search",
        json={"query": query, "top_k": 5},
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 5
    assert len({result["document_id"] for result in results}) == 5
    assert expected_document_id in {
        result["document_id"] for result in results
    }
    assert all(0 <= result["similarity_score"] <= 1 for result in results)
    assert all(result["text"] and result["metadata"] for result in results)


def test_top_k_limits_and_result_schema(indexed_api: IndexedAPI) -> None:
    client, _, _ = indexed_api
    response = client.post(
        "/knowledge/search",
        json={
            "query": "checkout database timeout",
            "top_k": 2,
        },
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert {
        "chunk_id",
        "document_id",
        "title",
        "document_type",
        "service",
        "source",
        "similarity_score",
        "text",
        "metadata",
    } <= set(results[0])


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   ", "top_k": 5},
        {"query": "timeout", "top_k": 0},
        {"query": "timeout", "top_k": 21},
    ],
)
def test_empty_queries_and_invalid_top_k_are_rejected(
    indexed_api: IndexedAPI,
    payload: dict,
) -> None:
    client, _, _ = indexed_api
    assert client.post("/knowledge/search", json=payload).status_code == 422


def test_unknown_document_is_a_safe_404(
    indexed_api: IndexedAPI,
) -> None:
    client, _, _ = indexed_api
    response = client.get("/knowledge/documents/NO-SUCH-DOCUMENT")
    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge document not found."


def test_retrieval_routes_do_not_add_reasoning_or_remediation() -> None:
    knowledge_paths = {
        route.path
        for route in app.routes
        if route.path.startswith("/knowledge/")
    }
    assert knowledge_paths == {
        "/knowledge/index",
        "/knowledge/search",
        "/knowledge/documents",
        "/knowledge/documents/{document_id}",
    }
    assert not any(
        marker in path
        for path in knowledge_paths
        for marker in ("root-cause", "investigate", "recommend", "simulate-fix", "execute")
    )


def test_document_metadata_and_vectors_are_stored_as_json(
    indexed_api: IndexedAPI,
) -> None:
    client, _, _ = indexed_api
    assert client.get("/knowledge/documents").status_code == 200
    # The metadata and vector columns use SQLAlchemy's portable JSON type rather
    # than a PostgreSQL-only extension or external vector database.
    assert KnowledgeChunk.__table__.c.embedding.type.__class__.__name__ == "JSON"
    assert KnowledgeChunk.__table__.c.metadata.type.__class__.__name__ == "JSON"
    assert KnowledgeDocumentMetadata.__table__.c.tags.type.__class__.__name__ == "JSON"