import { FormEvent, useState } from "react";

type EvidenceItem = {
  evidence_id: string;
  kind: string;
  label: string;
  source: string;
  summary: string;
  occurred_at?: string;
  document_id?: string;
};

type EvidenceReference = {
  evidence_id: string;
  reason: string;
};

type Hypothesis = {
  hypothesis_id: string;
  statement: string;
  supporting_evidence: EvidenceReference[];
  contradicting_evidence: EvidenceReference[];
  confidence: number;
};

type Analysis = {
  summary: string;
  hypotheses: Hypothesis[];
  primary_hypothesis: {
    hypothesis_id: string;
    reason: string;
    supporting_evidence_ids: string[];
    confidence: number;
    uncertainty: string;
  } | null;
  evidence_chain: string[];
  uncertainties: string[];
  recommended_next_checks: string[];
};

type AnalysisResponse = {
  incident_id: number;
  incident: {
    id: number;
    service: string;
    severity: string;
    status: string;
    title: string;
    summary: string;
  };
  analysis: Analysis;
  evidence: EvidenceItem[];
  retrieved_evidence: EvidenceItem[];
  model: string;
  ai_call_count: number;
  cached: boolean;
};

function apiErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (
      typeof detail === "object" &&
      detail !== null &&
      "message" in detail &&
      typeof (detail as { message: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
  }
  return fallback;
}

export default function RootCauseExplorer() {
  const [incidentId, setIncidentId] = useState("1");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedId = Number(incidentId);
    if (!Number.isSafeInteger(parsedId) || parsedId <= 0) {
      setError("Enter a valid positive incident ID.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/incidents/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_id: parsedId }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(apiErrorMessage(body, `Analysis failed (${response.status}).`));
      }
      setResult(body as AnalysisResponse);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The analysis request could not be completed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-6 py-8">
      <header className="flex flex-col justify-between gap-5 border-b border-slate-800 pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
            Phase 6 · Evidence-led reasoning
          </p>
          <h2 className="mt-2 text-3xl font-semibold text-white">
            Root-cause analysis
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            Review incident telemetry and Phase 5 knowledge alongside a
            validated Gemini analysis. The result is advisory, not a confirmed
            cause or remediation.
          </p>
        </div>
        <span className="w-fit rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-semibold text-amber-200">
          Analysis only · no actions executed
        </span>
      </header>

      <form
        onSubmit={analyze}
        className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-panel p-5 sm:flex-row sm:items-end"
      >
        <label className="flex-1 text-sm font-medium text-slate-300">
          Incident database ID
          <input
            type="number"
            min="1"
            step="1"
            required
            value={incidentId}
            onChange={(event) => setIncidentId(event.target.value)}
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-ink px-3 py-2.5 font-mono text-sm text-white outline-none focus:border-signal"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-signal px-5 py-2.5 text-sm font-semibold text-ink transition hover:bg-emerald-300 disabled:cursor-wait disabled:opacity-60"
        >
          {loading ? "Analyzing evidence…" : "Analyze incident"}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200"
        >
          {error}
        </div>
      )}

      {loading && (
        <p aria-live="polite" className="text-sm text-slate-400">
          Preparing bounded incident evidence and checking for a cached result.
          A new Gemini request can take up to the configured request timeout.
        </p>
      )}

      {result && (
        <div className="space-y-6">
          <article className="rounded-xl border border-slate-800 bg-panel p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-800 px-2.5 py-1 font-mono text-xs text-slate-200">
                Incident #{result.incident.id}
              </span>
              <span className="rounded-full bg-rose-400/10 px-2.5 py-1 text-xs text-rose-200">
                {result.incident.severity}
              </span>
              <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300">
                {result.incident.status}
              </span>
              <span className="ml-auto text-xs text-slate-500">
                {result.cached
                  ? "Cached result · 0 Gemini calls"
                  : `${result.ai_call_count} Gemini call`}
              </span>
            </div>
            <h3 className="mt-4 text-xl font-semibold text-white">
              {result.incident.title}
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              {result.incident.service}
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              {result.incident.summary}
            </p>
          </article>

          <section aria-labelledby="evidence-heading">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Deterministic input
                </p>
                <h3 id="evidence-heading" className="mt-1 text-xl font-semibold text-white">
                  Evidence sent for analysis
                </h3>
              </div>
              <span className="text-xs text-slate-500">
                {result.evidence.length} evidence items · {result.retrieved_evidence.length} retrieved
              </span>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {result.evidence.map((item) => (
                <article
                  key={item.evidence_id}
                  className="rounded-lg border border-slate-800 bg-panel p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.14em] text-slate-500">
                        {evidenceLabel(item.kind)} · {item.evidence_id}
                      </p>
                      <h4 className="mt-1 font-medium text-slate-200">{item.label}</h4>
                    </div>
                    {item.document_id && (
                      <span className="shrink-0 font-mono text-xs text-slate-500">
                        {item.document_id}
                      </span>
                    )}
                  </div>
                  <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-400">
                    {item.summary}
                  </p>
                  <p className="mt-3 text-xs text-slate-600">{item.source}</p>
                </article>
              ))}
              {result.evidence.length === 0 && (
                <p className="text-sm text-slate-500">No evidence was supplied.</p>
              )}
            </div>
          </section>

          <section
            aria-labelledby="analysis-heading"
            className="rounded-xl border border-signal/30 bg-panel p-5 sm:p-6"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-signal">
                  AI-GENERATED ANALYSIS
                </p>
                <h3 id="analysis-heading" className="mt-1 text-xl font-semibold text-white">
                  Root-cause hypotheses
                </h3>
              </div>
              <span className="rounded-full border border-slate-700 px-3 py-1 font-mono text-xs text-slate-400">
                {result.model}
              </span>
            </div>

            <p className="mt-5 text-sm leading-7 text-slate-200">
              {result.analysis.summary}
            </p>

            {result.analysis.primary_hypothesis && (
              <div className="mt-5 rounded-lg border border-signal/25 bg-signal/5 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">
                  Primary hypothesis · {result.analysis.primary_hypothesis.hypothesis_id}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-200">
                  {result.analysis.primary_hypothesis.reason}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-400">
                  Confidence {result.analysis.primary_hypothesis.confidence.toFixed(2)} · uncertainty:{" "}
                  {result.analysis.primary_hypothesis.uncertainty}
                </p>
              </div>
            )}

            <div className="mt-5 space-y-3">
              {result.analysis.hypotheses.map((hypothesis) => (
                <article
                  key={hypothesis.hypothesis_id}
                  className="rounded-lg border border-slate-800 bg-ink/50 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h4 className="font-medium text-white">
                      <span className="mr-2 font-mono text-signal">{hypothesis.hypothesis_id}</span>
                      {hypothesis.statement}
                    </h4>
                    <span
                      className="shrink-0 rounded-full bg-slate-800 px-2.5 py-1 font-mono text-xs text-slate-300"
                      title="Uncertainty indicator from 0.00 (low confidence) to 1.00 (high confidence)"
                    >
                      Confidence {hypothesis.confidence.toFixed(2)}
                    </span>
                  </div>
                  <EvidenceReferences
                    title="Supporting evidence"
                    items={hypothesis.supporting_evidence}
                  />
                  <EvidenceReferences
                    title="Contradicting evidence"
                    items={hypothesis.contradicting_evidence}
                  />
                </article>
              ))}
              {result.analysis.hypotheses.length === 0 && (
                <p className="rounded-lg border border-slate-800 p-4 text-sm text-slate-400">
                  No root-cause hypothesis was supported by the supplied evidence.
                </p>
              )}
            </div>

            <div className="mt-5 grid gap-5 border-t border-slate-800 pt-5 md:grid-cols-3">
              <StringList
                title="Evidence chain"
                items={result.analysis.evidence_chain}
                empty="No evidence chain was returned."
              />
              <StringList
                title="Uncertainties"
                items={result.analysis.uncertainties}
                empty="No uncertainty was listed."
              />
              <StringList
                title="Recommended next checks"
                items={result.analysis.recommended_next_checks}
                empty="No next checks were returned."
              />
            </div>
            <p className="mt-5 border-t border-slate-800 pt-4 text-xs leading-5 text-slate-500">
              This is an AI-generated assessment, not verified fact. Check cited
              source evidence before drawing conclusions. No commands, rollback,
              or remediation were executed.
            </p>
          </section>
        </div>
      )}
    </section>
  );
}

