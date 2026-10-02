from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from simulation import database, gateway


def test_pool_exhaustion_returns_timeouts() -> None:
    async def run() -> None:
        pool = database.SimulatedConnectionPool(pool_size=10)
        await pool.configure(10)
        outcomes = await asyncio.gather(
            *(pool.query() for _ in range(12)),
            return_exceptions=True,
        )
        successes = [item for item in outcomes if isinstance(item, float)]
        failures = [item for item in outcomes if isinstance(item, Exception)]
        assert len(successes) == 10
        assert len(failures) == 2
        assert pool.timeout_count == 2

    asyncio.run(run())


def test_database_pool_mutation_is_disabled_outside_simulation(monkeypatch) -> None:
    monkeypatch.setattr(database, "SIMULATION_ONLY", False)
    client = TestClient(database.app)
    response = client.post(
        "/control/pool-size",
        json={"pool_size": 10, "acknowledge_simulation_only": True},
    )
    assert response.status_code == 403


def test_run_summary_shows_failure_rate_and_latency() -> None:
    healthy = gateway.summarize_run(
        [
            {"success": True, "latency_ms": 40},
            {"success": True, "latency_ms": 45},
            {"success": True, "latency_ms": 55},
            {"success": True, "latency_ms": 60},
        ]
    )
    failure = gateway.summarize_run(
        [
            {"success": True, "latency_ms": 60},
            {"success": False, "latency_ms": 180},
            {"success": False, "latency_ms": 195},
            {"success": False, "latency_ms": 205},
        ]
    )
    assert healthy["error_rate_percent"] == 0
    assert failure["error_rate_percent"] == 75
    assert failure["p95_latency_ms"] > healthy["p95_latency_ms"]


def test_failure_injection_and_rollback_require_simulation_ack(monkeypatch) -> None:
    monkeypatch.setattr(gateway, "SIMULATION_ONLY", True)
    pool_size = 50
    calls: list[tuple[str, dict | None]] = []

    async def fake_request_json(method: str, url: str, *, json_body=None):
        nonlocal pool_size
        calls.append((method, json_body))
        if url.endswith("/control/config"):
            return 200, {"DB_POOL_SIZE": pool_size, "simulation_only": True}
        if url.endswith("/control/pool-size"):
            pool_size = json_body["pool_size"]
            return 200, {"DB_POOL_SIZE": pool_size, "simulation_only": True}
        raise AssertionError(f"Unexpected simulator call: {url}")

    monkeypatch.setattr(gateway, "request_json", fake_request_json)
    gateway.deployment_events.clear()
    gateway.logs.clear()
    client = TestClient(gateway.app)

    failure = client.post(
        "/simulation/failure-injection",
        json={"acknowledge_simulation_only": True},
    )
    assert failure.status_code == 200
    assert failure.json()["configuration"]["DB_POOL_SIZE"] == 10

    no_ack = client.post(
        "/simulation/rollback",
        json={"acknowledge_simulation_only": False},
    )
    assert no_ack.status_code == 422

    rollback = client.post(
        "/simulation/rollback",
        json={"acknowledge_simulation_only": True},
    )
    assert rollback.status_code == 200
    assert rollback.json()["configuration"]["DB_POOL_SIZE"] == 50
    assert [event["event_type"] for event in gateway.deployment_events] == [
        "failure_injection_deployment",
        "simulated_rollback",
    ]
    assert pool_size == 50