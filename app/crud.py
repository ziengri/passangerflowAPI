from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models import (
    Bus,
    BusTracker,
    DeviceCurrentStatus,
    DeviceEvent,
    GPSCurrentPosition,
    GPSTimeline,
    PassengerTimeline,
)
from app.utils.iso_datetime import format_iso8601_utc_output

DEFAULT_MONITORING_CAMERA_COUNT = 3


def _normalize_bus_number(bus_number: str) -> str:
    normalized = bus_number.strip()
    if not normalized:
        raise BadRequestError("`bus` must be a non-empty string.")
    return normalized


def _validate_non_negative(field_name: str, value: int) -> None:
    if value < 0:
        raise BadRequestError(f"`{field_name}` must be >= 0.")


def _normalize_non_empty_text(field_name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise BadRequestError(f"`{field_name}` must be a non-empty string.")
    return cleaned


def _ensure_camera_exists(bus: Bus, camera_number: int) -> None:
    if camera_number < 1 or camera_number > bus.camera_count:
        raise NotFoundError("Camera not found for this bus.")


def _get_bus_by_number(db: Session, bus_number: str) -> Bus | None:
    statement = select(Bus).where(Bus.bus_number == bus_number)
    return db.scalar(statement)


def _get_tracker_by_device_id(db: Session, device_id: int) -> BusTracker | None:
    statement = select(BusTracker).where(BusTracker.device_id == device_id)
    return db.scalar(statement)


def _get_device_current_status_by_bus(db: Session, bus_number: str) -> DeviceCurrentStatus | None:
    statement = select(DeviceCurrentStatus).where(DeviceCurrentStatus.bus_number == bus_number)
    return db.scalar(statement)


def _extract_camera_id(camera_payload: dict[str, Any]) -> int | None:
    raw_camera_id = camera_payload.get("cameraId")
    if isinstance(raw_camera_id, bool):
        return None
    if isinstance(raw_camera_id, int):
        return raw_camera_id if raw_camera_id > 0 else None
    if isinstance(raw_camera_id, str):
        cleaned = raw_camera_id.strip()
        if cleaned.isdigit():
            camera_id = int(cleaned)
            return camera_id if camera_id > 0 else None
    return None


def get_bus_or_404(db: Session, bus_number: str) -> Bus:
    normalized = _normalize_bus_number(bus_number)
    bus = _get_bus_by_number(db, normalized)
    if bus is None:
        raise NotFoundError("Bus not found.")
    return bus


def get_tracker_or_404(db: Session, device_id: int) -> BusTracker:
    if device_id <= 0:
        raise BadRequestError("`deviceId` must be greater than 0.")
    tracker = _get_tracker_by_device_id(db, device_id)
    if tracker is None:
        raise NotFoundError("Tracker not found.")
    return tracker


def list_buses(db: Session) -> list[Bus]:
    statement = select(Bus).order_by(Bus.bus_number.asc())
    return list(db.scalars(statement))


def list_trackers(db: Session) -> list[BusTracker]:
    statement = select(BusTracker).order_by(BusTracker.device_id.asc())
    return list(db.scalars(statement))


def list_current_positions(db: Session) -> list[tuple[GPSCurrentPosition, str | None]]:
    statement = (
        select(GPSCurrentPosition, BusTracker.bus_number)
        .join(BusTracker, BusTracker.device_id == GPSCurrentPosition.device_id)
        .order_by(GPSCurrentPosition.device_id.asc())
    )
    return [(position, bus_number) for position, bus_number in db.execute(statement).all()]


def bind_tracker_to_bus(db: Session, device_id: int, bus_number: str) -> BusTracker:
    tracker = get_tracker_or_404(db, device_id)
    bus = get_bus_or_404(db, bus_number)
    tracker.bus_number = bus.bus_number
    db.commit()
    db.refresh(tracker)
    return tracker


def unbind_tracker_from_bus(db: Session, device_id: int) -> BusTracker:
    tracker = get_tracker_or_404(db, device_id)
    tracker.bus_number = None
    db.commit()
    db.refresh(tracker)
    return tracker


def get_tracker_timeline_window(db: Session, device_id: int, at: datetime) -> tuple[GPSTimeline, list[GPSTimeline]]:
    get_tracker_or_404(db, device_id)

    # Index-friendly nearest lookup (avoids ORDER BY abs(...) full scan per device).
    before = db.scalar(
        select(GPSTimeline)
        .where(
            GPSTimeline.device_id == device_id,
            GPSTimeline.navigation_time <= at,
        )
        .order_by(GPSTimeline.navigation_time.desc(), GPSTimeline.id.desc())
        .limit(1)
    )
    after = db.scalar(
        select(GPSTimeline)
        .where(
            GPSTimeline.device_id == device_id,
            GPSTimeline.navigation_time >= at,
        )
        .order_by(GPSTimeline.navigation_time.asc(), GPSTimeline.id.asc())
        .limit(1)
    )

    if before is None and after is None:
        raise NotFoundError("GPS timeline not found for this tracker.")
    if before is None:
        nearest = after
    elif after is None:
        nearest = before
    else:
        before_delta = abs((before.navigation_time - at).total_seconds())
        after_delta = abs((after.navigation_time - at).total_seconds())
        if after_delta < before_delta:
            nearest = after
        elif after_delta > before_delta:
            nearest = before
        elif after.id < before.id:
            nearest = after
        else:
            nearest = before

    previous_points = list(
        db.scalars(
            select(GPSTimeline)
            .where(
                GPSTimeline.device_id == device_id,
                or_(
                    GPSTimeline.navigation_time < nearest.navigation_time,
                    and_(
                        GPSTimeline.navigation_time == nearest.navigation_time,
                        GPSTimeline.id < nearest.id,
                    ),
                ),
            )
            .order_by(GPSTimeline.navigation_time.desc(), GPSTimeline.id.desc())
            .limit(2)
        )
    )
    next_points = list(
        db.scalars(
            select(GPSTimeline)
            .where(
                GPSTimeline.device_id == device_id,
                or_(
                    GPSTimeline.navigation_time > nearest.navigation_time,
                    and_(
                        GPSTimeline.navigation_time == nearest.navigation_time,
                        GPSTimeline.id > nearest.id,
                    ),
                ),
            )
            .order_by(GPSTimeline.navigation_time.asc(), GPSTimeline.id.asc())
            .limit(2)
        )
    )

    window_points = list(reversed(previous_points)) + [nearest] + next_points
    return nearest, window_points


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


def infer_monitoring_camera_count(cameras: list[dict[str, Any]]) -> int:
    camera_ids = [_extract_camera_id(camera) for camera in cameras]
    inferred_from_ids = max((camera_id for camera_id in camera_ids if camera_id is not None), default=0)
    return max(DEFAULT_MONITORING_CAMERA_COUNT, len(cameras), inferred_from_ids)


def ensure_bus_exists_for_monitoring(
    db: Session,
    bus_number: str,
    inferred_camera_count: int,
) -> Bus:
    normalized = _normalize_bus_number(bus_number)
    target_camera_count = max(DEFAULT_MONITORING_CAMERA_COUNT, inferred_camera_count)

    bus = _get_bus_by_number(db, normalized)
    if bus is None:
        bus = Bus(bus_number=normalized, camera_count=target_camera_count)
        db.add(bus)
        return bus

    if target_camera_count > bus.camera_count:
        bus.camera_count = target_camera_count

    return bus


def upsert_current_status(
    db: Session,
    bus_number: str,
    reported_at: datetime,
    snapshot: dict[str, Any],
    inferred_camera_count: int,
) -> tuple[DeviceCurrentStatus, bool]:
    normalized = _normalize_bus_number(bus_number)
    ensure_bus_exists_for_monitoring(db, normalized, inferred_camera_count)

    current_status = _get_device_current_status_by_bus(db, normalized)
    applied = True

    if current_status is None:
        current_status = DeviceCurrentStatus(
            bus_number=normalized,
            reported_at=reported_at,
            snapshot_json=snapshot,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(current_status)
    elif reported_at >= current_status.reported_at:
        current_status.reported_at = reported_at
        current_status.snapshot_json = snapshot
        current_status.updated_at = datetime.now(timezone.utc)
    else:
        applied = False

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BadRequestError("Failed to upsert device status.") from exc

    if applied:
        db.refresh(current_status)

    return current_status, applied


def list_device_current_statuses(db: Session) -> list[DeviceCurrentStatus]:
    statement = select(DeviceCurrentStatus).order_by(DeviceCurrentStatus.bus_number.asc())
    return list(db.scalars(statement))


def get_device_current_status_or_404(db: Session, bus_number: str) -> DeviceCurrentStatus:
    normalized = _normalize_bus_number(bus_number)
    current_status = _get_device_current_status_by_bus(db, normalized)
    if current_status is None:
        raise NotFoundError("Device status not found.")
    return current_status


def serialize_device_current_status(current_status: DeviceCurrentStatus) -> dict[str, Any]:
    snapshot = dict(current_status.snapshot_json)
    snapshot["bus"] = current_status.bus_number
    snapshot["reportedAt"] = format_iso8601_utc_output(current_status.reported_at)
    snapshot.setdefault("cameras", [])
    snapshot.setdefault("services", [])
    return snapshot


def insert_events_batch(
    db: Session,
    bus_number: str,
    events: list[dict[str, Any]],
    inferred_camera_count: int = DEFAULT_MONITORING_CAMERA_COUNT,
) -> tuple[int, int]:
    normalized = _normalize_bus_number(bus_number)
    ensure_bus_exists_for_monitoring(db, normalized, inferred_camera_count)

    unique_events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    duplicates = 0

    for event in events:
        event_id = _normalize_non_empty_text("eventId", str(event["event_id"]))
        if event_id in seen_event_ids:
            duplicates += 1
            continue

        seen_event_ids.add(event_id)
        unique_events.append(
            {
                "event_id": event_id,
                "occurred_at": event["occurred_at"],
                "kind": _normalize_non_empty_text("kind", str(event["kind"])),
                "component": _normalize_non_empty_text("component", str(event["component"])),
                "severity": _normalize_non_empty_text("severity", str(event["severity"])),
                "message": _normalize_non_empty_text("message", str(event["message"])),
                "details": event.get("details"),
            }
        )

    existing_event_ids: set[str] = set()
    if unique_events:
        statement = select(DeviceEvent.event_id).where(
            DeviceEvent.bus_number == normalized,
            DeviceEvent.event_id.in_([event["event_id"] for event in unique_events]),
        )
        existing_event_ids = set(db.scalars(statement))

    rows_to_insert = [
        DeviceEvent(
            bus_number=normalized,
            event_id=event["event_id"],
            occurred_at=event["occurred_at"],
            kind=event["kind"],
            component=event["component"],
            severity=event["severity"],
            message=event["message"],
            details_json=event["details"],
        )
        for event in unique_events
        if event["event_id"] not in existing_event_ids
    ]
    duplicates += len(unique_events) - len(rows_to_insert)

    if rows_to_insert:
        db.add_all(rows_to_insert)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BadRequestError("Failed to store device events.") from exc

    return len(rows_to_insert), duplicates


def list_device_events(
    db: Session,
    bus_number: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[DeviceEvent]:
    statement = select(DeviceEvent)

    if bus_number is not None:
        statement = statement.where(DeviceEvent.bus_number == _normalize_bus_number(bus_number))
    if occurred_from is not None:
        statement = statement.where(DeviceEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(DeviceEvent.occurred_at <= occurred_to)
    if kind is not None:
        statement = statement.where(DeviceEvent.kind == _normalize_non_empty_text("kind", kind))

    statement = statement.order_by(DeviceEvent.occurred_at.desc(), DeviceEvent.id.desc()).limit(limit)
    return list(db.scalars(statement))


def serialize_device_event(event: DeviceEvent) -> dict[str, Any]:
    return {
        "bus": event.bus_number,
        "eventId": event.event_id,
        "occurredAt": format_iso8601_utc_output(event.occurred_at),
        "kind": event.kind,
        "component": event.component,
        "severity": event.severity,
        "message": event.message,
        "details": event.details_json,
    }


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
