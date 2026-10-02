import { FormEvent, useEffect, useState } from "react";

type DocumentMetadata = {
  document_id: string;
  document_type: string;
  title: string;
  service: string;
  source: string;
  version: string;
  created_at: string;
  tags: string[];
  synthetic: boolean;
};

type KnowledgeDocument = DocumentMetadata & {
  chunk_count: number;
};

type KnowledgeChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_type: string;
  service: string;
  source: string;
  text: string;
  metadata: Record<string, unknown>;
};

type DocumentDetail = KnowledgeDocument & {
  content: string;
  chunks: KnowledgeChunk[];
};

type SearchResult = KnowledgeChunk & {
  title: string;
  similarity_score: number;
};

const API_PREFIX = "/api/knowledge";
const SAMPLE_QUERY =
  "Checkout service is experiencing database connection timeouts after a deployment.";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export default function KnowledgeExplorer() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] =
    useState<DocumentDetail | null>(null);
  const [query, setQuery] = useState(SAMPLE_QUERY);
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [searching, setSearching] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_PREFIX}/documents`)
      .then(readJson<KnowledgeDocument[]>)
      .then((items) => {
        if (!active) return;
        setDocuments(items);
        setSelectedId(items[0]?.document_id ?? null);
      })
      .catch((loadError: Error) => {
        if (active) setError(loadError.message);
      })
      .finally(() => {
        if (active) setLoadingDocuments(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDocument(null);
      return;
    }
    let active = true;
    fetch(`${API_PREFIX}/documents/${encodeURIComponent(selectedId)}`)
      .then(readJson<DocumentDetail>)
      .then((document) => {
        if (active) setSelectedDocument(document);
      })
      .catch((loadError: Error) => {
        if (active) setError(loadError.message);
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearching(true);
    setError(null);
    try {
      const response = await fetch(`${API_PREFIX}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: topK }),
      });
      const body = await readJson<{ results: SearchResult[] }>(response);
      setResults(body.results);
    } catch (searchError) {
      setResults([]);
      setError(
        searchError instanceof Error
          ? searchError.message
          : "Knowledge search failed.",
      );
    } finally {
      setSearching(false);
    }
  }

  async function indexDocuments() {
    setIndexing(true);
    setError(null);
    setNotice(null);
    try {
      const indexed = await readJson<{
        documents_indexed: number;
        chunks_indexed: number;
      }>(
        await fetch(`${API_PREFIX}/index`, {
          method: "POST",
        }),
      );
      const refreshed = await readJson<KnowledgeDocument[]>(
        await fetch(`${API_PREFIX}/documents`),
      );
      setDocuments(refreshed);
      setSelectedId((current) => current ?? refreshed[0]?.document_id ?? null);
      setNotice(
        `Indexed ${indexed.documents_indexed} documents into ${indexed.chunks_indexed} chunks.`,
      );
    } catch (indexError) {
      setError(
        indexError instanceof Error
          ? indexError.message
          : "Knowledge indexing failed.",
      );
    } finally {
      setIndexing(false);
    }
  }

  return (
    <section aria-labelledby="knowledge-heading" className="space-y-5 py-7">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
            Local vector retrieval
          </p>
          <h2
            id="knowledge-heading"
            className="mt-2 text-2xl font-semibold text-white"
          >
            Knowledge library
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            Search approved synthetic runbooks, deployment records, architecture,
            known errors, and incident history. Results are evidence only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full border border-signal/30 bg-signal/10 px-3 py-1.5 text-xs font-medium text-signal">
            {documents.length} synthetic documents
          </span>
          <button
            type="button"
            onClick={indexDocuments}
            disabled={indexing}
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-signal hover:text-signal disabled:cursor-wait disabled:opacity-50"
          >
            {indexing ? "Indexing locally…" : "Index documents"}
          </button>
        </div>
      </header>

      {notice && (
        <div
          role="status"
          className="rounded-lg border border-signal/30 bg-signal/10 px-4 py-3 text-sm text-signal"
        >
          {notice}
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200"
        >
          {error}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <div className="space-y-5">
          <form
            onSubmit={runSearch}
            className="rounded-xl border border-slate-800 bg-panel p-5"
          >
            <label
              htmlFor="knowledge-query"
              className="text-sm font-medium text-slate-200"
            >
              Search operational knowledge
            </label>
            <textarea
              id="knowledge-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Describe the symptoms or operational question…"
              className="mt-3 w-full resize-y rounded-lg border border-slate-700 bg-ink px-3 py-3 text-sm leading-6 text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-signal"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-400">
                Top results
                <select
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value))}
                  className="rounded-md border border-slate-700 bg-ink px-2 py-1.5 text-slate-200"
                  aria-label="Number of top results"
                >
                  {[3, 5, 8, 10].map((count) => (
                    <option key={count} value={count}>
                      {count}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="submit"
                disabled={searching || !query.trim()}
                className="rounded-lg bg-signal px-4 py-2 text-sm font-semibold text-ink transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {searching ? "Searching…" : "Search knowledge"}
              </button>
            </div>
          </form>

          <section
            aria-labelledby="results-heading"
            className="rounded-xl border border-slate-800 bg-panel p-5"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3
                  id="results-heading"
                  className="text-sm font-semibold text-white"
                >
                  Retrieved evidence
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  Ranked by cosine similarity of local BGE embeddings
                </p>
              </div>
              {results.length > 0 && (
                <span className="font-mono text-xs text-slate-400">
                  {results.length} chunks
                </span>
              )}
            </div>
            {results.length === 0 ? (
              <p className="mt-5 rounded-lg border border-dashed border-slate-700 px-4 py-6 text-center text-sm text-slate-500">
                Run a search to retrieve relevant document chunks.
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {results.map((result) => (
                  <li
                    key={result.chunk_id}
                    className="rounded-lg border border-slate-800 bg-ink/70 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-slate-100">
                          {result.title}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          {result.document_type.replace(/_/g, " ")} ·{" "}
                          {result.service} · {result.document_id}
                        </p>
                      </div>
                      <span className="rounded-md bg-signal/10 px-2 py-1 font-mono text-xs text-signal">
                        {result.similarity_score.toFixed(4)}
                      </span>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                      {result.text}
                    </p>
                    <p className="mt-3 break-all text-[11px] text-slate-600">
                      {result.source} · {result.chunk_id}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="space-y-5">
          <section
            aria-labelledby="documents-heading"
            className="rounded-xl border border-slate-800 bg-panel p-5"
          >
            <div className="flex items-center justify-between gap-3">
              <h3
                id="documents-heading"
                className="text-sm font-semibold text-white"
              >
                Available documents
              </h3>
              {loadingDocuments && (
                <span className="text-xs text-slate-500">Loading…</span>
              )}
            </div>
            {documents.length === 0 && !loadingDocuments ? (
              <p className="mt-4 text-sm text-slate-500">
                No indexed documents found. Start the API and index the local knowledge base.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-slate-800">
                {documents.map((document) => (
                  <li key={document.document_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(document.document_id)}
                      aria-pressed={selectedId === document.document_id}
                      className={`w-full rounded-md px-3 py-3 text-left transition ${
                        selectedId === document.document_id
                          ? "bg-signal/10"
                          : "hover:bg-slate-800/60"
                      }`}
                    >
                      <span className="block text-sm font-medium text-slate-200">
                        {document.title}
                      </span>
                      <span className="mt-1 block text-xs text-slate-500">
                        {document.document_type.replace(/_/g, " ")} ·{" "}
                        {document.chunk_count}{" "}
                        {document.chunk_count === 1 ? "chunk" : "chunks"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {selectedDocument && (
            <section
              aria-labelledby="document-detail-heading"
              className="rounded-xl border border-slate-800 bg-panel p-5"
            >
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
                Document metadata
              </p>
              <h3
                id="document-detail-heading"
                className="mt-2 text-base font-semibold text-white"
              >
                {selectedDocument.title}
              </h3>
              <dl className="mt-4 grid grid-cols-[90px_1fr] gap-x-3 gap-y-2 text-xs">
                <MetadataRow label="ID" value={selectedDocument.document_id} />
                <MetadataRow label="Service" value={selectedDocument.service} />
                <MetadataRow label="Version" value={selectedDocument.version} />
                <MetadataRow label="Source" value={selectedDocument.source} />
                <MetadataRow
                  label="Created"
                  value={new Date(selectedDocument.created_at).toLocaleDateString()}
                />
              </dl>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {selectedDocument.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-400"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">
                {selectedDocument.synthetic
                  ? "Synthetic reference data · content is not executed."
                  : "Approved operational reference data."}
              </p>
            </section>
          )}
        </aside>
      </div>
    </section>
  );
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className="break-all text-slate-300">{value}</dd>
    </>
  );
}