function evidenceLabel(kind: string): string {
  const labels: Record<string, string> = {
    log_summary: "Log summary",
    log: "Log",
    simulation_state: "Simulation state",
    simulation_configuration: "Simulation configuration",
    simulation_metrics: "Simulation metrics",
    simulation_deployment: "Simulation deployment",
    simulation_log: "Simulation log",
    metric: "Metric series",
    derived_metric: "Calculated metric",
    deployment: "Deployment",
    recorded_evidence: "Recorded evidence",
    rag: "Phase 5 knowledge",
  };
  return labels[kind] ?? kind;
}

function EvidenceReferences({
  title,
  items,
}: {
  title: string;
  items: EvidenceReference[];
}) {
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      {items.length ? (
        <ul className="mt-2 space-y-1.5">
          {items.map((item, index) => (
            <li key={`${item.evidence_id}-${index}`} className="text-sm leading-5 text-slate-400">
              <span className="mr-2 font-mono text-signal">{item.evidence_id}</span>
              {item.reason}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-600">None cited.</p>
      )}
    </div>
  );
}

function StringList({
  title,
  items,
  empty,
}: {
  title: string;
  items: string[];
  empty: string;
}) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
      {items.length ? (
        <ul className="mt-2 space-y-2">
          {items.map((item, index) => (
            <li key={`${index}-${item}`} className="text-sm leading-5 text-slate-400">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-600">{empty}</p>
      )}
    </div>
  );
}