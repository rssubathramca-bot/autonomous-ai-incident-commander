from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SimulationLog(SimulationModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service: str
    level: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


def append_log(
    logs: list[SimulationLog],
    service: str,
    level: str,
    message: str,
    **details: Any,
) -> SimulationLog:
    entry = SimulationLog(
        service=service,
        level=level,
        message=message,
        details=details,
    )
    logs.append(entry)
    # Bound in-memory logs so a long-running demo cannot grow without limit.
    del logs[:-1000]
    return entry
