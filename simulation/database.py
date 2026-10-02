from __future__ import annotations

import asyncio
import os
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException

from .common import SimulationLog, SimulationModel, append_log


SERVICE_NAME = "database-simulation"
SIMULATION_ONLY = os.getenv("SIMULATION_ONLY", "false").lower() == "true"
POOL_WAIT_TIMEOUT_SECONDS = 0.015
QUERY_DURATION_SECONDS = 0.045


class PoolSizeChange(SimulationModel):
    pool_size: Literal[10, 50]
    acknowledge_simulation_only: Literal[True]


class SimulatedConnectionPool:
    """An in-memory pool limiter. It never opens a real database connection."""

    def __init__(self, pool_size: int = 50) -> None:
        self.pool_size = pool_size
        self.active = 0
        self.query_count = 0
        self.timeout_count = 0
        self._condition = asyncio.Condition()

    async def configure(self, pool_size: int) -> None:
        if pool_size not in (10, 50):
            raise ValueError("Only the synthetic pool sizes 10 and 50 are supported.")
        async with self._condition:
            self.pool_size = pool_size
            self._condition.notify_all()

    async def query(self) -> float:
        started = perf_counter()
        self.query_count += 1
        acquired = False
        try:
            await asyncio.wait_for(
                self._acquire(),
                timeout=POOL_WAIT_TIMEOUT_SECONDS,
            )
            acquired = True
        except TimeoutError as error:
            self.timeout_count += 1
            raise ConnectionPoolTimeout(
                "database connection timeout: simulated pool capacity exhausted"
            ) from error

        try:
            await asyncio.sleep(QUERY_DURATION_SECONDS)
            return (perf_counter() - started) * 1000
        finally:
            if acquired:
                await self._release()

    async def _acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self.active < self.pool_size)
            self.active += 1

    async def _release(self) -> None:
        async with self._condition:
            self.active -= 1
            self._condition.notify(1)


class ConnectionPoolTimeout(Exception):
    pass


app = FastAPI(
    title="Simulated Database",
    description="In-memory connection-pool simulator. No external database is used.",
)
pool = SimulatedConnectionPool(pool_size=int(os.getenv("DB_POOL_SIZE", "50")))
logs: list[SimulationLog] = []


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "simulation_only": True,
    }


@app.get("/control/config")
async def get_config() -> dict[str, int | bool]:
    return {"DB_POOL_SIZE": pool.pool_size, "simulation_only": True}


@app.post("/control/pool-size")
async def set_pool_size(data: PoolSizeChange) -> dict[str, int | bool]:
    if not SIMULATION_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Pool changes are disabled unless SIMULATION_ONLY=true.",
        )
    previous = pool.pool_size
    await pool.configure(data.pool_size)
    append_log(
        logs,
        SERVICE_NAME,
        "WARN" if data.pool_size == 10 else "INFO",
        "Simulated database pool configuration changed.",
        previous_pool_size=previous,
        DB_POOL_SIZE=data.pool_size,
        simulation_only=True,
    )
    return {"DB_POOL_SIZE": pool.pool_size, "simulation_only": True}


@app.post("/query")
async def query() -> dict[str, float | bool]:
    try:
        latency_ms = await pool.query()
        append_log(
            logs,
            SERVICE_NAME,
            "INFO",
            "Simulated database query completed.",
            latency_ms=round(latency_ms, 2),
        )
        return {"ok": True, "latency_ms": round(latency_ms, 2)}
    except ConnectionPoolTimeout as error:
        append_log(
            logs,
            SERVICE_NAME,
            "ERROR",
            str(error),
            DB_POOL_SIZE=pool.pool_size,
            active_connections=pool.active,
        )
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/metrics")
async def metrics() -> dict[str, int | float]:
    error_rate = (
        pool.timeout_count / pool.query_count * 100 if pool.query_count else 0.0
    )
    return {
        "DB_POOL_SIZE": pool.pool_size,
        "query_count": pool.query_count,
        "timeout_count": pool.timeout_count,
        "error_rate_percent": round(error_rate, 2),
        "active_connections": pool.active,
    }


@app.get("/logs", response_model=list[SimulationLog])
async def get_logs() -> list[SimulationLog]:
    return logs
