from __future__ import annotations

import json
from collections.abc import Generator
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import RootCauseAnalysisRecord
from backend.app.db.seed import seed_demo_data
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services import root_cause_analysis as analysis_service
from backend.app.services.root_cause_analysis import AnalysisConfig


RAG_TEXT = "The checkout pool runbook recommends checking pool size and waiters."
SIMULATION_REPORT = {
    "simulation_only": True,
    "state": "FAILURE",
    "configuration": {"DB_POOL_SIZE": 10},
    "metrics": {
        "request_volume": 100,
        "error_count": 75,
        "error_rate_percent": 75.0,
        "p95_latency_ms": 820.0,
        "DB_POOL_SIZE": 10,
    },
    "request_runs": [
        {
            "state": "FAILURE",
            "occurred_at": "2026-10-02T10:00:00+00:00",
            "request_volume": 100,
            "error_count": 75,
            "error_rate_percent": 75.0,
            "p95_latency_ms": 820.0,
        }
    ],
    "deployment_events": [
        {
            "event_type": "failure_injection_deployment",
            "occurred_at": "2026-10-02T09:59:00+00:00",
            "service": "checkout-service",
            "config_changes": {"DB_POOL_SIZE": {"before": 50, "after": 10}},
            "simulation_only": True,
        }
    ],
    "application_logs": [
        {
            "timestamp": "2026-10-02T10:00:01+00:00",
            "service": "checkout-service",
            "level": "ERROR",
            "message": "Database pool acquisition timed out.",
            "details": {"simulation_only": True},
        }
    ],
}
MODEL_OUTPUT = {
    "summary": "The supplied evidence is consistent with checkout database-pool pressure.",
    "hypotheses": [
        {
            "hypothesis_id": "H1",
            "statement": "Database-pool pressure contributed to checkout timeouts.",
            "supporting_evidence": [
                {"evidence_id": "E1", "reason": "The incident log summary records errors."}
            ],
            "contradicting_evidence": [],
            "confidence": 0.72,
        }
    ],
    "primary_hypothesis": {
        "hypothesis_id": "H1",
        "reason": "The available log evidence is consistent with this explanation.",
        "supporting_evidence_ids": ["E1"],
        "confidence": 0.72,
        "uncertainty": "The evidence does not independently prove causation.",
    },
    "evidence_chain": ["E1"],
    "uncertainties": ["No independent database-side telemetry was supplied."],
    "recommended_next_checks": ["Compare pool waiters with database-side connection telemetry."],
}


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with session_factory() as db:
        seed_demo_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    def fake_search(
        _db: Session,
        _provider: object,
        *,
        query: str,
        top_k: int,
    ) -> list[tuple[object, float]]:
        assert query
        assert top_k == 5
        return [
            (
                SimpleNamespace(
                    text=RAG_TEXT,
                    chunk_metadata={
                        "title": "Checkout Pool Runbook",
                        "source": "knowledge/runbooks/checkout.md",
                        "document_id": "RUNBOOK-CHECKOUT-DB-001",
                    },
                ),
                0.91,
            )
        ]

    def fake_simulation_get(url: str, *, timeout: float) -> httpx.Response:
        assert url == analysis_service.SIMULATION_REPORT_URL
        assert timeout == 1.0
        return httpx.Response(
            200,
            json=SIMULATION_REPORT,
            request=httpx.Request("GET", url),
        )

    monkeypatch.setenv("GEMINI_API_KEY", "mock-only-not-a-real-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(analysis_service, "get_embedding_provider", lambda: object())
    monkeypatch.setattr(analysis_service, "search_knowledge_chunks", fake_search)
    monkeypatch.setattr(analysis_service.httpx, "get", fake_simulation_get)
    analysis_service.clear_analysis_cache()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        analysis_service.clear_analysis_cache()
        engine.dispose()


def mock_gemini_response(
    monkeypatch: pytest.MonkeyPatch,
    output: object = MODEL_OUTPUT,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        if isinstance(output, str):
            text = output
        else:
            text = json.dumps(output)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(analysis_service.httpx, "post", fake_post)
    return calls


def analyze(client: TestClient, incident_id: int = 1) -> httpx.Response:
    return client.post("/incidents/analyze", json={"incident_id": incident_id})


def analyze_persisted(client: TestClient, incident_id: int = 1) -> httpx.Response:
    return client.post(f"/incidents/{incident_id}/root-cause-analysis")


def test_analysis_model_default_matches_configured_replit_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    assert AnalysisConfig.from_env().model == "gemini-3.8-flash"


def test_missing_api_key_fails_safely_without_calling_gemini(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY")
    calls = mock_gemini_response(monkeypatch)

    response = analyze(api)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "gemini_not_configured"
    assert "mock-only-not-a-real-key" not in response.text
    assert calls == []


def test_analysis_uses_deterministic_evidence_and_phase5_rag(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = mock_gemini_response(monkeypatch)

    response = analyze(api)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ai_call_count"] == 1
    assert result["cached"] is False
    assert result["analysis"]["hypotheses"][0]["confidence"] == 0.72
    assert result["incident"]["service"] == "Checkout Service"
    assert any(
        item["kind"] == "deployment" and "DB_POOL_SIZE" in item["summary"]
        for item in result["evidence"]
    )
    assert any("31.4" in item["summary"] for item in result["evidence"])
    assert any(
        item["kind"] == "simulation_metrics"
        and "error_rate_percent=75" in item["summary"]
        for item in result["evidence"]
    )
    assert any(
        item["kind"] == "simulation_deployment"
        and '"before":50' in item["summary"]
        for item in result["evidence"]
    )
    assert any(
        item["kind"] == "simulation_log"
        and "timed out" in item["summary"]
        for item in result["evidence"]
    )
    assert result["retrieved_evidence"][0]["document_id"] == (
        "RUNBOOK-CHECKOUT-DB-001"
    )
    prompt = calls[0]["json"]["contents"][0]["parts"][0]["text"]  # type: ignore[index]
    assert RAG_TEXT in prompt
    assert "E1" in prompt
    assert calls[0]["headers"]["x-goog-api-key"] == "mock-only-not-a-real-key"  # type: ignore[index]
    assert calls[0]["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-test-model:generateContent"
    )
    generation_config = calls[0]["json"]["generationConfig"]  # type: ignore[index]
    assert generation_config["responseMimeType"] == "application/json"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not JSON", "failed response validation"),
        ({"summary": "Required response fields are missing."}, "failed response validation"),
        (
            {
                **MODEL_OUTPUT,
                "hypotheses": [
                    {**MODEL_OUTPUT["hypotheses"][0], "confidence": 2.0}
                ],
            },
            "failed response validation",
        ),
        (
            {
                **MODEL_OUTPUT,
                "evidence_chain": ["E999"],
            },
            "evidence that was not provided",
        ),
    ],
)
def test_invalid_gemini_responses_are_rejected(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    output: object,
    message: str,
) -> None:
    mock_gemini_response(monkeypatch, output)

    response = analyze(api)

    assert response.status_code == 502
    assert message in response.json()["detail"]["message"].lower()


def test_identical_evidence_uses_cache_without_a_second_gemini_call(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = mock_gemini_response(monkeypatch)

    first = analyze(api)
    second = analyze(api)

    assert first.status_code == second.status_code == 200
    assert len(calls) == 1
    assert first.json()["ai_call_count"] == 1
    assert second.json()["ai_call_count"] == 0
    assert second.json()["cached"] is True
    assert second.json()["evidence"] == first.json()["evidence"]


def test_persisted_analysis_get_and_duplicate_post_do_not_call_gemini_again(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = mock_gemini_response(monkeypatch)

    created = analyze_persisted(api)

    assert created.status_code == 200, created.text
    assert created.json()["ai_call_count"] == 1
    assert len(calls) == 1
    stored = api.get("/incidents/1/root-cause-analysis")
    assert stored.status_code == 200
    assert stored.json() == created.json()
    assert len(calls) == 1

    repeated = analyze_persisted(api)
    assert repeated.status_code == 200
    assert repeated.json()["cached"] is True
    assert repeated.json()["ai_call_count"] == 0
    assert len(calls) == 1


def test_get_analysis_without_saved_record_returns_404_without_gemini(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = mock_gemini_response(monkeypatch)

    response = api.get("/incidents/1/root-cause-analysis")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "root_cause_analysis_not_found"
    assert calls == []


def test_empty_rag_results_are_reported_as_uncertainty(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_service,
        "search_knowledge_chunks",
        lambda *_args, **_kwargs: [],
    )
    mock_gemini_response(monkeypatch)

    response = analyze(api)

    assert response.status_code == 200
    assert response.json()["retrieved_evidence"] == []
    assert any(
        "no matching knowledge evidence" in item.lower()
        for item in response.json()["analysis"]["uncertainties"]
    )


def test_simulator_unavailable_is_reported_without_failing_analysis(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_get(_url: str, *, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("simulator is stopped")

    monkeypatch.setattr(analysis_service.httpx, "get", unavailable_get)
    mock_gemini_response(monkeypatch)

    response = analyze(api)

    assert response.status_code == 200
    assert not any(
        item["kind"].startswith("simulation_")
        for item in response.json()["evidence"]
    )
    assert any(
        "local phase 4 simulator report was unavailable"
        in item.lower()
        for item in response.json()["analysis"]["uncertainties"]
    )


def test_non_simulation_report_is_rejected(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = analysis_service.SIMULATION_REPORT_URL

    def non_simulation_get(_url: str, *, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": "FAILURE", "configuration": {"DB_POOL_SIZE": 1}},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(analysis_service.httpx, "get", non_simulation_get)
    mock_gemini_response(monkeypatch)

    response = analyze(api)

    assert response.status_code == 200
    assert not any(
        item["kind"].startswith("simulation_")
        for item in response.json()["evidence"]
    )
    assert any(
        "local phase 4 simulator report was unavailable"
        in item.lower()
        for item in response.json()["analysis"]["uncertainties"]
    )


def test_gemini_upstream_failure_is_sanitized(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "private-upstream-error-detail"
    calls: list[str] = []

    def failed_post(url: str, **_kwargs: object) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            500,
            text=sentinel,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(analysis_service.httpx, "post", failed_post)

    response = analyze(api)

    assert response.status_code == 502
    assert sentinel not in response.text
    assert "mock-only-not-a-real-key" not in response.text
    assert len(calls) == 1
    record = next(
        item for item in caplog.records
        if item.message == "gemini_analysis_request_failed"
    )
    assert record.upstream_status == 500


def test_invalid_incident_id_returns_not_found(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = mock_gemini_response(monkeypatch)

    response = analyze(api, incident_id=99999)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "incident_not_found"
    assert calls == []


def test_incident_without_telemetry_returns_insufficient_evidence(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = api.post(
        "/incidents",
        json={
            "service_id": 1,
            "title": "New incident without telemetry",
            "description": "No logs, metrics, deployments, or evidence have been recorded.",
        },
    )
    assert created.status_code == 201
    monkeypatch.setattr(
        analysis_service,
        "search_knowledge_chunks",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        analysis_service.httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            httpx.ConnectError("simulator is stopped")
        ),
    )
    calls = mock_gemini_response(monkeypatch)

    response = analyze(api, incident_id=created.json()["id"])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "insufficient_evidence"
    assert calls == []
