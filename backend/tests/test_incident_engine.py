from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Service
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = Session(engine)
    test_session.add(
        Service(
            name="Checkout Service",
            description="Processes checkout requests.",
            environment="production",
            owner_team="Commerce SRE",
        )
    )
    test_session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        test_session.close()
        engine.dispose()


def create_incident(client: TestClient, **overrides: object) -> dict:
    payload = {
        "service_id": 1,
        "title": "Checkout latency elevated",
        "description": "Synthetic incident for deterministic engine verification.",
        **overrides,
    }
    response = client.post("/incidents", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_retrieve_assign_severity_and_status_timeline(client: TestClient) -> None:
    incident = create_incident(
        client,
        signals={
            "error_rate_percent": 22,
            "latency_ms": 2100,
            "db_pool_waiters": 24,
        },
    )
    incident_id = incident["id"]
    assert incident["severity"] == "SEV-2"
    assert incident["status"] == "investigating"
    assert incident["service"]["name"] == "Checkout Service"
    assert [event["event_type"] for event in incident["timeline"]] == [
        "incident_created"
    ]

    response = client.get(f"/incidents/{incident_id}")
    assert response.status_code == 200
    assert response.json()["id"] == incident_id

    resolved = client.patch(
        f"/incidents/{incident_id}/status",
        json={"status": "resolved", "note": "Metrics returned to baseline."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    assert resolved.json()["timeline"][-1]["details"]["note"] == (
        "Metrics returned to baseline."
    )

    reopened = client.patch(
        f"/incidents/{incident_id}/status",
        json={"status": "investigating"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None
    assert len(reopened.json()["timeline"]) == 3

    forbidden = client.patch(
        f"/incidents/{incident_id}/status",
        json={"status": "closed"},
    )
    assert forbidden.status_code == 409


def test_store_logs_deployments_metrics_and_traceable_evidence(
    client: TestClient,
) -> None:
    incident_id = create_incident(client)["id"]

    log = client.post(
        f"/incidents/{incident_id}/logs",
        json={
            "level": "ERROR",
            "message": "database connection timeout",
            "source": "checkout-api/pod-1",
        },
    )
    assert log.status_code == 201
    assert log.json()["service_id"] == 1

    deployment = client.post(
        f"/incidents/{incident_id}/deployments",
        json={
            "version": "checkout-1.2.3",
            "commit_sha": "abc1234",
            "environment": "production",
            "change_summary": "Reduced database pool size.",
            "config_changes": {"DB_POOL_SIZE": {"before": 50, "after": 10}},
        },
    )
    assert deployment.status_code == 201

    metric = client.post(
        f"/incidents/{incident_id}/metrics",
        json={
            "name": "checkout_error_rate",
            "value": 24.1,
            "unit": "%",
        },
    )
    assert metric.status_code == 201

    evidence = client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "evidence_type": "log",
            "summary": "Connection timeout observed.",
            "relevance_score": 0.95,
            "log_event_id": log.json()["id"],
        },
    )
    assert evidence.status_code == 201

    detail = client.get(f"/incidents/{incident_id}").json()
    assert len(detail["logs"]) == 1
    assert len(detail["deployments"]) == 1
    assert len(detail["metrics"]) == 1
    assert len(detail["evidence"]) == 1
    assert len(detail["timeline"]) == 5

    assert len(client.get(f"/incidents/{incident_id}/evidence").json()) == 1
    assert len(client.get(f"/incidents/{incident_id}/metrics").json()) == 1


def test_severity_threshold_endpoint_and_related_resource_validation(
    client: TestClient,
) -> None:
    incident_id = create_incident(client)["id"]
    assignment = client.post(
        f"/incidents/{incident_id}/severity",
        json={
            "signals": {
                "error_rate_percent": 52,
                "latency_ms": 6500,
                "db_pool_waiters": 60,
            }
        },
    )
    assert assignment.status_code == 200
    assert assignment.json()["severity"] == "SEV-1"
    assert assignment.json()["timeline"][-1]["event_type"] == "severity_changed"

    missing_source = client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "evidence_type": "metric",
            "summary": "Unrelated metric reference.",
            "metric_id": 999,
        },
    )
    assert missing_source.status_code == 422


def test_missing_incident_and_service_are_reported(client: TestClient) -> None:
    assert client.get("/incidents/999").status_code == 404
    assert client.get("/incidents/999/evidence").status_code == 404

    response = client.post(
        "/incidents",
        json={
            "service_id": 999,
            "title": "Unknown service",
            "description": "This should fail.",
        },
    )
    assert response.status_code == 404


def test_invalid_payload_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/incidents",
        json={
            "service_id": 1,
            "title": "",
            "description": "Missing title.",
            "signals": {"error_rate_percent": -1},
        },
    )
    assert response.status_code == 422