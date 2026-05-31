from __future__ import annotations

from datetime import datetime

from app.errors import BadRequestError
from app.utils.timezones import BUS_LOCAL_TIMEZONE, UTC

INPUT_DATETIME_FORMAT = "%d.%m.%YT%H:%M"
OUTPUT_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def parse_input_datetime(value: str, field_name: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise BadRequestError(f"`{field_name}` is required.")

    try:
        parsed = datetime.strptime(cleaned, INPUT_DATETIME_FORMAT)
    except ValueError as exc:
        raise BadRequestError(
            f"Invalid `{field_name}` format. Expected DD.MM.YYYYTHH:MM."
        ) from exc

    return parsed.replace(tzinfo=BUS_LOCAL_TIMEZONE).astimezone(UTC)


def format_output_datetime(value: datetime) -> str:
    utc_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return utc_value.astimezone(BUS_LOCAL_TIMEZONE).strftime(OUTPUT_DATETIME_FORMAT)
