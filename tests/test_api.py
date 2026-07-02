from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

AUTH_HEADERS = {"X-AUTH": "test-api-key"}


def create_bus(client: TestClient, bus: str, camera_count: int):
    return client.post(
        "/api/v1/buses",
        data={"bus": bus, "cameraCount": camera_count},
        headers=AUTH_HEADERS,
    )


def create_timeline(
    client: TestClient,
    bus: str,
    cam: int,
    date: str,
    in_count: int,
    out_count: int,
):
    return client.post(
        "/api/v1/timeline",
        data={
            "bus": bus,
            "cam": cam,
            "date": date,
            "in": in_count,
            "out": out_count,
        },
        headers=AUTH_HEADERS,
    )


def post_device_status(client: TestClient, payload: dict):
    return client.post(
        "/api/v1/device-status",
        json=payload,
        headers=AUTH_HEADERS,
    )


def post_device_events(client: TestClient, payload: dict):
    return client.post(
        "/api/v1/device-events/batch",
        json=payload,
        headers=AUTH_HEADERS,
    )


def build_device_status_payload(bus: str, reported_at: str, camera_count: int) -> dict:
    return {
        "bus": bus,
        "reportedAt": reported_at,
        "connectivity": {
            "apiReachable": True,
            "apiLastOnlineAt": reported_at,
        },
        "cameras": [
            {
                "cameraId": camera_number,
                "ip": f"192.168.0.{camera_number + 2}",
                "reachable": True,
            }
            for camera_number in range(1, camera_count + 1)
        ],
        "services": [
            {
                "name": "buspcrt-processor.service",
                "status": "active",
            },
            {
                "name": "buspcrt-door-gateway.service",
                "status": "active",
            },
        ],
        "storage": {
            "sessionsDirBytes": 2048,
            "freeBytes": 4096,
        },
        "buffers": {
            "monitorPendingEvents": 1,
            "monitorPendingStatus": 0,
            "timelinePendingRecords": 2,
        },
    }


def build_device_event_payload(
    event_id: str,
    occurred_at: str,
    kind: str,
    component: str,
    severity: str,
    message: str,
    details: dict | None = None,
) -> dict:
    return {
        "eventId": event_id,
        "occurredAt": occurred_at,
        "kind": kind,
        "component": component,
        "severity": severity,
        "message": message,
        "details": details,
    }


def create_tracker(db_engine: Engine, device_id: int, bus: str | None = None) -> None:
    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO bus_trackers (
                    device_id,
                    bus_number,
                    first_seen_at,
                    last_seen_at,
                    meta_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :device_id,
                    :bus_number,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    '{}'::jsonb,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {"device_id": device_id, "bus_number": bus},
        )


