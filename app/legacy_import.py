from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import DATABASE_URL
from app.migrations import run_migrations
from app.models import Bus, DeviceCurrentStatus, DeviceEvent, PassengerTimeline
from app.utils.timezones import BUS_LOCAL_TIMEZONE, UTC


@dataclass(slots=True)
class ImportSummary:
    buses: int
    passenger_timeline: int
    device_current_status: int
    device_events: int


def _parse_sqlite_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _as_utc_from_local(value: Any) -> datetime:
    parsed = _parse_sqlite_datetime(value)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=BUS_LOCAL_TIMEZONE)
    return aware.astimezone(UTC)


def _as_utc_from_legacy_utc(value: Any) -> datetime:
    parsed = _parse_sqlite_datetime(value)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return aware.astimezone(UTC)


def _load_json(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise ValueError(f"Unsupported JSON value: {value!r}")


def _ensure_target_tables_are_empty(db: Session) -> None:
    table_checks = (
        ("buses", select(Bus.id)),
        ("passenger_timeline", select(PassengerTimeline.id)),
        ("device_current_status", select(DeviceCurrentStatus.id)),
        ("device_events", select(DeviceEvent.id)),
    )
    non_empty = [table_name for table_name, statement in table_checks if db.scalar(statement.limit(1)) is not None]
    if non_empty:
        joined = ", ".join(non_empty)
        raise RuntimeError(f"Target database must be empty before import. Non-empty tables: {joined}.")


def import_sqlite_to_timescaledb(
    sqlite_path: str | Path,
    target_database_url: str = DATABASE_URL,
) -> ImportSummary:
    source_path = Path(sqlite_path)
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    run_migrations(target_database_url)

    sqlite_connection = sqlite3.connect(source_path)
    sqlite_connection.row_factory = sqlite3.Row
    target_engine = create_engine(target_database_url, pool_pre_ping=True)
    target_session_local = sessionmaker(
        bind=target_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    try:
        with target_session_local() as db:
            _ensure_target_tables_are_empty(db)

            buses = [
                Bus(
                    bus_number=row["bus_number"],
                    camera_count=row["camera_count"],
                    created_at=_as_utc_from_legacy_utc(row["created_at"]),
                )
                for row in sqlite_connection.execute(
                    "SELECT bus_number, camera_count, created_at FROM buses ORDER BY id"
                )
            ]
            if buses:
                db.add_all(buses)
                db.commit()

            passenger_timeline = [
                PassengerTimeline(
                    bus_number=row["bus_number"],
                    camera_number=row["camera_number"],
                    event_date=_as_utc_from_local(row["event_date"]),
                    in_count=row["in_count"],
                    out_count=row["out_count"],
                    created_at=_as_utc_from_legacy_utc(row["created_at"]),
                )
                for row in sqlite_connection.execute(
                    """
                    SELECT bus_number, camera_number, event_date, in_count, out_count, created_at
                    FROM passenger_timeline
                    ORDER BY id
                    """
                )
            ]
            if passenger_timeline:
                db.add_all(passenger_timeline)
                db.commit()

            device_current_statuses = [
                DeviceCurrentStatus(
                    bus_number=row["bus_number"],
                    reported_at=_as_utc_from_legacy_utc(row["reported_at"]),
                    snapshot_json=_load_json(row["snapshot_json"]) or {},
                    created_at=_as_utc_from_legacy_utc(row["created_at"]),
                    updated_at=_as_utc_from_legacy_utc(row["updated_at"]),
                )
                for row in sqlite_connection.execute(
                    """
                    SELECT bus_number, reported_at, snapshot_json, created_at, updated_at
                    FROM device_current_status
                    ORDER BY id
                    """
                )
            ]
            if device_current_statuses:
                db.add_all(device_current_statuses)
                db.commit()

            device_events = [
                DeviceEvent(
                    bus_number=row["bus_number"],
                    event_id=row["event_id"],
                    occurred_at=_as_utc_from_legacy_utc(row["occurred_at"]),
                    kind=row["kind"],
                    component=row["component"],
                    severity=row["severity"],
                    message=row["message"],
                    details_json=_load_json(row["details_json"]),
                    created_at=_as_utc_from_legacy_utc(row["created_at"]),
                )
                for row in sqlite_connection.execute(
                    """
                    SELECT bus_number, event_id, occurred_at, kind, component, severity, message, details_json, created_at
                    FROM device_events
                    ORDER BY id
                    """
                )
            ]
            if device_events:
                db.add_all(device_events)
                db.commit()

        return ImportSummary(
            buses=len(buses),
            passenger_timeline=len(passenger_timeline),
            device_current_status=len(device_current_statuses),
            device_events=len(device_events),
        )
    finally:
        sqlite_connection.close()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy SQLite data into TimescaleDB.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the legacy SQLite database file.")
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help="Target TimescaleDB/PostgreSQL SQLAlchemy URL.",
    )
    args = parser.parse_args()

    summary = import_sqlite_to_timescaledb(
        sqlite_path=args.sqlite_path,
        target_database_url=args.database_url,
    )
    print(
        "Imported "
        f"buses={summary.buses}, "
        f"passenger_timeline={summary.passenger_timeline}, "
        f"device_current_status={summary.device_current_status}, "
        f"device_events={summary.device_events}"
    )


if __name__ == "__main__":
    main()
