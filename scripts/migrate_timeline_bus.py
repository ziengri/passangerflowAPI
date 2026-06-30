"""
Migrate passenger_timeline data for a specific bus from legacy SQLite to TimescaleDB.

Adds only rows that are not yet present in the target (deduplicates by
bus_number + camera_number + event_date). Safe to run multiple times.

Usage:
    uv run python scripts/migrate_timeline_bus.py --sqlite-path legacy.db --bus "rks332"
    uv run python scripts/migrate_timeline_bus.py --sqlite-path legacy.db --bus "rks332" --dry-run
    uv run python scripts/migrate_timeline_bus.py --sqlite-path legacy.db --bus "rks332" --database-url postgresql+psycopg://user:pass@host/db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import DATABASE_URL
from app.models import Bus, PassengerTimeline
from app.utils.timezones import BUS_LOCAL_TIMEZONE, UTC


# ---------------------------------------------------------------------------
# Datetime helpers (same logic as legacy_import.py)
# ---------------------------------------------------------------------------

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
    """Treat naive datetime as Moscow TZ, convert to UTC."""
    parsed = _parse_sqlite_datetime(value)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=BUS_LOCAL_TIMEZONE)
    return aware.astimezone(UTC)


def _as_utc_from_legacy_utc(value: Any) -> datetime:
    """Treat naive datetime as UTC."""
    parsed = _parse_sqlite_datetime(value)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return aware.astimezone(UTC)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _sqlite_connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        print(f"ERROR: SQLite file not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_get_bus(conn: sqlite3.Connection, bus_number: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM buses WHERE bus_number = ?", (bus_number,)
    ).fetchone()


def _sqlite_get_timeline_rows(conn: sqlite3.Connection, bus_number: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT bus_number, camera_number, event_date, in_count, out_count, created_at
        FROM passenger_timeline
        WHERE bus_number = ?
        ORDER BY event_date, camera_number
        """,
        (bus_number,),
    ).fetchall()


def _sqlite_infer_camera_count(conn: sqlite3.Connection, bus_number: str) -> int:
    row = conn.execute(
        "SELECT MAX(camera_number) AS max_cam FROM passenger_timeline WHERE bus_number = ?",
        (bus_number,),
    ).fetchone()
    return int(row["max_cam"]) if row and row["max_cam"] is not None else 1


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@dataclass
class MigrationResult:
    bus_number: str
    bus_created: bool
    source_rows: int
    skipped_duplicates: int
    rows_imported: int


