from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import Field

from .common import SimulationLog, SimulationModel, append_log


SERVICE_NAME = "api-gateway-simulation"
SIMULATION_ONLY = os.getenv("SIMULATION_ONLY", "false").lower() == "true"
DATABASE_URL = os.getenv("SIM_DATABASE_URL", "http://database-simulation:8092")
CHECKOUT_URL = os.getenv("SIM_CHECKOUT_URL", "http://checkout-service:8090")
ORDER_URL = os.getenv("SIM_ORDER_URL", "http://order-service:8091")

app = FastAPI(
    title="E-commerce Simulation API Gateway",
    description=(
        "Local-only control surface for the isolated synthetic Checkout Service demo. "
        "It has no production integrations."
    ),
)
logs: list[SimulationLog] = []
deployment_events: list[dict[str, Any]] = [
    {
        "event_type": "baseline_deployment",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "service": "checkout-service",
        "version": "sim-checkout-healthy",
        "config_changes": {"DB_POOL_SIZE": {"before": None, "after": 50}},
        "simulation_only": True,
    }
]
run_history: list[dict[str, Any]] = []
scenario_lock = asyncio.Lock()


class AcknowledgedSimulationAction(SimulationModel):
    acknowledge_simulation_only: Literal[True]


class SimulationRunRequest(AcknowledgedSimulationAction):
    request_volume: int = Field(default=40, ge=1, le=200)


class FailureInjectionRequest(AcknowledgedSimulationAction):
    scenario: Literal["checkout-db-pool-exhaustion"] = "checkout-db-pool-exhaustion"


async def request_json(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.request(method, url, json=json_body)
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text}
    if response.is_error:
        detail = payload.get("detail", f"Service returned HTTP {response.status_code}.")
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.status_code, payload


def _require_simulation_acknowledgement() -> None:
    if not SIMULATION_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Simulation controls are disabled unless SIMULATION_ONLY=true.",
        )


def summarize_run(samples: list[dict[str, Any]]) -> dict[str, float | int]:
    if not samples:
        return {
            "request_volume": 0,
            "error_count": 0,
            "error_rate_percent": 0.0,
            "average_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }
    latencies = sorted(float(sample["latency_ms"]) for sample in samples)
    error_count = sum(not bool(sample["success"]) for sample in samples)
    p95_index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    return {
        "request_volume": len(samples),
        "error_count": error_count,
        "error_rate_percent": round(error_count / len(samples) * 100, 2),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2),
        "p95_latency_ms": round(latencies[p95_index], 2),
    }


async def _pool_configuration() -> dict[str, Any]:
    _, configuration = await request_json("GET", f"{DATABASE_URL}/control/config")
    return configuration


def _public_state(pool_size: int) -> str:
    return "HEALTHY" if pool_size == 50 else "FAILURE"


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "simulation_only": True,
    }


@app.get("/simulation/state")
async def simulation_state() -> dict[str, Any]:
    configuration = await _pool_configuration()
    return {
        "state": _public_state(int(configuration["DB_POOL_SIZE"])),
        "configuration": configuration,
        "simulation_only": True,
    }


@app.post("/simulation/failure-injection")
async def inject_failure(
    data: FailureInjectionRequest,
) -> dict[str, Any]:
    _require_simulation_acknowledgement()
    async with scenario_lock:
        current = await _pool_configuration()
        if int(current["DB_POOL_SIZE"]) != 50:
            raise HTTPException(
                status_code=409,
                detail="Failure injection requires the HEALTHY pool size of 50.",
            )
        _, configuration = await request_json(
            "POST",
            f"{DATABASE_URL}/control/pool-size",
            json_body={
                "pool_size": 10,
                "acknowledge_simulation_only": True,
            },
        )
        event = {
            "event_type": "failure_injection_deployment",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "service": "checkout-service",
            "scenario": data.scenario,
            "config_changes": {"DB_POOL_SIZE": {"before": 50, "after": 10}},
            "simulation_only": True,
        }
        deployment_events.append(event)
        append_log(
            logs,
            SERVICE_NAME,
            "WARN",
            "Controlled failure injected in the synthetic environment.",
            scenario=data.scenario,
            DB_POOL_SIZE=10,
            simulation_only=True,
        )
        return {
            "state": "FAILURE",
            "configuration": configuration,
            "deployment_event": event,
            "simulation_only": True,
        }


