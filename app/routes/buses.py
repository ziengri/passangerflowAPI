from __future__ import annotations

from fastapi import APIRouter, Depends, Form, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db

router = APIRouter(prefix="/api/v1", tags=["buses"])


@router.get("/buses", response_model=list[schemas.BusItemResponse])
def get_buses(db: Session = Depends(get_db)) -> list[schemas.BusItemResponse]:
    buses = crud.list_buses(db)
    return [
        schemas.BusItemResponse(
            bus=bus.bus_number,
            cameras=list(range(1, bus.camera_count + 1)),
        )
        for bus in buses
    ]


@router.post(
    "/buses",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.BusCreateResponse,
)
def create_bus(
    bus: str = Form(...),
    camera_count: int = Form(..., alias="cameraCount"),
    db: Session = Depends(get_db),
) -> schemas.BusCreateResponse:
    created_bus = crud.create_bus(db=db, bus_number=bus, camera_count=camera_count)
    return schemas.BusCreateResponse(bus=created_bus.bus_number, cameraCount=created_bus.camera_count)


@router.delete("/buses/{bus}", response_model=schemas.BusDeleteResponse)
def delete_bus(bus: str, db: Session = Depends(get_db)) -> schemas.BusDeleteResponse:
    deleted_bus = crud.delete_bus(db=db, bus_number=bus)
    return schemas.BusDeleteResponse(bus=deleted_bus.bus_number)
