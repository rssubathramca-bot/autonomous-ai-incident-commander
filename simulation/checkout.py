from __future__ import annotations

import os
import uuid
from time import perf_counter
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .common import SimulationLog, append_log


SERVICE_NAME = "checkout-service"
DATABASE_URL = os.getenv("SIM_DATABASE_URL", "http://database-simulation:8092")
ORDER_URL = os.getenv("SIM_ORDER_URL", "http://order-service:8091")
SIMULATION_ONLY = os.getenv("SIMULATION_ONLY", "false").lower() == "true"
FAILURE_RETRY_DELAY_SECONDS = 0.6

app = FastAPI(
    title="Simulated Checkout Service",
    description="Synthetic checkout traffic; all dependent services are simulated.",
)
logs: list[SimulationLog] = []


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "service": SERVICE_NAME, "simulation_only": True}


@app.post("/checkout")
async def checkout() -> JSONResponse:
    if not SIMULATION_ONLY:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": "Simulation-only mode is disabled."},
        )

    started = perf_counter()
    checkout_reference = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            db_response = await client.post(f"{DATABASE_URL}/query")
            if db_response.is_error:
                error_detail = db_response.json().get("detail", "simulated database error")
                raise RuntimeError(error_detail)
            order_response = await client.post(
                f"{ORDER_URL}/orders",
                json={
                    "checkout_reference": checkout_reference,
                    "acknowledge_simulation_only": True,
                },
            )
            order_response.raise_for_status()
            order = order_response.json()
    except (httpx.HTTPError, RuntimeError) as error:
        # A fixed simulated retry/backoff delay models the elevated failure latency.
        import asyncio

        await asyncio.sleep(FAILURE_RETRY_DELAY_SECONDS)
        latency_ms = (perf_counter() - started) * 1000
        append_log(
            logs,
            SERVICE_NAME,
            "ERROR",
            f"Checkout failed: {error}",
            latency_ms=round(latency_ms, 2),
            checkout_reference=checkout_reference,
            simulation_only=True,
        )
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": str(error),
                "latency_ms": round(latency_ms, 2),
                "checkout_reference": checkout_reference,
                "simulation_only": True,
            },
        )

    latency_ms = (perf_counter() - started) * 1000
    append_log(
        logs,
        SERVICE_NAME,
        "INFO",
        "Checkout completed.",
        latency_ms=round(latency_ms, 2),
        order_id=order["order_id"],
        simulation_only=True,
    )
    return JSONResponse(
        content={
            "success": True,
            "latency_ms": round(latency_ms, 2),
            "order_id": order["order_id"],
            "simulation_only": True,
        }
    )


@app.get("/logs", response_model=list[SimulationLog])
async def get_logs() -> list[SimulationLog]:
    return logs
