from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedRead(DatabaseSchema):
    id: int
    created_at: datetime
    updated_at: datetime


class ServiceBase(DatabaseSchema):
    name: str = Field(min_length=1, max_length=120)
    description: str
    environment: str = "production"
    owner_team: str


class ServiceCreate(ServiceBase):
    pass


class ServiceRead(ServiceBase, TimestampedRead):
    pass


class IncidentBase(DatabaseSchema):
    service_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str
    severity: str = "SEV-3"
    status: str = "investigating"
    started_at: datetime
    resolved_at: datetime | None = None


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase, TimestampedRead):
    pass


class IncidentSignals(DatabaseSchema):
    error_rate_percent: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    db_pool_waiters: int | None = Field(default=None, ge=0)


class IncidentCreate(DatabaseSchema):
    service_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Literal["SEV-1", "SEV-2", "SEV-3", "SEV-4"] | None = None
    status: Literal["open", "investigating"] = "investigating"
    signals: IncidentSignals = Field(default_factory=IncidentSignals)


class IncidentStatusUpdate(DatabaseSchema):
    status: Literal["open", "investigating", "mitigated", "resolved", "closed"]
    note: str | None = Field(default=None, max_length=1000)


class IncidentSeverityUpdate(DatabaseSchema):
    signals: IncidentSignals


class TimelineEventRead(TimestampedRead):
    incident_id: int
    occurred_at: datetime
    event_type: str
    summary: str
    details: dict[str, Any]


class IncidentDetail(IncidentRead):
    service: ServiceRead
    timeline: list[TimelineEventRead]
    logs: list["LogEventRead"]
    deployments: list["DeploymentRead"]
    metrics: list["MetricRead"]
    evidence: list["EvidenceRead"]


class LogEventBase(DatabaseSchema):
    incident_id: int
    service_id: int
    occurred_at: datetime
    level: str
    message: str
    source: str
    trace_id: str | None = None


class LogEventCreate(LogEventBase):
    pass


class LogEventRead(LogEventBase, TimestampedRead):
    pass


class LogEventIngest(DatabaseSchema):
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: Literal["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"]
    message: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=120)
    trace_id: str | None = Field(default=None, max_length=120)


class DeploymentBase(DatabaseSchema):
    service_id: int
    incident_id: int | None = None
    version: str
    commit_sha: str
    environment: str
    deployed_at: datetime
    change_summary: str
    config_changes: dict[str, Any] = Field(default_factory=dict)


class DeploymentCreate(DeploymentBase):
    pass


class DeploymentRead(DeploymentBase, TimestampedRead):
    pass


class DeploymentIngest(DatabaseSchema):
    version: str = Field(min_length=1, max_length=80)
    commit_sha: str = Field(min_length=1, max_length=64)
    environment: str = Field(min_length=1, max_length=40)
    deployed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    change_summary: str = Field(min_length=1)
    config_changes: dict[str, Any] = Field(default_factory=dict)


class MetricBase(DatabaseSchema):
    incident_id: int
    service_id: int
    recorded_at: datetime
    name: str
    value: float
    unit: str


class MetricCreate(MetricBase):
    pass


class MetricRead(MetricBase, TimestampedRead):
    pass


class MetricIngest(DatabaseSchema):
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    name: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=30)


class KnowledgeDocumentBase(DatabaseSchema):
    title: str
    document_type: str
    source: str
    content: str


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    pass


class KnowledgeDocumentRead(KnowledgeDocumentBase, TimestampedRead):
    pass


class EvidenceBase(DatabaseSchema):
    incident_id: int
    evidence_type: str
    summary: str
    relevance_score: float | None = None
    log_event_id: int | None = None
    deployment_id: int | None = None
    metric_id: int | None = None
    knowledge_document_id: int | None = None


class EvidenceCreate(EvidenceBase):
    pass


class EvidenceRead(EvidenceBase, TimestampedRead):
    pass


class EvidenceIngest(DatabaseSchema):
    evidence_type: str = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1)
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    log_event_id: int | None = Field(default=None, gt=0)
    deployment_id: int | None = Field(default=None, gt=0)
    metric_id: int | None = Field(default=None, gt=0)
    knowledge_document_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_source_reference(self) -> "EvidenceIngest":
        if not any(
            (
                self.log_event_id,
                self.deployment_id,
                self.metric_id,
                self.knowledge_document_id,
            )
        ):
            raise ValueError("Evidence must reference at least one source record.")
        return self


class RecommendationBase(DatabaseSchema):
    incident_id: int
    title: str
    rationale: str
    proposed_change: str
    risk_level: str
    status: str = "draft"


class RecommendationCreate(RecommendationBase):
    pass


class RecommendationRead(RecommendationBase, TimestampedRead):
    pass


class ActionBase(DatabaseSchema):
    incident_id: int
    recommendation_id: int | None = None
    action_type: str
    status: str = "proposed"
    approval_status: str = "not_requested"
    simulation_only: bool = True
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ActionCreate(ActionBase):
    pass


class ActionRead(ActionBase, TimestampedRead):
    pass


class PostmortemBase(DatabaseSchema):
    incident_id: int
    status: str = "draft"
    summary: str
    root_cause: str
    impact: str
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    follow_up_items: list[str] = Field(default_factory=list)


class PostmortemCreate(PostmortemBase):
    pass


class PostmortemRead(PostmortemBase, TimestampedRead):
    pass


IncidentDetail.model_rebuild()
