from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Action,
    Deployment,
    Evidence,
    Incident,
    IncidentTimelineEvent,
    KnowledgeDocument,
    LogEvent,
    Metric,
    Postmortem,
    Recommendation,
    Service,
)


def seed_demo_data(db: Session) -> bool:
    """Insert the Checkout Service demo dataset once.

    Returns True when rows were inserted and False when the demo already exists.
    The dataset is deliberately static and deterministic; it does not call an LLM.
    """
    service = db.scalar(
        select(Service).where(
            Service.name == "Checkout Service",
            Service.environment == "production",
        )
    )
    if service is None:
        service = Service(
            name="Checkout Service",
            description="Processes cart checkout, payment authorization, and order creation.",
            environment="production",
            owner_team="Commerce SRE",
        )
        db.add(service)
        db.flush()

    existing_incident = db.scalar(
        select(Incident).where(
            Incident.title == "Checkout error spike after database pool configuration change"
        )
    )
    if existing_incident is not None:
        if not existing_incident.timeline_events:
            db.add(
                IncidentTimelineEvent(
                    incident=existing_incident,
                    occurred_at=existing_incident.started_at,
                    event_type="timeline_baseline",
                    summary=(
                        "Timeline baseline added; activity before timeline tracking "
                        "was not recorded."
                    ),
                    details={"source": "phase3_seed_backfill"},
                )
            )
            db.commit()
        return False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    incident = Incident(
        service=service,
        title="Checkout error spike after database pool configuration change",
        description=(
            "Checkout failures increased during a traffic ramp after the latest deployment. "
            "Synthetic evidence points to database connection-pool exhaustion."
        ),
        severity="SEV-2",
        status="investigating",
        started_at=now - timedelta(minutes=42),
    )
    db.add(incident)
    db.flush()
    db.add(
        IncidentTimelineEvent(
            incident=incident,
            occurred_at=incident.started_at,
            event_type="incident_created",
            summary="Synthetic Checkout Service incident created.",
            details={"source": "synthetic_seed", "severity": incident.severity},
        )
    )

    deployment = Deployment(
        service=service,
        incident=incident,
        version="checkout-2026.09.30.3",
        commit_sha="a91c7e2",
        environment="production",
        deployed_at=now - timedelta(minutes=58),
        change_summary="Tune database pool settings for checkout worker concurrency.",
        config_changes={
            "DB_POOL_SIZE": {"before": 50, "after": 10},
            "DB_POOL_TIMEOUT_SECONDS": {"before": 5, "after": 2},
        },
    )
    db.add(deployment)

    logs = [
        LogEvent(
            service=service,
            incident=incident,
            occurred_at=now - timedelta(minutes=41),
            level="ERROR",
            message="database connection timeout while creating checkout transaction",
            source="checkout-api/pod-7f89d",
            trace_id="trace-checkout-001",
        ),
        LogEvent(
            service=service,
            incident=incident,
            occurred_at=now - timedelta(minutes=37),
            level="WARN",
            message="connection pool exhausted: active=10 idle=0 waiting=27",
            source="checkout-api/pod-7f89d",
            trace_id="trace-checkout-002",
        ),
        LogEvent(
            service=service,
            incident=incident,
            occurred_at=now - timedelta(minutes=28),
            level="ERROR",
            message="checkout request failed after 2000ms waiting for a database connection",
            source="checkout-api/pod-81a2c",
            trace_id="trace-checkout-003",
        ),
        LogEvent(
            service=service,
            incident=incident,
            occurred_at=now - timedelta(minutes=12),
            level="INFO",
            message="traffic autoscaler increased checkout-api replicas from 8 to 12",
            source="checkout-api/controller",
            trace_id="trace-checkout-004",
        ),
    ]
    db.add_all(logs)

    metric_values = [
        ("checkout_error_rate", 0.8, "%", 42),
        ("checkout_error_rate", 18.7, "%", 28),
        ("checkout_error_rate", 31.4, "%", 8),
        ("checkout_p95_latency", 420.0, "ms", 42),
        ("checkout_p95_latency", 1840.0, "ms", 28),
        ("checkout_p95_latency", 2670.0, "ms", 8),
        ("db_pool_active_connections", 8.0, "connections", 42),
        ("db_pool_active_connections", 10.0, "connections", 28),
        ("db_pool_waiting_requests", 2.0, "requests", 42),
        ("db_pool_waiting_requests", 27.0, "requests", 28),
    ]
    metrics = [
        Metric(
            service=service,
            incident=incident,
            recorded_at=now - timedelta(minutes=minutes_ago),
            name=name,
            value=value,
            unit=unit,
        )
        for name, value, unit, minutes_ago in metric_values
    ]
    db.add_all(metrics)

    runbook = KnowledgeDocument(
        title="Checkout database connection pool runbook",
        document_type="runbook",
        source="sre/runbooks/checkout-db-pool.md",
        content=(
            "If checkout database waiters increase after a deployment, compare DB_POOL_SIZE "
            "with the last known healthy value. Validate traffic and replica count before "
            "changing pool settings. Roll back the configuration change when pool exhaustion "
            "is confirmed."
        ),
    )
    historical_incident = KnowledgeDocument(
        title="Historical incident: checkout pool exhaustion",
        document_type="historical_incident",
        source="postmortems/checkout-2026-07-14.md",
        content=(
            "A checkout release reduced DB_POOL_SIZE from 50 to 10. Under peak traffic, "
            "connection timeouts caused elevated checkout errors. Restoring the pool size "
            "to 50 returned error rate and latency to baseline."
        ),
    )
    db.add_all([runbook, historical_incident])
    db.flush()

    evidence = [
        Evidence(
            incident=incident,
            evidence_type="log",
            summary="Connection timeout and pool exhaustion messages appear in checkout pods.",
            relevance_score=0.98,
            log_event=logs[0],
        ),
        Evidence(
            incident=incident,
            evidence_type="deployment",
            summary="The latest production deployment changed DB_POOL_SIZE from 50 to 10.",
            relevance_score=0.99,
            deployment=deployment,
        ),
        Evidence(
            incident=incident,
            evidence_type="metric",
            summary="Error rate rose from 0.8% to 31.4% while p95 latency rose to 2670ms.",
            relevance_score=0.96,
            metric=metrics[2],
        ),
        Evidence(
            incident=incident,
            evidence_type="runbook",
            summary="The checkout runbook identifies a reduced pool size as a likely cause of waiters.",
            relevance_score=0.91,
            knowledge_document=runbook,
        ),
        Evidence(
            incident=incident,
            evidence_type="historical_incident",
            summary="A prior checkout incident recovered after restoring DB_POOL_SIZE to 50.",
            relevance_score=0.89,
            knowledge_document=historical_incident,
        ),
    ]
    db.add_all(evidence)

    recommendation = Recommendation(
        incident=incident,
        title="Restore the checkout database pool size",
        rationale=(
            "The deployment change, pool waiter logs, traffic growth, and historical incident "
            "all align with database connection-pool exhaustion."
        ),
        proposed_change="Set DB_POOL_SIZE from 10 back to 50 in the simulated checkout environment.",
        risk_level="low",
        status="pending_approval",
    )
    db.add(recommendation)
    db.flush()

    db.add(
        Action(
            incident=incident,
            recommendation=recommendation,
            action_type="restore_db_pool_size",
            status="proposed",
            approval_status="not_requested",
            simulation_only=True,
            details={"parameter": "DB_POOL_SIZE", "current": 10, "target": 50},
        )
    )

    db.add(
        Postmortem(
            incident=incident,
            status="draft",
            summary=(
                "Checkout requests are failing during increased traffic after a deployment "
                "reduced the database connection pool."
            ),
            root_cause=(
                "Synthetic incident record: DB_POOL_SIZE changed from 50 to 10, causing "
                "connection-pool exhaustion under increased checkout traffic."
            ),
            impact="Elevated checkout errors and latency; no production action has been executed.",
            timeline=[
                {"at": (now - timedelta(minutes=58)).isoformat(), "event": "Deployment completed"},
                {"at": (now - timedelta(minutes=42)).isoformat(), "event": "Incident started"},
                {"at": (now - timedelta(minutes=28)).isoformat(), "event": "Timeouts increased"},
            ],
            follow_up_items=[
                "Validate pool sizing against peak replica count.",
                "Add a deployment guardrail for unsafe pool reductions.",
            ],
        )
    )

    db.commit()
    return True
