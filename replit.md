# Replit run notes

## Workflows

- `Incident Commander Frontend`: `cd frontend && npm run dev`, port 5000
- `Incident Commander API`: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

The frontend calls `/api/health`. Vite proxies that path to the FastAPI `/health` endpoint.

## Current phase

Phase 4 is an isolated synthetic e-commerce environment in `docker-compose.simulation.yml`. Phase 5 adds local embedding-based knowledge retrieval to the API and a Knowledge Retrieval view to the frontend. The simulator remains separate from the frontend/API workflows and has no production connectivity.

LLM reasoning, agents, automated incident investigation, production remediation, recovery validation, and automated postmortem generation remain intentionally deferred until a later requested phase.