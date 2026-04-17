from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_missing_auth_header_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/buses")
    assert response.status_code == 401
