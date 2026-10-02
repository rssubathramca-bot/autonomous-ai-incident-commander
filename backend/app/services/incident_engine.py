from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import (
    Deployment,
    Evidence,
    Incident,
    IncidentTimelineEvent,
    KnowledgeDocument,
    LogEvent,
    Metric,
    Service,
)
from backend.app.db.schemas import (
    DeploymentIngest,
    EvidenceIngest,
    IncidentCreate,
    IncidentSignals,
    IncidentStatusUpdate,
    LogEventIngest,
    MetricIngest,
)


class IncidentNotFound(Exception):
    pass


class ServiceNotFound(Exception):
    pass


class InvalidStatusTransition(Exception):
    pass


class EvidenceSourceNotFound(Exception):
    pass


SEVERITY_THRESHOLDS = {
    "SEV-1": {
        "error_rate_percent": 50.0,
        "latency_ms": 5000.0,
        "db_pool_waiters": 50,
    },
    "SEV-2": {
        "error_rate_percent": 20.0,
        "latency_ms": 2000.0,
        "db_pool_waiters": 20,
    },
    "SEV-3": {
        "error_rate_percent": 5.0,
        "latency_ms": 1000.0,
        "db_pool_waiters": 5,
    },
}

ALLOWED_STATUS_TRANSITIONS = {
    "open": {"investigating", "closed"},
    "investigating": {"mitigated", "resolved"},
    "mitigated": {"investigating", "resolved"},
    "resolved": {"investigating", "closed"},
    "closed": set(),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def assign_severity(signals: IncidentSignals) -> str:
    """Classify an incident using fixed, transparent operational thresholds."""
    values = signals.model_dump()
    for severity, thresholds in SEVERITY_THRESHOLDS.items():
        if any(
            values[name] is not None and values[name] >= threshold
            for name, threshold in thresholds.items()
        ):
            return severity
    return "SEV-4"


def _add_timeline_event(
    db: Session,
    incident: Incident,
    event_type: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> IncidentTimelineEvent:
    event = IncidentTimelineEvent(
        incident=incident,
        occurred_at=utc_now(),
        event_type=event_type,
        summary=summary,
        details=details or {},
    )
    db.add(event)
    return event


def _get_incident_or_raise(db: Session, incident_id: int) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentNotFound(f"Incident {incident_id} was not found.")
    return incident


def create_incident(db: Session, data: IncidentCreate) -> Incident:
    service = db.get(Service, data.service_id)
    if service is None:
        raise ServiceNotFound(f"Service {data.service_id} was not found.")

    severity = data.severity or assign_severity(data.signals)
    incident = Incident(
        service=service,
        title=data.title.strip(),
        description=data.description.strip(),
        severity=severity,
        status=data.status,
        started_at=data.started_at,
    )
    db.add(incident)
    db.flush()
    _add_timeline_event(
        db,
        incident,
        "incident_created",
        f"Incident created with status {incident.status} and severity {incident.severity}.",
        {
            "service_id": service.id,
            "status": incident.status,
            "severity": incident.severity,
            "severity_signals": data.signals.model_dump(exclude_none=True),
        },
    )
    db.commit()
    db.refresh(incident)
    return incident


def get_incident(db: Session, incident_id: int) -> Incident:
    statement = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.service),
            selectinload(Incident.timeline_events),
            selectinload(Incident.log_events),
            selectinload(Incident.deployments),
            selectinload(Incident.metrics),
            selectinload(Incident.evidence),
        )
    )
    incident = db.scalar(statement)
    if incident is None:
        raise IncidentNotFound(f"Incident {incident_id} was not found.")
    return incident


def update_incident_status(
    db: Session,
    incident_id: int,
    data: IncidentStatusUpdate,
) -> Incident:
    incident = _get_incident_or_raise(db, incident_id)
    previous_status = incident.status
    if data.status == previous_status:
        return incident

    if data.status not in ALLOWED_STATUS_TRANSITIONS.get(previous_status, set()):
        raise InvalidStatusTransition(
            f"Cannot change incident status from {previous_status} to {data.status}."
        )

    incident.status = data.status
    if data.status == "resolved":
        incident.resolved_at = utc_now()
    elif previous_status == "resolved":
        incident.resolved_at = None

    _add_timeline_event(
        db,
        incident,
        "status_changed",
        f"Status changed from {previous_status} to {data.status}.",
        {
            "previous_status": previous_status,
            "status": data.status,
            "note": data.note,
        },
    )
    db.commit()
    db.refresh(incident)
    return incident


