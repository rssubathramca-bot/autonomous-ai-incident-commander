# Replit run notes

## Workflows

- `Incident Commander Frontend`: `cd frontend && npm run dev`, port 5000
- `Incident Commander API`: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

The frontend calls `/api/health`. Vite proxies that path to the FastAPI `/health` endpoint.

## Phase 1 status

Phase 2 is complete: SQLAlchemy SQLite models, Pydantic schemas, database initialization, migration-ready metadata, and seeded Checkout Service data.

AI, agents, RAG, incident investigation, remediation, recovery, and automated postmortem generation remain intentionally deferred until the next requested phase.