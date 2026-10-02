# Replit run notes

## Workflows

- `Incident Commander Frontend`: `cd frontend && npm run dev`, port 5000
- `Incident Commander API`: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

The frontend calls `/api/health`. Vite proxies that path to the FastAPI `/health` endpoint. The Root-cause analysis view calls `/api/incidents/analyze`, which Vite proxies to FastAPI.

## Current phase

Phase 4 is an isolated synthetic e-commerce environment in `docker-compose.simulation.yml`. Phase 5 adds local embedding-based knowledge retrieval to the API and a Knowledge Retrieval view to the frontend. Phase 6 adds Gemini root-cause analysis, evidence-ID validation, duplicate-call caching, and a Root-cause analysis view. The simulator remains separate from the frontend/API workflows and has no production connectivity.

## Phase 6 configuration

- Set `GEMINI_API_KEY` using Replit Secrets. Never commit a key to `.env.example` or source.
- `GEMINI_MODEL` defaults to `gemini-2.5-flash`.
- `ROOT_CAUSE_RAG_TOP_K`, `ROOT_CAUSE_MAX_EVIDENCE_CHARS`, `ROOT_CAUSE_MAX_LOG_CHARS`, `ROOT_CAUSE_MAX_PROMPT_CHARS`, `ROOT_CAUSE_MAX_LOG_EVENTS`, and `ROOT_CAUSE_TIMEOUT_SECONDS` bound each request.
- `ROOT_CAUSE_CACHE_TTL_SECONDS` and `ROOT_CAUSE_CACHE_MAX_ENTRIES` tune the process-local duplicate-analysis cache.
- Initialize and seed SQLite with `python -m backend.app.db.init_db`; the analysis view defaults to seeded incident ID `1`.
- `POST /incidents/analyze` accepts `{"incident_id": 1}`. Fresh analysis requires `GEMINI_API_KEY` and stored incident evidence. If the isolated simulator is running, it reads its loopback report and checks `simulation_only: true`; otherwise it reports that the simulator is unavailable. Phase 6 is analysis only and does not execute remediation or contact production infrastructure.