def test_create_bus_and_list_buses(client: TestClient) -> None:
    create_response = create_bus(client, "BUS-001", 4)
    assert create_response.status_code == 201
    assert create_response.json() == {
        "status": "ok",
        "bus": "BUS-001",
        "cameraCount": 4,
    }

    list_response = client.get("/api/v1/buses", headers=AUTH_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json() == [{"bus": "BUS-001", "cameras": [1, 2, 3, 4]}]


def test_create_duplicate_bus_returns_409(client: TestClient) -> None:
    first = create_bus(client, "BUS-001", 2)
    assert first.status_code == 201

    duplicate = create_bus(client, "BUS-001", 2)
    assert duplicate.status_code == 409


def test_list_trackers_and_bind_unbind_tracker(client: TestClient, db_engine: Engine) -> None:
    assert create_bus(client, "BUS-001", 4).status_code == 201
    assert create_bus(client, "BUS-002", 3).status_code == 201
    create_tracker(db_engine, 1001)
    create_tracker(db_engine, 1002, bus="BUS-002")

    list_response = client.get("/api/v1/trackers", headers=AUTH_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json() == [
        {"deviceId": 1001, "bus": None},
        {"deviceId": 1002, "bus": "BUS-002"},
    ]

    bind_response = client.put(
        "/api/v1/trackers/1001/bus",
        data={"bus": "BUS-001"},
        headers=AUTH_HEADERS,
    )
    assert bind_response.status_code == 200
    assert bind_response.json() == {
        "status": "ok",
        "deviceId": 1001,
        "bus": "BUS-001",
    }

    unbind_response = client.delete("/api/v1/trackers/1002/bus", headers=AUTH_HEADERS)
    assert unbind_response.status_code == 200
    assert unbind_response.json() == {
        "status": "ok",
        "deviceId": 1002,
        "bus": None,
    }

    final_list_response = client.get("/api/v1/trackers", headers=AUTH_HEADERS)
    assert final_list_response.status_code == 200
    assert final_list_response.json() == [
        {"deviceId": 1001, "bus": "BUS-001"},
        {"deviceId": 1002, "bus": None},
    ]


def test_bind_tracker_validates_bus_and_tracker(client: TestClient, db_engine: Engine) -> None:
    assert create_bus(client, "BUS-001", 4).status_code == 201
    create_tracker(db_engine, 1001)

    missing_tracker_response = client.put(
        "/api/v1/trackers/9999/bus",
        data={"bus": "BUS-001"},
        headers=AUTH_HEADERS,
    )
    assert missing_tracker_response.status_code == 404

    missing_bus_response = client.put(
        "/api/v1/trackers/1001/bus",
        data={"bus": "BUS-404"},
        headers=AUTH_HEADERS,
    )
    assert missing_bus_response.status_code == 404

    invalid_device_id_response = client.delete("/api/v1/trackers/0/bus", headers=AUTH_HEADERS)
    assert invalid_device_id_response.status_code == 400


def test_create_timeline_validations_and_errors(client: TestClient) -> None:
    assert create_bus(client, "BUS-001", 2).status_code == 201

    valid = create_timeline(client, "BUS-001", 1, "19.05.2026T19:30", 4, 2)
    assert valid.status_code == 201
    assert valid.json() == {
        "status": "ok",
        "data": {
            "bus": "BUS-001",
            "cam": 1,
            "date": "2026-05-19T19:30:00",
            "in": 4,
            "out": 2,
        },
    }

    missing_bus = create_timeline(client, "BUS-404", 1, "19.05.2026T19:30", 1, 1)
    assert missing_bus.status_code == 404

    missing_cam = create_timeline(client, "BUS-001", 3, "19.05.2026T19:30", 1, 1)
    assert missing_cam.status_code == 404

    invalid_date = create_timeline(client, "BUS-001", 1, "2026-05-19T19:30", 1, 1)
    assert invalid_date.status_code == 400

    negative_in = create_timeline(client, "BUS-001", 1, "19.05.2026T19:30", -1, 1)
    assert negative_in.status_code == 400


def test_passengers_period_response_and_sum(client: TestClient) -> None:
    assert create_bus(client, "BUS-001", 2).status_code == 201

    assert create_timeline(client, "BUS-001", 2, "19.05.2026T19:32", 3, 1).status_code == 201
    assert create_timeline(client, "BUS-001", 2, "19.05.2026T19:30", 0, 0).status_code == 201
    assert create_timeline(client, "BUS-001", 2, "19.05.2026T19:40", 5, 2).status_code == 201

    response = client.post(
        "/api/v1/passengers",
        data={
            "bus": "BUS-001",
            "cam": 2,
            "dateFrom": "19.05.2026T19:30",
            "dateTo": "19.05.2026T19:32",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "timeline": [
            {"date": "2026-05-19T19:30:00", "in": 0, "out": 0},
            {"date": "2026-05-19T19:32:00", "in": 3, "out": 1},
        ],
        "sum": {"in": 3, "out": 1},
    }

    invalid_period = client.post(
        "/api/v1/passengers",
        data={
            "bus": "BUS-001",
            "cam": 2,
            "dateFrom": "19.05.2026T19:32",
            "dateTo": "19.05.2026T19:30",
        },
        headers=AUTH_HEADERS,
    )
    assert invalid_period.status_code == 400


def test_delete_bus_cascades_timeline(client: TestClient) -> None:
    assert create_bus(client, "BUS-001", 1).status_code == 201
    assert create_timeline(client, "BUS-001", 1, "19.05.2026T19:30", 4, 2).status_code == 201

    delete_response = client.delete("/api/v1/buses/BUS-001", headers=AUTH_HEADERS)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "ok", "bus": "BUS-001"}

    list_response = client.get("/api/v1/buses", headers=AUTH_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json() == []

    passengers_after_delete = client.post(
        "/api/v1/passengers",
        data={
            "bus": "BUS-001",
            "cam": 1,
            "dateFrom": "19.05.2026T19:00",
            "dateTo": "19.05.2026T20:00",
        },
        headers=AUTH_HEADERS,
    )
    assert passengers_after_delete.status_code == 404


def test_device_status_upsert_autocreates_bus_and_rejects_stale_snapshot(client: TestClient) -> None:
    latest_payload = build_device_status_payload(
        "BUS-MON-001",
        "2026-05-19T22:30:00+03:00",
        camera_count=4,
    )

    create_response = post_device_status(client, latest_payload)
    assert create_response.status_code == 200
    assert create_response.json() == {
        "status": "ok",
        "bus": "BUS-MON-001",
        "reportedAt": "2026-05-19T19:30:00Z",
        "applied": True,
    }

    stale_payload = build_device_status_payload(
        "BUS-MON-001",
        "2026-05-19T19:29:00Z",
        camera_count=2,
    )
    stale_response = post_device_status(client, stale_payload)
    assert stale_response.status_code == 200
    assert stale_response.json() == {
        "status": "ok",
        "bus": "BUS-MON-001",
        "reportedAt": "2026-05-19T19:29:00Z",
        "applied": False,
    }

    current_status_response = client.get("/api/v1/device-status/BUS-MON-001", headers=AUTH_HEADERS)
    assert current_status_response.status_code == 200
    expected_snapshot = dict(latest_payload)
    expected_snapshot["reportedAt"] = "2026-05-19T19:30:00Z"
    assert current_status_response.json() == expected_snapshot

    list_status_response = client.get("/api/v1/device-status", headers=AUTH_HEADERS)
    assert list_status_response.status_code == 200
    assert list_status_response.json() == [expected_snapshot]

    list_buses_response = client.get("/api/v1/buses", headers=AUTH_HEADERS)
    assert list_buses_response.status_code == 200
    assert list_buses_response.json() == [{"bus": "BUS-MON-001", "cameras": [1, 2, 3, 4]}]

    missing_status_response = client.get("/api/v1/device-status/BUS-404", headers=AUTH_HEADERS)
    assert missing_status_response.status_code == 404


def test_device_events_batch_deduplicates_and_filters(client: TestClient) -> None:
    empty_batch_response = post_device_events(client, {"bus": "BUS-MON-EMPTY", "events": []})
    assert empty_batch_response.status_code == 200
    assert empty_batch_response.json() == {
        "status": "ok",
        "bus": "BUS-MON-EMPTY",
        "received": 0,
        "inserted": 0,
        "duplicates": 0,
    }

    events_response = post_device_events(
        client,
        {
            "bus": "BUS-MON-001",
            "events": [
                build_device_event_payload(
                    "evt-1",
                    "2026-05-19T19:30:00Z",
                    "camera.status_changed",
                    "camera-1",
                    "warning",
                    "Camera 1 is offline",
                    {"reachable": False},
                ),
                build_device_event_payload(
                    "evt-1",
                    "2026-05-19T19:31:00Z",
                    "camera.status_changed",
                    "camera-1",
                    "warning",
                    "Camera 1 is still offline",
                    {"reachable": False},
                ),
                build_device_event_payload(
                    "evt-2",
                    "2026-05-19T22:32:00+03:00",
                    "service.status_changed",
                    "buspcrt-processor.service",
                    "critical",
                    "Processor stopped",
                    {"status": "failed"},
                ),
            ],
        },
    )
    assert events_response.status_code == 200
    assert events_response.json() == {
        "status": "ok",
        "bus": "BUS-MON-001",
        "received": 3,
        "inserted": 2,
        "duplicates": 1,
    }

    second_bus_response = post_device_events(
        client,
        {
            "bus": "BUS-MON-002",
            "events": [
                build_device_event_payload(
                    "evt-1",
                    "2026-05-19T19:34:00Z",
                    "camera.status_changed",
                    "camera-2",
                    "warning",
                    "Camera 2 is offline",
                    {"reachable": False},
                )
            ],
        },
    )
    assert second_bus_response.status_code == 200
    assert second_bus_response.json() == {
        "status": "ok",
        "bus": "BUS-MON-002",
        "received": 1,
        "inserted": 1,
        "duplicates": 0,
    }

    filtered_events_response = client.get(
        "/api/v1/device-events",
        params={
            "bus": "BUS-MON-001",
            "kind": "camera.status_changed",
            "from": "2026-05-19T19:00:00Z",
            "to": "2026-05-19T20:00:00Z",
            "limit": 10,
        },
        headers=AUTH_HEADERS,
    )
    assert filtered_events_response.status_code == 200
    assert filtered_events_response.json() == [
        {
            "bus": "BUS-MON-001",
            "eventId": "evt-1",
            "occurredAt": "2026-05-19T19:30:00Z",
            "kind": "camera.status_changed",
            "component": "camera-1",
            "severity": "warning",
            "message": "Camera 1 is offline",
            "details": {"reachable": False},
        }
    ]

    latest_event_response = client.get(
        "/api/v1/device-events",
        params={"limit": 1},
        headers=AUTH_HEADERS,
    )
    assert latest_event_response.status_code == 200
    assert latest_event_response.json() == [
        {
            "bus": "BUS-MON-002",
            "eventId": "evt-1",
            "occurredAt": "2026-05-19T19:34:00Z",
            "kind": "camera.status_changed",
            "component": "camera-2",
            "severity": "warning",
            "message": "Camera 2 is offline",
            "details": {"reachable": False},
        }
    ]

    invalid_period_response = client.get(
        "/api/v1/device-events",
        params={
            "from": "2026-05-19T20:00:00Z",
            "to": "2026-05-19T19:00:00Z",
        },
        headers=AUTH_HEADERS,
    )
    assert invalid_period_response.status_code == 400

    list_buses_response = client.get("/api/v1/buses", headers=AUTH_HEADERS)
    assert list_buses_response.status_code == 200
    assert list_buses_response.json() == [
        {"bus": "BUS-MON-001", "cameras": [1, 2, 3]},
        {"bus": "BUS-MON-002", "cameras": [1, 2, 3]},
        {"bus": "BUS-MON-EMPTY", "cameras": [1, 2, 3]},
    ]


def test_missing_auth_header_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/buses")
    assert response.status_code == 401


def test_dev_mode_skips_auth_check(client: TestClient) -> None:
    previous_value = os.environ.get("API_DEV_MODE")
    os.environ["API_DEV_MODE"] = "true"

    try:
        response = client.get("/api/v1/buses")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        if previous_value is None:
            os.environ.pop("API_DEV_MODE", None)
        else:
            os.environ["API_DEV_MODE"] = previous_value
