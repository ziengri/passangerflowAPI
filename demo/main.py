from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from app.utils.datetime_parser import INPUT_DATETIME_FORMAT

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("demo-service")


@dataclass(frozen=True)
class DemoConfig:
    api_url: str
    api_auth_key: str
    bus: str
    cam_mode: str
    cam_values: list[int]
    interval_seconds: int
    bus_camera_count: int
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "DemoConfig":
        api_url = os.getenv("API_URL", "http://api:8000").rstrip("/")
        api_auth_key = os.getenv("API_AUTH_KEY", "local-dev-key")
        bus = os.getenv("DEMO_BUS", "BUS-DEMO").strip() or "BUS-DEMO"

        cam_mode = os.getenv("DEMO_CAM_MODE", "random").strip().lower()
        if cam_mode not in {"fixed", "random"}:
            logger.warning("Invalid DEMO_CAM_MODE=%s. Fallback to random.", cam_mode)
            cam_mode = "random"

        cam_values = _read_camera_list("DEMO_CAM", [1])
        interval_seconds = _read_positive_int("DEMO_INTERVAL_SECONDS", 120)
        bus_camera_count = _read_positive_int("DEMO_BUS_CAMERA_COUNT", 4)
        timeout_seconds = _read_positive_int("DEMO_TIMEOUT_SECONDS", 10)

        return cls(
            api_url=api_url,
            api_auth_key=api_auth_key,
            bus=bus,
            cam_mode=cam_mode,
            cam_values=cam_values,
            interval_seconds=interval_seconds,
            bus_camera_count=bus_camera_count,
            timeout_seconds=timeout_seconds,
        )


def _read_positive_int(env_name: str, default: int) -> int:
    raw = os.getenv(env_name, str(default))
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%s. Fallback to %d.", env_name, raw, default)
        return default

    if value <= 0:
        logger.warning("%s must be > 0. Fallback to %d.", env_name, default)
        return default

    return value


def _read_camera_list(env_name: str, default: list[int]) -> list[int]:
    raw = os.getenv(env_name, ",".join(str(item) for item in default)).strip()
    if not raw:
        return default

    values: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            logger.warning("Invalid %s value token '%s'. It will be ignored.", env_name, token)
            continue
        if value <= 0:
            logger.warning("%s token '%s' must be > 0. It will be ignored.", env_name, token)
            continue
        values.append(value)

    if not values:
        logger.warning("No valid %s values were provided. Fallback to %s.", env_name, default)
        return default

    # Remove duplicates while keeping order.
    unique_values: list[int] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        unique_values.append(value)
        seen.add(value)
    return unique_values


class ApiClient:
    def __init__(self, api_url: str, timeout_seconds: int, api_auth_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"X-AUTH": api_auth_key})

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def get_buses(self) -> list[dict[str, Any]]:
        response = self.session.get(self._url("/api/v1/buses"), timeout=self.timeout_seconds)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to get buses: HTTP {response.status_code}, body={response.text}"
            )

        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected buses response payload format.")
        return payload

    def create_bus(self, bus: str, camera_count: int) -> None:
        response = self.session.post(
            self._url("/api/v1/buses"),
            data={"bus": bus, "cameraCount": camera_count},
            timeout=self.timeout_seconds,
        )
        if response.status_code in {201, 409}:
            return

        raise RuntimeError(
            f"Failed to create bus {bus}: HTTP {response.status_code}, body={response.text}"
        )

    def post_timeline(self, bus: str, cam: int, date_value: str, in_count: int, out_count: int) -> None:
        response = self.session.post(
            self._url("/api/v1/timeline"),
            data={
                "bus": bus,
                "cam": cam,
                "date": date_value,
                "in": in_count,
                "out": out_count,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code != 201:
            raise RuntimeError(
                "Failed to create timeline event: "
                f"HTTP {response.status_code}, body={response.text}"
            )

    def get_bus_camera_count(self, bus: str) -> int | None:
        buses = self.get_buses()
        for item in buses:
            if item.get("bus") == bus:
                cameras = item.get("cameras", [])
                if not isinstance(cameras, list):
                    raise RuntimeError("Unexpected cameras payload format.")
                return len(cameras)
        return None


def ensure_bus_exists(client: ApiClient, bus: str, fallback_camera_count: int) -> int:
    existing_camera_count = client.get_bus_camera_count(bus)
    if existing_camera_count is not None:
        return existing_camera_count

    logger.info(
        "Bus %s not found. Creating it automatically with cameraCount=%d.",
        bus,
        fallback_camera_count,
    )
    client.create_bus(bus, fallback_camera_count)

    camera_count = client.get_bus_camera_count(bus)
    if camera_count is None:
        raise RuntimeError("Bus was not found after creation attempt.")

    return camera_count


def _filter_cameras_for_bus(camera_candidates: list[int], camera_count: int) -> list[int]:
    return [camera for camera in camera_candidates if 1 <= camera <= camera_count]


def pick_camera(cam_mode: str, camera_candidates: list[int], camera_count: int) -> int:
    if camera_count <= 0:
        raise RuntimeError("Invalid camera_count from API: must be > 0.")

    valid_candidates = _filter_cameras_for_bus(camera_candidates, camera_count)

    if cam_mode == "fixed":
        fixed_camera = valid_candidates[0] if valid_candidates else 1
        if valid_candidates:
            return fixed_camera

        logger.warning(
            "DEMO_CAM=%s is out of bus range 1..%d. Fallback to camera 1.",
            camera_candidates,
            camera_count,
        )
        return 1

    if valid_candidates:
        return random.choice(valid_candidates)

    logger.warning(
        "DEMO_CAM=%s has no cameras inside range 1..%d. Using all available cameras randomly.",
        camera_candidates,
        camera_count,
    )
    return random.randint(1, camera_count)


def make_event_date_value(current_time: datetime | None = None) -> str:
    now = current_time or datetime.now()
    return now.strftime(INPUT_DATETIME_FORMAT)


def run_demo_loop(config: DemoConfig, client: ApiClient) -> None:
    logger.info(
        "Demo service started. bus=%s mode=%s cams=%s interval=%ss api=%s",
        config.bus,
        config.cam_mode,
        config.cam_values,
        config.interval_seconds,
        config.api_url,
    )

    while True:
        try:
            camera_count = ensure_bus_exists(client, config.bus, config.bus_camera_count)
            camera = pick_camera(config.cam_mode, config.cam_values, camera_count)

            in_count = random.randint(0, 9)
            out_count = random.randint(0, 9)
            date_value = make_event_date_value()

            client.post_timeline(
                bus=config.bus,
                cam=camera,
                date_value=date_value,
                in_count=in_count,
                out_count=out_count,
            )

            logger.info(
                "Event created: bus=%s cam=%d date=%s in=%d out=%d",
                config.bus,
                camera,
                date_value,
                in_count,
                out_count,
            )
        except Exception:
            logger.exception("Demo iteration failed.")

        time.sleep(config.interval_seconds)


def main() -> None:
    config = DemoConfig.from_env()
    client = ApiClient(
        api_url=config.api_url,
        timeout_seconds=config.timeout_seconds,
        api_auth_key=config.api_auth_key,
    )
    run_demo_loop(config=config, client=client)


if __name__ == "__main__":
    main()