def update_incident_severity(
    db: Session,
    incident_id: int,
    severity: str,
    source: str,
    signals: IncidentSignals | None = None,
) -> Incident:
    incident = _get_incident_or_raise(db, incident_id)
    previous_severity = incident.severity
    if previous_severity == severity:
        return incident

    incident.severity = severity
    _add_timeline_event(
        db,
        incident,
        "severity_changed",
        f"Severity changed from {previous_severity} to {severity}.",
        {
            "previous_severity": previous_severity,
            "severity": severity,
            "source": source,
            "signals": signals.model_dump(exclude_none=True) if signals else {},
        },
    )
    db.commit()
    db.refresh(incident)
    return incident


def _ensure_incident(db: Session, incident_id: int) -> Incident:
    return _get_incident_or_raise(db, incident_id)


def store_log(db: Session, incident_id: int, data: LogEventIngest) -> LogEvent:
    incident = _ensure_incident(db, incident_id)
    log = LogEvent(
        incident=incident,
        service_id=incident.service_id,
        occurred_at=data.occurred_at,
        level=data.level,
        message=data.message.strip(),
        source=data.source,
        trace_id=data.trace_id,
    )
    db.add(log)
    db.flush()
    _add_timeline_event(
        db,
        incident,
        "log_recorded",
        f"{data.level} log recorded from {data.source}.",
        {"log_event_id": log.id, "level": data.level, "source": data.source},
    )
    db.commit()
    db.refresh(log)
    return log


def store_deployment(
    db: Session,
    incident_id: int,
    data: DeploymentIngest,
) -> Deployment:
    incident = _ensure_incident(db, incident_id)
    deployment = Deployment(
        incident=incident,
        service_id=incident.service_id,
        version=data.version,
        commit_sha=data.commit_sha,
        environment=data.environment,
        deployed_at=data.deployed_at,
        change_summary=data.change_summary.strip(),
        config_changes=data.config_changes,
    )
    db.add(deployment)
    db.flush()
    _add_timeline_event(
        db,
        incident,
        "deployment_recorded",
        f"Deployment {data.version} recorded.",
        {"deployment_id": deployment.id, "version": data.version},
    )
    db.commit()
    db.refresh(deployment)
    return deployment


def store_metric(db: Session, incident_id: int, data: MetricIngest) -> Metric:
    incident = _ensure_incident(db, incident_id)
    metric = Metric(
        incident=incident,
        service_id=incident.service_id,
        recorded_at=data.recorded_at,
        name=data.name,
        value=data.value,
        unit=data.unit,
    )
    db.add(metric)
    db.flush()
    _add_timeline_event(
        db,
        incident,
        "metric_recorded",
        f"Metric {data.name} recorded at {data.value:g} {data.unit}.",
        {"metric_id": metric.id, "name": data.name, "value": data.value, "unit": data.unit},
    )
    db.commit()
    db.refresh(metric)
    return metric


def store_evidence(db: Session, incident_id: int, data: EvidenceIngest) -> Evidence:
    incident = _ensure_incident(db, incident_id)
    linked: dict[str, Any] = {}

    if data.log_event_id is not None:
        log = db.get(LogEvent, data.log_event_id)
        if log is None or log.incident_id != incident_id:
            raise EvidenceSourceNotFound("The referenced log event does not belong to this incident.")
        linked["log_event"] = log
    if data.deployment_id is not None:
        deployment = db.get(Deployment, data.deployment_id)
        if deployment is None or deployment.incident_id != incident_id:
            raise EvidenceSourceNotFound("The referenced deployment does not belong to this incident.")
        linked["deployment"] = deployment
    if data.metric_id is not None:
        metric = db.get(Metric, data.metric_id)
        if metric is None or metric.incident_id != incident_id:
            raise EvidenceSourceNotFound("The referenced metric does not belong to this incident.")
        linked["metric"] = metric
    if data.knowledge_document_id is not None:
        document = db.get(KnowledgeDocument, data.knowledge_document_id)
        if document is None:
            raise EvidenceSourceNotFound("The referenced knowledge document was not found.")
        linked["knowledge_document"] = document

    evidence = Evidence(
        incident=incident,
        evidence_type=data.evidence_type,
        summary=data.summary.strip(),
        relevance_score=data.relevance_score,
        **linked,
    )
    db.add(evidence)
    db.flush()
    _add_timeline_event(
        db,
        incident,
        "evidence_recorded",
        f"{data.evidence_type} evidence recorded.",
        {"evidence_id": evidence.id, "evidence_type": data.evidence_type},
    )
    db.commit()
    db.refresh(evidence)
    return evidence


def list_incident_evidence(db: Session, incident_id: int) -> list[Evidence]:
    _ensure_incident(db, incident_id)
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.incident_id == incident_id)
            .order_by(Evidence.created_at, Evidence.id)
        )
    )


def list_incident_metrics(db: Session, incident_id: int) -> list[Metric]:
    _ensure_incident(db, incident_id)
    return list(
        db.scalars(
            select(Metric)
            .where(Metric.incident_id == incident_id)
            .order_by(Metric.recorded_at, Metric.id)
        )
    )