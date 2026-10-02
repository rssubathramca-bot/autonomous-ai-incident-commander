from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import RootCauseAnalysisRecord
from backend.app.db.schemas import (
    DeploymentIngest,
    DeploymentRead,
    EvidenceIngest,
    EvidenceRead,
    IncidentCreate,
    IncidentDetail,
    IncidentRead,
    IncidentSeverityUpdate,
    IncidentStatusUpdate,
    LogEventIngest,
    LogEventRead,
    MetricIngest,
    MetricRead,
    ServiceRead,
    TimelineEventRead,
)
from backend.app.db.session import get_db
from backend.app.services.root_cause_analysis import (
    AnalysisRequest,
    RootCauseAnalysisError,
    analyze_incident,
)
from backend.app.services.incident_engine import (
    EvidenceSourceNotFound,
    IncidentNotFound,
    InvalidStatusTransition,
    ServiceNotFound,
    assign_severity,
    create_incident,
    get_incident,
    list_incident_evidence,
    list_incident_metrics,
    store_deployment,
    store_evidence,
    store_log,
    store_metric,
    update_incident_severity,
    update_incident_status,
)


router = APIRouter(prefix="/incidents", tags=["incidents"])


def _detail_response(incident: object) -> IncidentDetail:
    base = IncidentRead.model_validate(incident).model_dump()
    return IncidentDetail(
        **base,
        service=ServiceRead.model_validate(incident.service),
        timeline=[
            TimelineEventRead.model_validate(event)
            for event in incident.timeline_events
        ],
        logs=[LogEventRead.model_validate(log) for log in incident.log_events],
        deployments=[
            DeploymentRead.model_validate(deployment)
            for deployment in incident.deployments
        ],
        metrics=[MetricRead.model_validate(metric) for metric in incident.metrics],
        evidence=[
            EvidenceRead.model_validate(evidence)
            for evidence in incident.evidence
        ],
    )


def _raise_not_found(error: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _saved_analysis_response(
    db: Session,
    incident_id: int,
) -> dict | None:
    record = db.scalar(
        select(RootCauseAnalysisRecord).where(
            RootCauseAnalysisRecord.incident_id == incident_id
        )
    )
    if record is None:
        return None
    result = dict(record.payload)
    result["ai_call_count"] = 0
    result["cached"] = True
    return result


def _analyze_and_persist(db: Session, incident_id: int) -> dict:
    saved = _saved_analysis_response(db, incident_id)
    if saved is not None:
        return saved

    result = analyze_incident(db, incident_id)
    db.add(
        RootCauseAnalysisRecord(
            incident_id=incident_id,
            payload=result,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request may have persisted the same incident while this
        # request was completing. Return that validated result without another
        # generation request.
        db.rollback()
        saved = _saved_analysis_response(db, incident_id)
        if saved is None:
            raise
        return saved
    return result


def _analysis_error_response(db: Session, incident_id: int) -> dict:
    try:
        return _analyze_and_persist(db, incident_id)
    except IncidentNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "incident_not_found",
                "message": "The requested incident was not found.",
            },
        ) from None
    except RootCauseAnalysisError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.public_message},
        ) from None


@router.post("/{incident_id}/root-cause-analysis")
def post_root_cause_analysis(
    incident_id: int,
    db: Session = Depends(get_db),
) -> dict:
    return _analysis_error_response(db, incident_id)


@router.get("/{incident_id}/root-cause-analysis")
def get_root_cause_analysis(
    incident_id: int,
    db: Session = Depends(get_db),
) -> dict:
    record = db.scalar(
        select(RootCauseAnalysisRecord).where(
            RootCauseAnalysisRecord.incident_id == incident_id
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "root_cause_analysis_not_found",
                "message": "No root-cause analysis exists for this incident.",
            },
        )
    return record.payload


@router.post("/analyze")
def post_incident_analysis(
    data: AnalysisRequest,
    db: Session = Depends(get_db),
) -> dict:
    return _analysis_error_response(db, data.incident_id)


@router.post("", response_model=IncidentDetail, status_code=status.HTTP_201_CREATED)
def post_incident(
    data: IncidentCreate,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        incident = create_incident(db, data)
        return _detail_response(get_incident(db, incident.id))
    except ServiceNotFound as error:
        _raise_not_found(error)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident_by_id(
    incident_id: int,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        return _detail_response(get_incident(db, incident_id))
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.patch("/{incident_id}/status", response_model=IncidentDetail)
def patch_incident_status(
    incident_id: int,
    data: IncidentStatusUpdate,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        incident = update_incident_status(db, incident_id, data)
        return _detail_response(get_incident(db, incident.id))
    except IncidentNotFound as error:
        _raise_not_found(error)
    except InvalidStatusTransition as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.post("/{incident_id}/severity", response_model=IncidentDetail)
def post_incident_severity(
    incident_id: int,
    data: IncidentSeverityUpdate,
    db: Session = Depends(get_db),
) -> IncidentDetail:
    try:
        incident = update_incident_severity(
            db,
            incident_id,
            assign_severity(data.signals),
            source="deterministic_thresholds",
            signals=data.signals,
        )
        return _detail_response(get_incident(db, incident.id))
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.get("/{incident_id}/evidence", response_model=list[EvidenceRead])
def get_incident_evidence(
    incident_id: int,
    db: Session = Depends(get_db),
) -> list[EvidenceRead]:
    try:
        return [
            EvidenceRead.model_validate(item)
            for item in list_incident_evidence(db, incident_id)
        ]
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.get("/{incident_id}/metrics", response_model=list[MetricRead])
def get_incident_metrics(
    incident_id: int,
    db: Session = Depends(get_db),
) -> list[MetricRead]:
    try:
        return [
            MetricRead.model_validate(item)
            for item in list_incident_metrics(db, incident_id)
        ]
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.post(
    "/{incident_id}/logs",
    response_model=LogEventRead,
    status_code=status.HTTP_201_CREATED,
)
def post_incident_log(
    incident_id: int,
    data: LogEventIngest,
    db: Session = Depends(get_db),
) -> LogEventRead:
    try:
        return LogEventRead.model_validate(store_log(db, incident_id, data))
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.post(
    "/{incident_id}/deployments",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
)
def post_incident_deployment(
    incident_id: int,
    data: DeploymentIngest,
    db: Session = Depends(get_db),
) -> DeploymentRead:
    try:
        return DeploymentRead.model_validate(
            store_deployment(db, incident_id, data)
        )
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.post(
    "/{incident_id}/metrics",
    response_model=MetricRead,
    status_code=status.HTTP_201_CREATED,
)
def post_incident_metric(
    incident_id: int,
    data: MetricIngest,
    db: Session = Depends(get_db),
) -> MetricRead:
    try:
        return MetricRead.model_validate(store_metric(db, incident_id, data))
    except IncidentNotFound as error:
        _raise_not_found(error)


@router.post(
    "/{incident_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
def post_incident_evidence(
    incident_id: int,
    data: EvidenceIngest,
    db: Session = Depends(get_db),
) -> EvidenceRead:
    try:
        return EvidenceRead.model_validate(
            store_evidence(db, incident_id, data)
        )
    except IncidentNotFound as error:
        _raise_not_found(error)
    except EvidenceSourceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error