# Phase 5: Local knowledge and vector retrieval

Phase 5 indexes six synthetic e-commerce operations documents, creates stable
overlapping chunks, generates local BGE sentence embeddings, stores vectors in SQLite,
and returns the highest cosine-similarity matches. Retrieved text is evidence only.
There is no root-cause reasoning, LLM summarization, agent, remediation decision, or
action execution in this phase.

## Start and index

The regular FastAPI workflow creates the additional MVP tables on startup. Index the
versioned source documents from the repository:

```bash
curl -X POST http://127.0.0.1:8000/knowledge/index
```

The default embedding model is `BAAI/bge-small-en-v1.5` (384 dimensions), executed
locally on CPU through FastEmbed. The model weights are downloaded from the public
model registry on first use and cached under `.cache/fastembed`. Searches use the
cached model locally and do not call an embedding API. For a network-isolated
deployment, pre-populate the configured model cache before starting the service. The
Docker backend image warms the model cache at build time.

The chunker uses whitespace-delimited words, a configurable maximum of 180 words, and
a deterministic 30-word overlap. It keeps document metadata on each chunk and creates
stable chunk IDs from the document ID, chunk position, and chunk text. Re-indexing
updates document content and replaces its chunks atomically; it does not duplicate
documents.

## API

- `POST /knowledge/index` — load, validate, chunk, embed, and persist the synthetic
  knowledge directory.
- `POST /knowledge/search` — embed a query and return ranked top-K chunks.
- `GET /knowledge/documents` — list indexed documents and metadata.
- `GET /knowledge/documents/{document_id}` — return one document and its chunks.

Search body:

```json
{
  "query": "Checkout service is experiencing database connection timeouts after a deployment",
  "top_k": 5
}
```

The `knowledge_chunks` table stores JSON vectors and chunk metadata. Search calculates
cosine similarity in application code, which keeps the initial schema SQLite-friendly
and PostgreSQL-compatible without requiring a vector extension. This is appropriate
for the small synthetic corpus; a larger corpus would need an indexed vector backend.

The Knowledge Retrieval view in the frontend supports indexing, document browsing,
semantic search, chunk inspection, similarity scores, and metadata. It renders retrieved
content as text and does not execute or interpret it as instructions.
