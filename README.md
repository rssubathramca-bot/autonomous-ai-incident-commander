# Autonomous AI-Powered Incident Commander

Hackathon-quality foundation for an enterprise SRE/DevOps incident investigation system.

## Phase 2: Database foundation

This phase contains:

- React + TypeScript + Vite frontend
- FastAPI backend with health checks
- SQLite database through SQLAlchemy
- Relational models for incidents, services, evidence, recommendations, actions, and postmortems
- Pydantic create/read schemas
- Idempotent Checkout Service seed data
- Migration-ready SQLAlchemy metadata boundary
- Docker configuration for local portability

AI orchestration, specialist agents, RAG, incident workflows, and remediation execution are intentionally not implemented yet.

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