@app.post("/simulation/rollback")
async def rollback(data: AcknowledgedSimulationAction) -> dict[str, Any]:
    _require_simulation_acknowledgement()
    async with scenario_lock:
        current = await _pool_configuration()
        if int(current["DB_POOL_SIZE"]) != 10:
            raise HTTPException(
                status_code=409,
                detail="Rollback is only available after failure injection.",
            )
        _, configuration = await request_json(
            "POST",
            f"{DATABASE_URL}/control/pool-size",
            json_body={
                "pool_size": 50,
                "acknowledge_simulation_only": True,
            },
        )
        event = {
            "event_type": "simulated_rollback",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "service": "checkout-service",
            "config_changes": {"DB_POOL_SIZE": {"before": 10, "after": 50}},
            "simulation_only": True,
        }
        deployment_events.append(event)
        append_log(
            logs,
            SERVICE_NAME,
            "INFO",
            "Simulated rollback restored the healthy database pool size.",
            DB_POOL_SIZE=50,
            simulation_only=True,
        )
        return {
            "state": "HEALTHY",
            "configuration": configuration,
            "deployment_event": event,
            "simulation_only": True,
        }


@app.post("/simulation/run")
async def run_scenario(data: SimulationRunRequest) -> dict[str, Any]:
    _require_simulation_acknowledgement()
    async with scenario_lock:
        configuration = await _pool_configuration()
        samples: list[dict[str, Any]] = []

        async def run_one(client: httpx.AsyncClient, request_number: int) -> None:
            started = asyncio.get_running_loop().time()
            try:
                response = await client.post(f"{CHECKOUT_URL}/checkout")
                latency_ms = (asyncio.get_running_loop().time() - started) * 1000
                body = response.json()
                samples.append(
                    {
                        "request_number": request_number,
                        "success": response.is_success and bool(body.get("success")),
                        "http_status": response.status_code,
                        "latency_ms": round(
                            float(body.get("latency_ms", latency_ms)),
                            2,
                        ),
                        "error": body.get("error"),
                    }
                )
            except (httpx.HTTPError, ValueError) as error:
                latency_ms = (asyncio.get_running_loop().time() - started) * 1000
                samples.append(
                    {
                        "request_number": request_number,
                        "success": False,
                        "http_status": 502,
                        "latency_ms": round(latency_ms, 2),
                        "error": str(error),
                    }
                )

        async with httpx.AsyncClient(timeout=5.0) as client:
            await asyncio.gather(
                *(
                    run_one(client, request_number)
                    for request_number in range(1, data.request_volume + 1)
                )
            )

        samples.sort(key=lambda item: item["request_number"])
        metrics = summarize_run(samples)
        run = {
            "state": _public_state(int(configuration["DB_POOL_SIZE"])),
            **metrics,
            "DB_POOL_SIZE": int(configuration["DB_POOL_SIZE"]),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "simulation_only": True,
        }
        run_history.append(run)
        del run_history[:-100]
        append_log(
            logs,
            SERVICE_NAME,
            "ERROR" if metrics["error_count"] else "INFO",
            "Synthetic checkout load run completed.",
            **run,
        )
        return {**run, "samples": samples}


@app.get("/simulation/report")
async def simulation_report() -> dict[str, Any]:
    configuration = await _pool_configuration()
    service_logs: list[dict[str, Any]] = []
    for service_url in (DATABASE_URL, CHECKOUT_URL, ORDER_URL):
        _, remote_logs = await request_json("GET", f"{service_url}/logs")
        service_logs.extend(remote_logs)
    service_logs.extend(log.model_dump(mode="json") for log in logs)
    return {
        "state": _public_state(int(configuration["DB_POOL_SIZE"])),
        "configuration": configuration,
        "metrics": run_history[-1] if run_history else None,
        "request_runs": run_history,
        "deployment_events": deployment_events,
        "application_logs": service_logs[-1000:],
        "simulation_only": True,
    }
