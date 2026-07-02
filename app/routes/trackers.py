from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db
from app.utils.iso_datetime import format_iso8601_utc_output, parse_iso8601_datetime

router = APIRouter(prefix="/api/v1", tags=["trackers"])


@router.get("/trackers", response_model=list[schemas.TrackerItemResponse])
def get_trackers(db: Session = Depends(get_db)) -> list[schemas.TrackerItemResponse]:
    trackers = crud.list_trackers(db)
    return [
        schemas.TrackerItemResponse(
            deviceId=tracker.device_id,
            bus=tracker.bus_number,
        )
        for tracker in trackers
    ]


@router.put("/trackers/{device_id}/bus", response_model=schemas.TrackerBindingResponse)
def bind_tracker_to_bus(
    device_id: int,
    bus: str = Form(...),
    db: Session = Depends(get_db),
) -> schemas.TrackerBindingResponse:
    tracker = crud.bind_tracker_to_bus(db=db, device_id=device_id, bus_number=bus)
    return schemas.TrackerBindingResponse(deviceId=tracker.device_id, bus=tracker.bus_number)


@router.delete("/trackers/{device_id}/bus", response_model=schemas.TrackerBindingResponse)
def unbind_tracker_from_bus(
    device_id: int,
    db: Session = Depends(get_db),
) -> schemas.TrackerBindingResponse:
    tracker = crud.unbind_tracker_from_bus(db=db, device_id=device_id)
    return schemas.TrackerBindingResponse(deviceId=tracker.device_id, bus=tracker.bus_number)


@router.get("/trackers/{device_id}/timeline/window", response_model=schemas.TrackerTimelineWindowResponse)
def get_tracker_timeline_window(
    device_id: int,
    at: str = Query(...),
    db: Session = Depends(get_db),
) -> schemas.TrackerTimelineWindowResponse:
    requested_at = parse_iso8601_datetime(at, "at")
    nearest, points = crud.get_tracker_timeline_window(db=db, device_id=device_id, at=requested_at)
    return schemas.TrackerTimelineWindowResponse(
        deviceId=device_id,
        requestedAt=format_iso8601_utc_output(requested_at),
        nearestAt=format_iso8601_utc_output(nearest.navigation_time),
        points=[
            schemas.TrackerTimelinePointResponse(
                navigationTime=format_iso8601_utc_output(point.navigation_time),
                receivedTime=format_iso8601_utc_output(point.received_time),
                lat=point.latitude,
                lon=point.longitude,
                speed=point.speed,
                course=point.course,
                packetId=point.packet_id,
            )
            for point in points
        ],
    )
