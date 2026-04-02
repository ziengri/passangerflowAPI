from __future__ import annotations

from datetime import datetime

from app.errors import BadRequestError

INPUT_DATETIME_FORMAT = "%d.%m.%YT%H:%M"
OUTPUT_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def parse_input_datetime(value: str, field_name: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise BadRequestError(f"`{field_name}` is required.")

    try:
        return datetime.strptime(cleaned, INPUT_DATETIME_FORMAT)
    except ValueError as exc:
        raise BadRequestError(
            f"Invalid `{field_name}` format. Expected DD.MM.YYYYTHH:MM."
        ) from exc


def format_output_datetime(value: datetime) -> str:
    return value.strftime(OUTPUT_DATETIME_FORMAT)
