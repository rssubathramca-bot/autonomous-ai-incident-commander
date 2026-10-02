from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .api.knowledge import router as knowledge_router
from .api.incidents import router as incidents_router
from .db.session import get_db, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create new MVP tables on startup without altering existing SQLite tables.
    init_db()
    yield


app = FastAPI(
    title="Incident Commander API",
    version="0.1.0",
    description=(
        "Deterministic incident engine and local knowledge retrieval API for the "
        "Autonomous AI-Powered Incident Commander."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)
app.include_router(incidents_router)
app.include_router(knowledge_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a deterministic liveness response for the foundation service."""
    return {
        "status": "ok",
        "service": "incident-commander-api",
        "phase": "incident-engine",
    }


@app.get("/health/database", tags=["system"])
def database_health(db: Session = Depends(get_db)) -> dict[str, str | bool]:
    """Confirm the database connection and initialized schema are available."""
    try:
        db.execute(text("SELECT 1"))
        tables = inspect(db.bind).get_table_names()
        initialized = "incidents" in tables and "services" in tables
        return {
            "status": "ok" if initialized else "degraded",
            "database": "sqlite",
            "initialized": initialized,
        }
    except SQLAlchemyError:
        return {
            "status": "error",
            "database": "sqlite",
            "initialized": False,
        }
