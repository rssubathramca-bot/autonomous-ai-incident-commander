from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Service(TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("name", "environment", name="uq_service_name_environment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="production")
    owner_team: Mapped[str] = mapped_column(String(120), nullable=False)

    incidents: Mapped[list[Incident]] = relationship(back_populates="service")
    log_events: Mapped[list[LogEvent]] = relationship(back_populates="service")
    deployments: Mapped[list[Deployment]] = relationship(back_populates="service")
    metrics: Mapped[list[Metric]] = relationship(back_populates="service")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="SEV-3")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="investigating")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service: Mapped[Service] = relationship(back_populates="incidents")
    timeline_events: Mapped[list[IncidentTimelineEvent]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentTimelineEvent.occurred_at",
    )
    log_events: Mapped[list[LogEvent]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    deployments: Mapped[list[Deployment]] = relationship(back_populates="incident")
    metrics: Mapped[list[Metric]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    recommendation: Mapped[Recommendation | None] = relationship(
        back_populates="incident",
        uselist=False,
        cascade="all, delete-orphan",
    )
    actions: Mapped[list[Action]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    postmortem: Mapped[Postmortem | None] = relationship(
        back_populates="incident",
        uselist=False,
        cascade="all, delete-orphan",
    )


class IncidentTimelineEvent(TimestampMixin, Base):
    __tablename__ = "incident_timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    incident: Mapped[Incident] = relationship(back_populates="timeline_events")


class LogEvent(TimestampMixin, Base):
    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(120))

    incident: Mapped[Incident] = relationship(back_populates="log_events")
    service: Mapped[Service] = relationship(back_populates="log_events")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="log_event")


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"),
        index=True,
    )
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    config_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    service: Mapped[Service] = relationship(back_populates="deployments")
    incident: Mapped[Incident | None] = relationship(back_populates="deployments")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="deployment")


class Metric(TimestampMixin, Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="metrics")
    service: Mapped[Service] = relationship(back_populates="metrics")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="metric")


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    evidence: Mapped[list[Evidence]] = relationship(back_populates="knowledge_document")


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    log_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("log_events.id", ondelete="SET NULL"),
        index=True,
    )
    deployment_id: Mapped[int | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"),
        index=True,
    )
    metric_id: Mapped[int | None] = mapped_column(
        ForeignKey("metrics.id", ondelete="SET NULL"),
        index=True,
    )
    knowledge_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        index=True,
    )

    incident: Mapped[Incident] = relationship(back_populates="evidence")
    log_event: Mapped[LogEvent | None] = relationship(back_populates="evidence")
    deployment: Mapped[Deployment | None] = relationship(back_populates="evidence")
    metric: Mapped[Metric | None] = relationship(back_populates="evidence")
    knowledge_document: Mapped[KnowledgeDocument | None] = relationship(
        back_populates="evidence",
    )


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_change: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")

    incident: Mapped[Incident] = relationship(back_populates="recommendation")
    actions: Mapped[list[Action]] = relationship(back_populates="recommendation")


class Action(TimestampMixin, Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="proposed")
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_requested")
    simulation_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    incident: Mapped[Incident] = relationship(back_populates="actions")
    recommendation: Mapped[Recommendation | None] = relationship(back_populates="actions")


class Postmortem(TimestampMixin, Base):
    __tablename__ = "postmortems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    follow_up_items: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    incident: Mapped[Incident] = relationship(back_populates="postmortem")
