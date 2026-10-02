from __future__ import annotations

import asyncio
import os
from typing import Literal

from fastapi import FastAPI, HTTPException

from .common import SimulationLog, SimulationModel, append_log


SERVICE_NAME = "order-service"
SIMULATION_ONLY = os.getenv("SIMULATION_ONLY", "false").lower() == "true"


class OrderRequest(SimulationModel):
    checkout_reference: str
    acknowledge_simulation_only: Literal[True]


app = FastAPI(
    title="Simulated Order Service",
    description="Creates in-memory demo orders only; no commerce system is contacted.",
)
logs: list[SimulationLog] = []
_next_order = 1
_order_lock = asyncio.Lock()


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "service": SERVICE_NAME, "simulation_only": True}


@app.post("/orders")
async def create_order(data: OrderRequest) -> dict[str, str | bool | int]:
    global _next_order
    if not SIMULATION_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Order creation is disabled unless SIMULATION_ONLY=true.",
        )
    async with _order_lock:
        order_id = _next_order
        _next_order += 1
    append_log(
        logs,
        SERVICE_NAME,
        "INFO",
        "Synthetic order created in memory.",
        order_id=order_id,
        checkout_reference=data.checkout_reference,
        simulation_only=True,
    )
    return {"order_id": order_id, "status": "created", "simulation_only": True}


@app.get("/logs", response_model=list[SimulationLog])
async def get_logs() -> list[SimulationLog]:
    return logs
