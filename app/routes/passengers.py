from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db import get_db
from app.errors import BadRequestError
from app.utils.datetime_parser import format_output_datetime, parse_input_datetime

router = APIRouter(prefix="/api/v1", tags=["passengers"])


@router.post("/passengers", response_model=schemas.PassengersResponse)
def get_passengers(
    bus: str = Form(...),
    cam: int = Form(...),
    date_from_value: str = Form(..., alias="dateFrom"),
    date_to_value: str = Form(..., alias="dateTo"),
    db: Session = Depends(get_db),
) -> schemas.PassengersResponse:
    date_from = parse_input_datetime(date_from_value, field_name="dateFrom")
    date_to = parse_input_datetime(date_to_value, field_name="dateTo")

    if date_from > date_to:
        raise BadRequestError("`dateFrom` must be less than or equal to `dateTo`.")

    timeline_entries, sum_in, sum_out = crud.get_passengers_for_period(
        db=db,
        bus_number=bus,
        camera_number=cam,
        date_from=date_from,
        date_to=date_to,
    )

    timeline_payload = [
        schemas.PassengerTimelinePoint(
            date=format_output_datetime(item.event_date),
            in_count=item.in_count,
            out_count=item.out_count,
        )
        for item in timeline_entries
    ]

    return schemas.PassengersResponse(
        timeline=timeline_payload,
        sum=schemas.PassengerSumResponse(in_count=sum_in, out_count=sum_out),
    )
