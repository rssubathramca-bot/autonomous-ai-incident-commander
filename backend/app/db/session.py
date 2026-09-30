import os
from pathlib import Path
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .base import Base


# Use an app-specific variable so a platform-provided PostgreSQL DATABASE_URL
# cannot redirect the SQLite MVP to an unavailable external service.
DATABASE_URL = os.getenv(
    "INCIDENT_DATABASE_URL",
    "sqlite:///./database/incident_commander.db",
)

if DATABASE_URL.startswith("sqlite:///") and ":memory:" not in DATABASE_URL:
    database_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

engine_kwargs: dict[str, object] = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for the MVP. Migrations can target the same Base.metadata."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
