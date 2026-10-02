# Replit run notes

## Workflows

- `Incident Commander Frontend`: `cd frontend && npm run dev`, port 5000
- `Incident Commander API`: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

The frontend calls `/api/health`. Vite proxies that path to the FastAPI `/health` endpoint.

## Current phase

Phase 4 includes an isolated synthetic e-commerce environment in `docker-compose.simulation.yml`. The simulator is intentionally separate from the frontend/API workflows and has no production connectivity.

AI, agents, RAG, incident investigation, production remediation, recovery, and automated postmortem generation remain intentionally deferred until the next requested phase.