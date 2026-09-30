import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  service: string;
  phase: string;
};

type ConnectionState =
  | { status: "checking" }
  | { status: "online"; data: HealthResponse }
  | { status: "offline"; message: string };

function App() {
  const [connection, setConnection] = useState<ConnectionState>({
    status: "checking",
  });

  useEffect(() => {
    fetch("/api/health")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return (await response.json()) as HealthResponse;
      })
      .then((data) => setConnection({ status: "online", data }))
      .catch((error: Error) =>
        setConnection({ status: "offline", message: error.message }),
      );
  }, []);

  const isOnline = connection.status === "online";

  return (
    <main className="min-h-screen bg-ink px-6 py-10 text-slate-100 sm:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-col justify-between gap-6 border-b border-slate-800 pb-8 sm:flex-row sm:items-end">
          <div>
            <div className="mb-4 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.24em] text-signal">
              <span className="h-2 w-2 rounded-full bg-signal shadow-[0_0_12px_rgba(65,214,167,0.9)]" />
              Database / Phase 2
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Incident Commander
            </h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-slate-400">
              A controlled workspace for evidence-led incident investigation
              across enterprise services.
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-panel px-4 py-3 text-sm">
            <p className="text-slate-500">Operating mode</p>
            <p className="mt-1 font-medium text-slate-200">Read-only data layer</p>
          </div>
        </header>

        <section className="grid gap-5 py-8 md:grid-cols-3">
          <article className="rounded-xl border border-slate-800 bg-panel p-5 md:col-span-2">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-400">System readiness</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  API connectivity
                </h2>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  connection.status === "checking"
                    ? "bg-amber-400/10 text-amber-300"
                    : isOnline
                      ? "bg-signal/10 text-signal"
                      : "bg-rose-400/10 text-rose-300"
                }`}
              >
                {connection.status === "checking"
                  ? "Checking"
                  : isOnline
                    ? "Online"
                    : "Offline"}
              </span>
            </div>
            <div className="mt-8 grid gap-4 border-t border-slate-800 pt-5 sm:grid-cols-3">
              <StatusMetric
                label="Service"
                value={isOnline ? connection.data.service : "Incident API"}
              />
              <StatusMetric
                label="Environment"
                value={isOnline ? connection.data.phase : "Foundation"}
              />
              <StatusMetric
                label="Endpoint"
                value="/api/health"
              />
            </div>
            {connection.status === "offline" && (
              <p className="mt-5 text-sm text-rose-300">
                Unable to reach the API: {connection.message}
              </p>
            )}
          </article>

          <article className="rounded-xl border border-slate-800 bg-panel p-5">
            <p className="text-sm font-medium text-slate-400">Next layers</p>
            <ul className="mt-4 space-y-3 text-sm text-slate-300">
              <RoadmapItem label="Incident data model" />
              <RoadmapItem label="Evidence collection" />
              <RoadmapItem label="AI orchestration" muted />
              <RoadmapItem label="Safe remediation" muted />
            </ul>
          </article>
        </section>

        <footer className="border-t border-slate-800 pt-5 text-sm text-slate-500">
          Phase 2 includes persistence and seed data; AI, agents, RAG, and remediation remain deferred.
        </footer>
      </div>
    </main>
  );
}

function StatusMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-2 truncate font-mono text-sm text-slate-200">{value}</p>
    </div>
  );
}

function RoadmapItem({ label, muted = false }: { label: string; muted?: boolean }) {
  return (
    <li className={`flex items-center gap-3 ${muted ? "text-slate-500" : ""}`}>
      <span
        className={`h-2 w-2 rounded-full ${
          muted ? "bg-slate-700" : "bg-signal"
        }`}
      />
      {label}
    </li>
  );
}

export default App;
