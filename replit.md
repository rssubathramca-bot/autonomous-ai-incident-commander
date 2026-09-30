# Replit run notes

## Workflows

- `Incident Commander Frontend`: `cd frontend && npm run dev`, port 5000
- `Incident Commander API`: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

The frontend calls `/api/health`. Vite proxies that path to the FastAPI `/health` endpoint.

## Phase 1 status

The project foundation is complete: React + TypeScript + Tailwind, FastAPI health check, reserved architecture directories, and Docker portability files.

AI, agents, RAG, database entities, incident investigation, remediation, recovery, and postmortem features are intentionally deferred until the next requested phase.