def migrate_bus_timeline(
    sqlite_path: Path,
    bus_number: str,
    target_database_url: str,
    dry_run: bool,
) -> MigrationResult:
    sqlite_conn = _sqlite_connect(sqlite_path)
    try:
        # --- Read from SQLite ---
        sqlite_bus_row = _sqlite_get_bus(sqlite_conn, bus_number)
        timeline_rows = _sqlite_get_timeline_rows(sqlite_conn, bus_number)

        if not timeline_rows:
            print(f"No passenger_timeline rows found for bus '{bus_number}' in SQLite.")
            sys.exit(0)

        if sqlite_bus_row is not None:
            camera_count = int(sqlite_bus_row["camera_count"])
        else:
            camera_count = _sqlite_infer_camera_count(sqlite_conn, bus_number)
            print(
                f"Bus '{bus_number}' not found in SQLite buses table. "
                f"Inferred camera_count={camera_count} from timeline data."
            )

        print(f"Source (SQLite): {len(timeline_rows)} rows for bus '{bus_number}' "
              f"(camera_count={camera_count}).")

        # Convert all source event_dates to UTC upfront for dedup comparison
        source: list[tuple[datetime, int, sqlite3.Row]] = [
            (_as_utc_from_local(row["event_date"]), row["camera_number"], row)
            for row in timeline_rows
        ]

        if dry_run:
            print("[DRY RUN] No changes will be made.")
            _print_sample(timeline_rows)
            return MigrationResult(
                bus_number=bus_number,
                bus_created=False,
                source_rows=len(timeline_rows),
                skipped_duplicates=0,
                rows_imported=0,
            )

        # --- Connect to target DB ---
        engine = create_engine(target_database_url, pool_pre_ping=True)
        Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

        try:
            with Session_() as db:
                # Check if bus exists in target
                existing_bus = db.scalar(select(Bus).where(Bus.bus_number == bus_number))
                bus_created = existing_bus is None

                # Load existing (camera_number, event_date) pairs from target for this bus
                existing_rows = db.execute(
                    text(
                        "SELECT camera_number, event_date "
                        "FROM passenger_timeline WHERE bus_number = :b"
                    ),
                    {"b": bus_number},
                ).fetchall()

                existing_keys: set[tuple[int, datetime]] = {
                    (r.camera_number, r.event_date.astimezone(UTC))
                    for r in existing_rows
                }

                print(f"Target (PostgreSQL): {len(existing_keys)} existing rows for bus '{bus_number}'.")

                # Filter out duplicates
                new_entries: list[PassengerTimeline] = []
                skipped = 0
                for event_date_utc, camera_number, row in source:
                    if (camera_number, event_date_utc) in existing_keys:
                        skipped += 1
                        continue
                    new_entries.append(
                        PassengerTimeline(
                            bus_number=row["bus_number"],
                            camera_number=camera_number,
                            event_date=event_date_utc,
                            in_count=row["in_count"],
                            out_count=row["out_count"],
                            created_at=_as_utc_from_legacy_utc(row["created_at"]),
                        )
                    )

                print(f"Duplicates skipped: {skipped}. New rows to insert: {len(new_entries)}.")

                if not new_entries:
                    print("Nothing to import.")
                    return MigrationResult(
                        bus_number=bus_number,
                        bus_created=False,
                        source_rows=len(timeline_rows),
                        skipped_duplicates=skipped,
                        rows_imported=0,
                    )

                # Ensure bus exists in target
                if bus_created:
                    db.add(Bus(bus_number=bus_number, camera_count=camera_count))
                    db.commit()
                    print(f"Created bus '{bus_number}' with camera_count={camera_count}.")

                db.add_all(new_entries)
                db.commit()
                print(f"Imported {len(new_entries)} rows.")

                return MigrationResult(
                    bus_number=bus_number,
                    bus_created=bus_created,
                    source_rows=len(timeline_rows),
                    skipped_duplicates=skipped,
                    rows_imported=len(new_entries),
                )
        finally:
            engine.dispose()
    finally:
        sqlite_conn.close()


def _print_sample(rows: list[sqlite3.Row], n: int = 5) -> None:
    print(f"\nSample rows (first {min(n, len(rows))}):")
    headers = ["bus_number", "camera_number", "event_date", "in_count", "out_count"]
    print("  " + "  ".join(f"{h:<20}" for h in headers))
    print("  " + "-" * 72)
    for row in rows[:n]:
        print("  " + "  ".join(f"{str(row[h]):<20}" for h in headers))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate passenger_timeline for a specific bus from SQLite to TimescaleDB."
    )
    parser.add_argument("--sqlite-path", required=True, help="Path to the legacy SQLite file.")
    parser.add_argument("--bus", required=True, help="Bus number to migrate.")
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help="Target PostgreSQL SQLAlchemy URL (default: from env DATABASE_URL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without making any changes.",
    )
    args = parser.parse_args()

    result = migrate_bus_timeline(
        sqlite_path=Path(args.sqlite_path),
        bus_number=args.bus,
        target_database_url=args.database_url,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print(
            f"\nDone: bus_created={result.bus_created}, "
            f"source={result.source_rows}, "
            f"skipped={result.skipped_duplicates}, "
            f"imported={result.rows_imported}"
        )


if __name__ == "__main__":
    main()
