# Autonomous AI-Powered Incident Commander

Hackathon-quality foundation for an enterprise SRE/DevOps incident investigation system.

## Phase 1: Project foundation

This phase contains:

- React + TypeScript + Vite frontend
- FastAPI backend with a basic health check
- Relative frontend-to-backend API connectivity through the Vite proxy
- Reserved directories for the database, simulation, knowledge, and documentation layers
- Docker configuration for local portability

AI orchestration, specialist agents, RAG, incident workflows, remediation, and postmortems are intentionally not implemented yet.

## Run on Replit

The project uses two workflows:

1. `Incident Commander Frontend` — Vite on port 5000
2. `Incident Commander API` — Uvicorn on port 8000

The frontend health card calls `/api/health`, which Vite proxies to the API service.

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
