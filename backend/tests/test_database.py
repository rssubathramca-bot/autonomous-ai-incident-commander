from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Action,
    Deployment,
    Evidence,
    Incident,
    KnowledgeDocument,
    LogEvent,
    Metric,
    Postmortem,
    Recommendation,
    Service,
)
from backend.app.db.schemas import IncidentRead, ServiceRead
from backend.app.db.seed import seed_demo_data


def test_checkout_seed_is_relational_and_idempotent() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        assert seed_demo_data(db) is True
        assert seed_demo_data(db) is False

        service = db.scalar(select(Service).where(Service.name == "Checkout Service"))
        incident = db.scalar(
            select(Incident).where(
                Incident.title == "Checkout error spike after database pool configuration change"
            )
        )

        assert service is not None
        assert incident is not None
        assert incident.service is service
        assert len(incident.timeline_events) == 1
        assert incident.timeline_events[0].event_type == "incident_created"
        assert len(incident.log_events) == 4
        assert len(incident.deployments) == 1
        assert len(incident.metrics) == 10
        assert len(incident.evidence) == 5
        assert incident.recommendation is not None
        assert len(incident.actions) == 1
        assert incident.postmortem is not None

        assert db.query(Service).count() == 1
        assert db.query(Incident).count() == 1
        assert db.query(LogEvent).count() == 4
        assert db.query(Deployment).count() == 1
        assert db.query(Metric).count() == 10
        assert db.query(KnowledgeDocument).count() == 2
        assert db.query(Evidence).count() == 5
        assert db.query(Recommendation).count() == 1
        assert db.query(Action).count() == 1
        assert db.query(Postmortem).count() == 1

        service_schema = ServiceRead.model_validate(service)
        incident_schema = IncidentRead.model_validate(incident)
        assert service_schema.name == "Checkout Service"
        assert incident_schema.service_id == service.id
        assert incident_schema.severity == "SEV-2"
