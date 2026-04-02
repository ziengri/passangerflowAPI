from __future__ import annotations

from fastapi import APIRouter, Depends, Form, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db
from app.utils.datetime_parser import format_output_datetime, parse_input_datetime

router = APIRouter(prefix="/api/v1", tags=["timeline"])


@router.post(
    "/timeline",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.TimelineCreateResponse,
)
def create_timeline(
    bus: str = Form(...),
    cam: int = Form(...),
    date_value: str = Form(..., alias="date"),
    in_count: int = Form(..., alias="in"),
    out_count: int = Form(..., alias="out"),
    db: Session = Depends(get_db),
) -> schemas.TimelineCreateResponse:
    parsed_date = parse_input_datetime(date_value, field_name="date")

    created_timeline = crud.create_timeline_entry(
        db=db,
        bus_number=bus,
        camera_number=cam,
        event_date=parsed_date,
        in_count=in_count,
        out_count=out_count,
    )

    return schemas.TimelineCreateResponse(
        data=schemas.TimelineDataResponse(
            bus=created_timeline.bus_number,
            cam=created_timeline.camera_number,
            date=format_output_datetime(created_timeline.event_date),
            in_count=created_timeline.in_count,
            out_count=created_timeline.out_count,
        )
    )
