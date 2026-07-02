from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db

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
