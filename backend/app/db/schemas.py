from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
