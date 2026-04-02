from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models import Bus, PassengerTimeline


def _normalize_bus_number(bus_number: str) -> str:
    normalized = bus_number.strip()
    if not normalized:
        raise BadRequestError("`bus` must be a non-empty string.")
    return normalized


def _validate_non_negative(field_name: str, value: int) -> None:
    if value < 0:
        raise BadRequestError(f"`{field_name}` must be >= 0.")


def _ensure_camera_exists(bus: Bus, camera_number: int) -> None:
    if camera_number < 1 or camera_number > bus.camera_count:
        raise NotFoundError("Camera not found for this bus.")


def _get_bus_by_number(db: Session, bus_number: str) -> Bus | None:
    statement = select(Bus).where(Bus.bus_number == bus_number)
    return db.scalar(statement)


def get_bus_or_404(db: Session, bus_number: str) -> Bus:
    normalized = _normalize_bus_number(bus_number)
    bus = _get_bus_by_number(db, normalized)
    if bus is None:
        raise NotFoundError("Bus not found.")
    return bus


def list_buses(db: Session) -> list[Bus]:
    statement = select(Bus).order_by(Bus.bus_number.asc())
    return list(db.scalars(statement))


def create_bus(db: Session, bus_number: str, camera_count: int) -> Bus:
    normalized = _normalize_bus_number(bus_number)
    if camera_count <= 0:
        raise BadRequestError("`cameraCount` must be greater than 0.")

    existing = _get_bus_by_number(db, normalized)
    if existing is not None:
        raise ConflictError("Bus already exists.")

    bus = Bus(bus_number=normalized, camera_count=camera_count)
    db.add(bus)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Bus already exists.") from exc

    db.refresh(bus)
    return bus


def delete_bus(db: Session, bus_number: str) -> Bus:
    bus = get_bus_or_404(db, bus_number)
    db.delete(bus)
    db.commit()
    return bus


def create_timeline_entry(
    db: Session,
    bus_number: str,
    camera_number: int,
    event_date: datetime,
    in_count: int,
    out_count: int,
) -> PassengerTimeline:
    normalized = _normalize_bus_number(bus_number)
    _validate_non_negative("in", in_count)
    _validate_non_negative("out", out_count)

    bus = get_bus_or_404(db, normalized)
    _ensure_camera_exists(bus, camera_number)

    timeline_entry = PassengerTimeline(
        bus_number=bus.bus_number,
        camera_number=camera_number,
        event_date=event_date,
        in_count=in_count,
        out_count=out_count,
    )
    db.add(timeline_entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BadRequestError("Failed to create timeline record.") from exc

    db.refresh(timeline_entry)
    return timeline_entry


def get_passengers_for_period(
    db: Session,
    bus_number: str,
    camera_number: int,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[PassengerTimeline], int, int]:
    normalized = _normalize_bus_number(bus_number)
    bus = get_bus_or_404(db, normalized)
    _ensure_camera_exists(bus, camera_number)

    base_filters = (
        PassengerTimeline.bus_number == bus.bus_number,
        PassengerTimeline.camera_number == camera_number,
        PassengerTimeline.event_date >= date_from,
        PassengerTimeline.event_date <= date_to,
    )

    timeline_statement = (
        select(PassengerTimeline)
        .where(*base_filters)
        .order_by(PassengerTimeline.event_date.asc())
    )
    timeline_entries = list(db.scalars(timeline_statement))

    sums_statement = select(
        func.coalesce(func.sum(PassengerTimeline.in_count), 0),
        func.coalesce(func.sum(PassengerTimeline.out_count), 0),
    ).where(*base_filters)
    sum_in, sum_out = db.execute(sums_statement).one()

    return timeline_entries, int(sum_in), int(sum_out)
