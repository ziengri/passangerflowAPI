from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db
from app.errors import BadRequestError
from app.utils.iso_datetime import format_iso8601_utc_output, parse_iso8601_datetime

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


def _build_status_snapshot(
    payload: schemas.DeviceStatusSnapshot,
    normalized_bus: str,
    reported_at_iso: str,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "bus": normalized_bus,
        "reportedAt": reported_at_iso,
        "cameras": payload.cameras,
        "services": payload.services,
    }
    if payload.connectivity is not None:
        snapshot["connectivity"] = payload.connectivity
    if payload.storage is not None:
        snapshot["storage"] = payload.storage
    if payload.buffers is not None:
        snapshot["buffers"] = payload.buffers
    return snapshot


@router.post("/device-status", response_model=schemas.DeviceStatusUpsertResponse)
def upsert_device_status(
    payload: schemas.DeviceStatusSnapshot,
    db: Session = Depends(get_db),
) -> schemas.DeviceStatusUpsertResponse:
    reported_at = parse_iso8601_datetime(payload.reported_at, field_name="reportedAt")
    normalized_bus = payload.bus.strip()
    reported_at_iso = format_iso8601_utc_output(reported_at)
    snapshot = _build_status_snapshot(payload, normalized_bus, reported_at_iso)

    _current_status, applied = crud.upsert_current_status(
        db=db,
        bus_number=payload.bus,
        reported_at=reported_at,
        snapshot=snapshot,
        inferred_camera_count=crud.infer_monitoring_camera_count(payload.cameras),
    )

    return schemas.DeviceStatusUpsertResponse(
        bus=normalized_bus,
        reported_at=reported_at_iso,
        applied=applied,
    )


@router.get(
    "/device-status",
    response_model=list[schemas.DeviceStatusSnapshot],
    response_model_exclude_none=True,
)
def get_device_statuses(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    statuses = crud.list_device_current_statuses(db)
    return [crud.serialize_device_current_status(status) for status in statuses]


@router.get(
    "/device-status/{bus}",
    response_model=schemas.DeviceStatusSnapshot,
    response_model_exclude_none=True,
)
def get_device_status(bus: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_status = crud.get_device_current_status_or_404(db, bus)
    return crud.serialize_device_current_status(current_status)


@router.post("/device-events/batch", response_model=schemas.DeviceEventsBatchResponse)
def create_device_events_batch(
    payload: schemas.DeviceEventsBatchRequest,
    db: Session = Depends(get_db),
) -> schemas.DeviceEventsBatchResponse:
    normalized_events = [
        {
            "event_id": event.event_id,
            "occurred_at": parse_iso8601_datetime(event.occurred_at, field_name="occurredAt"),
            "kind": event.kind,
            "component": event.component,
            "severity": event.severity,
            "message": event.message,
            "details": event.details,
        }
        for event in payload.events
    ]

    inserted, duplicates = crud.insert_events_batch(
        db=db,
        bus_number=payload.bus,
        events=normalized_events,
    )

    return schemas.DeviceEventsBatchResponse(
        bus=payload.bus.strip(),
        received=len(payload.events),
        inserted=inserted,
        duplicates=duplicates,
    )


@router.get("/device-events", response_model=list[schemas.DeviceEventResponse])
def get_device_events(
    bus: str | None = None,
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    occurred_from = (
        parse_iso8601_datetime(from_value, field_name="from") if from_value is not None else None
    )
    occurred_to = parse_iso8601_datetime(to_value, field_name="to") if to_value is not None else None

    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise BadRequestError("`from` must be less than or equal to `to`.")

    events = crud.list_device_events(
        db=db,
        bus_number=bus,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        kind=kind,
        limit=limit,
    )
    return [crud.serialize_device_event(event) for event in events]
