from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _native_simulation_stack() -> Iterator[str]:
    database_port, orders_port, checkout_port, gateway_port = (
        _free_port(),
        _free_port(),
        _free_port(),
        _free_port(),
    )
    common_env = {**os.environ, "SIMULATION_ONLY": "true"}
    processes: list[subprocess.Popen] = []

    def start(module: str, port: int, **extra_env: str) -> None:
        env = {**common_env, **extra_env}
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"simulation.{module}:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "error",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )

    start("database", database_port, DB_POOL_SIZE="50")
    start("orders", orders_port)
    start(
        "checkout",
        checkout_port,
        SIM_DATABASE_URL=f"http://127.0.0.1:{database_port}",
        SIM_ORDER_URL=f"http://127.0.0.1:{orders_port}",
    )
    start(
        "gateway",
        gateway_port,
        SIM_DATABASE_URL=f"http://127.0.0.1:{database_port}",
        SIM_CHECKOUT_URL=f"http://127.0.0.1:{checkout_port}",
        SIM_ORDER_URL=f"http://127.0.0.1:{orders_port}",
    )
    base_url = f"http://127.0.0.1:{gateway_port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("A Phase 4 simulator service exited during startup.")
            try:
                if httpx.get(f"{base_url}/health", timeout=0.5).is_success:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("The Phase 4 simulation gateway did not become healthy.")
        yield base_url
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_phase4_healthy_failure_timeout_and_rollback_regression() -> None:
    with _native_simulation_stack() as base_url, httpx.Client(timeout=10) as client:
        initial = client.get(f"{base_url}/simulation/state").json()
        assert initial["state"] == "HEALTHY"
        assert initial["configuration"]["DB_POOL_SIZE"] == 50

        healthy = client.post(
            f"{base_url}/simulation/run",
            json={
                "request_volume": 40,
                "acknowledge_simulation_only": True,
            },
        )
        assert healthy.status_code == 200
        healthy_metrics = healthy.json()
        assert healthy_metrics["error_rate_percent"] == 0

        injected = client.post(
            f"{base_url}/simulation/failure-injection",
            json={"acknowledge_simulation_only": True},
        )
        assert injected.status_code == 200
        assert injected.json()["configuration"]["DB_POOL_SIZE"] == 10

        failure = client.post(
            f"{base_url}/simulation/run",
            json={
                "request_volume": 40,
                "acknowledge_simulation_only": True,
            },
        )
        assert failure.status_code == 200
        failure_metrics = failure.json()
        assert failure_metrics["state"] == "FAILURE"
        assert failure_metrics["error_rate_percent"] > 0
        assert (
            failure_metrics["p95_latency_ms"]
            > healthy_metrics["p95_latency_ms"]
        )
        assert any(
            "database connection timeout" in (sample.get("error") or "")
            for sample in failure_metrics["samples"]
        )

        rollback = client.post(
            f"{base_url}/simulation/rollback",
            json={"acknowledge_simulation_only": True},
        )
        assert rollback.status_code == 200
        assert rollback.json()["configuration"]["DB_POOL_SIZE"] == 50

        recovered = client.post(
            f"{base_url}/simulation/run",
            json={
                "request_volume": 40,
                "acknowledge_simulation_only": True,
            },
        )
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "HEALTHY"
        assert recovered.json()["error_rate_percent"] == 0

        report = client.get(f"{base_url}/simulation/report")
        assert report.status_code == 200
        assert len(report.json()["deployment_events"]) == 3