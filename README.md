# Autonomous AI-Powered Incident Commander

Hackathon-quality foundation for an enterprise SRE/DevOps incident investigation system.

## Current implementation

This phase contains:

- React + TypeScript + Vite frontend
- FastAPI backend with health checks
- SQLite database through SQLAlchemy
- Relational models for incidents, services, evidence, recommendations, actions, and postmortems
- Pydantic create/read schemas
- Idempotent Checkout Service seed data
- Migration-ready SQLAlchemy metadata boundary
- Deterministic incident create/retrieve, severity classification, and status transitions
- Auditable incident timeline events
- Log, deployment, metric, and evidence ingestion linked to incidents and services
- Docker configuration for local portability
- Evidence-linked Gemini root-cause analysis with response validation and duplicate-call caching

The project also includes a separate Phase 4 synthetic e-commerce simulation and the Phase 5 local knowledge-retrieval layer. Phase 6 adds evidence-grounded Gemini reasoning; remediation automation remains deferred.

## Run on Replit

The project uses two workflows:

1. `Incident Commander Frontend` — Vite on port 5000
2. `Incident Commander API` — Uvicorn on port 8000

The frontend health card calls `/api/health`, which Vite proxies to the API service.

Initialize and seed the database from the project root:

```bash
python -m backend.app.db.init_db
```

The default SQLite file is `database/incident_commander.db`. Set
`INCIDENT_DATABASE_URL` to point at a future PostgreSQL or other SQLAlchemy-supported
database.

Incident API routes include `POST /incidents`, `GET /incidents/{id}`,
`GET /incidents/{id}/evidence`, and `GET /incidents/{id}/metrics`. Deterministic status
updates and record-ingestion routes are also available under `/incidents/{id}`.

Phase 6 adds `POST /incidents/{incident_id}/root-cause-analysis` and
`GET /incidents/{incident_id}/root-cause-analysis`. It reads the
incident's stored logs, metric series, deployment records, and linked evidence, then
retrieves up to five relevant Phase 5 chunks by default before making one Gemini request.
Validated results are stored in the existing application database; GET returns that
stored result without another Gemini request or RAG generation. The legacy
`POST /incidents/analyze` route remains available and uses the same persistence path.
When the isolated Phase 4 simulator is running on its configured loopback port, the
analysis also reads its read-only `/simulation/report`; it accepts that report only
when `simulation_only` is true. If the simulator is stopped, the analysis reports
that limitation and uses evidence already stored with the incident.
Set `GEMINI_API_KEY` through Replit Secrets to enable fresh analyses; without it,
the endpoint returns a safe configuration error and does not call Gemini. The model
uses the configured `GEMINI_MODEL` (the development default is `gemini-3.8-flash`).

Input limits and cache behavior can be tuned with the `ROOT_CAUSE_*` values in
`.env.example`. Identical evidence reuses a bounded, process-local cache for five
minutes by default. The cache is not shared between processes and is cleared on
restart. A missing or unindexed knowledge base is reported as an uncertainty; it
does not cause a fabricated diagnosis. Phase 6 performs analysis only—no commands,
rollback, production access, or remediation are executed.

## Run locally

```bash
# Backend
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5000`.

## Docker

```bash
docker compose up --build
```

Docker is provided as a portability option. Replit workflows run directly in the workspace environment.

## Phase 4: isolated e-commerce simulation

Run the synthetic Checkout, Order, API Gateway, and database-pool simulator with:

```bash
docker compose -f docker-compose.simulation.yml up --build
```

The simulator gateway is bound to `127.0.0.1:8088` only. See
`docs/phase-4-simulation.md` for the HEALTHY → FAILURE → rollback flow. The simulation
network is internal and has no production connectivity.

## Phase 5: local knowledge retrieval

Index the synthetic runbooks, architecture, known errors, deployment, and incident
documents:

```bash
curl -X POST http://127.0.0.1:8000/knowledge/index
```

Use `POST /knowledge/search`, `GET /knowledge/documents`, and
`GET /knowledge/documents/{document_id}` to inspect the vector-retrieval results.
The local FastEmbed model is cached in `.cache/fastembed`; see
`docs/phase-5-knowledge-layer.md` for model-cache and API details. No LLM or production
service is called.
