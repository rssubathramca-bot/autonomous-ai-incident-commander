from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from fastapi import Depends
from sqlalchemy.orm import Session

from .db.session import get_db


app = FastAPI(
    title="Incident Commander API",
    version="0.1.0",
    description="Phase 2 database foundation API for the Autonomous AI-Powered Incident Commander.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a deterministic liveness response for the foundation service."""
    return {
        "status": "ok",
        "service": "incident-commander-api",
        "phase": "database",
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
