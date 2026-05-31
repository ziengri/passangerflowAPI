from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.legacy_import import import_sqlite_to_timescaledb

from tests.test_api import AUTH_HEADERS


def _create_legacy_sqlite_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE buses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_number VARCHAR(64) NOT NULL UNIQUE,
                camera_count INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE passenger_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_number VARCHAR(64) NOT NULL,
                camera_number INTEGER NOT NULL,
                event_date DATETIME NOT NULL,
                in_count INTEGER NOT NULL,
                out_count INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE device_current_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_number VARCHAR(64) NOT NULL UNIQUE,
                reported_at DATETIME NOT NULL,
                snapshot_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE device_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_number VARCHAR(64) NOT NULL,
                event_id VARCHAR(128) NOT NULL,
                occurred_at DATETIME NOT NULL,
                kind VARCHAR(128) NOT NULL,
                component VARCHAR(128) NOT NULL,
                severity VARCHAR(32) NOT NULL,
                message VARCHAR(1024) NOT NULL,
                details_json JSON,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX uq_device_events_bus_event_id
                ON device_events (bus_number, event_id);
            """
        )

        connection.execute(
            """
            INSERT INTO buses (bus_number, camera_count, created_at)
            VALUES (?, ?, ?)
            """,
            ("BUS-LEGACY-001", 4, "2026-05-19 10:00:00"),
        )
        connection.execute(
            """
            INSERT INTO passenger_timeline (bus_number, camera_number, event_date, in_count, out_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("BUS-LEGACY-001", 2, "2026-05-19 19:30:00", 4, 2, "2026-05-19 19:31:00"),
        )
        connection.execute(
            """
            INSERT INTO device_current_status (bus_number, reported_at, snapshot_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "BUS-LEGACY-001",
                "2026-05-19 19:30:00",
                json.dumps(
                    {
                        "bus": "BUS-LEGACY-001",
                        "reportedAt": "2026-05-19T19:30:00Z",
                        "cameras": [{"cameraId": 1, "reachable": True}],
                        "services": [{"name": "buspcrt-processor.service", "status": "active"}],
                    }
                ),
                "2026-05-19 19:30:10",
                "2026-05-19 19:30:20",
            ),
        )
        connection.execute(
            """
            INSERT INTO device_events (
                bus_number,
                event_id,
                occurred_at,
                kind,
                component,
                severity,
                message,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "BUS-LEGACY-001",
                "evt-legacy-1",
                "2026-05-19 19:31:00",
                "camera.status_changed",
                "camera-1",
                "warning",
                "Camera 1 is offline",
                json.dumps({"reachable": False}),
                "2026-05-19 19:31:10",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_timescaledb_schema_is_applied(db_engine) -> None:
    with db_engine.connect() as connection:
        hypertables = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    """
                    SELECT hypertable_name, compression_enabled
                    FROM timescaledb_information.hypertables
                    WHERE hypertable_name IN ('passenger_timeline', 'device_events')
                    """
                )
            )
        }
        compression_jobs = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT hypertable_name
                    FROM timescaledb_information.jobs
                    WHERE proc_name = 'policy_compression'
                    """
                )
            )
        }

    assert hypertables == {
        "device_events": True,
        "passenger_timeline": True,
    }
    assert {"device_events", "passenger_timeline"} <= compression_jobs


def test_passenger_timeline_is_stored_in_utc(client, db_engine) -> None:
    create_bus_response = client.post(
        "/api/v1/buses",
        data={"bus": "BUS-TZ-001", "cameraCount": 2},
        headers=AUTH_HEADERS,
    )
    assert create_bus_response.status_code == 201

    create_timeline_response = client.post(
        "/api/v1/timeline",
        data={
            "bus": "BUS-TZ-001",
            "cam": 2,
            "date": "19.05.2026T19:30",
            "in": 7,
            "out": 3,
        },
        headers=AUTH_HEADERS,
    )
    assert create_timeline_response.status_code == 201
    assert create_timeline_response.json()["data"]["date"] == "2026-05-19T19:30:00"

    with db_engine.connect() as connection:
        stored_event_date = connection.execute(
            text(
                """
                SELECT event_date
                FROM passenger_timeline
                WHERE bus_number = :bus_number
                """
            ),
            {"bus_number": "BUS-TZ-001"},
        ).scalar_one()

    assert stored_event_date.isoformat() == "2026-05-19T16:30:00+00:00"


def test_import_legacy_sqlite_migrates_data(client, db_engine, tmp_path: Path) -> None:
    legacy_sqlite_path = tmp_path / "legacy.db"
    _create_legacy_sqlite_fixture(legacy_sqlite_path)

    summary = import_sqlite_to_timescaledb(legacy_sqlite_path)
    assert summary.buses == 1
    assert summary.passenger_timeline == 1
    assert summary.device_current_status == 1
    assert summary.device_events == 1

    buses_response = client.get("/api/v1/buses", headers=AUTH_HEADERS)
    assert buses_response.status_code == 200
    assert buses_response.json() == [{"bus": "BUS-LEGACY-001", "cameras": [1, 2, 3, 4]}]

    passengers_response = client.post(
        "/api/v1/passengers",
        data={
            "bus": "BUS-LEGACY-001",
            "cam": 2,
            "dateFrom": "19.05.2026T19:00",
            "dateTo": "19.05.2026T20:00",
        },
        headers=AUTH_HEADERS,
    )
    assert passengers_response.status_code == 200
    assert passengers_response.json() == {
        "timeline": [{"date": "2026-05-19T19:30:00", "in": 4, "out": 2}],
        "sum": {"in": 4, "out": 2},
    }

    status_response = client.get("/api/v1/device-status/BUS-LEGACY-001", headers=AUTH_HEADERS)
    assert status_response.status_code == 200
    assert status_response.json() == {
        "bus": "BUS-LEGACY-001",
        "reportedAt": "2026-05-19T19:30:00Z",
        "cameras": [{"cameraId": 1, "reachable": True}],
        "services": [{"name": "buspcrt-processor.service", "status": "active"}],
    }

    events_response = client.get(
        "/api/v1/device-events",
        params={"bus": "BUS-LEGACY-001"},
        headers=AUTH_HEADERS,
    )
    assert events_response.status_code == 200
    assert events_response.json() == [
        {
            "bus": "BUS-LEGACY-001",
            "eventId": "evt-legacy-1",
            "occurredAt": "2026-05-19T19:31:00Z",
            "kind": "camera.status_changed",
            "component": "camera-1",
            "severity": "warning",
            "message": "Camera 1 is offline",
            "details": {"reachable": False},
        }
    ]

    with db_engine.connect() as connection:
        stored_event_date = connection.execute(
            text("SELECT event_date FROM passenger_timeline WHERE bus_number = 'BUS-LEGACY-001'")
        ).scalar_one()
        stored_reported_at = connection.execute(
            text("SELECT reported_at FROM device_current_status WHERE bus_number = 'BUS-LEGACY-001'")
        ).scalar_one()

    assert stored_event_date.isoformat() == "2026-05-19T16:30:00+00:00"
    assert stored_reported_at.isoformat() == "2026-05-19T19:30:00+00:00"
