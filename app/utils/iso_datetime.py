from __future__ import annotations

from datetime import datetime

from app.errors import BadRequestError
from app.utils.timezones import UTC


def parse_iso8601_datetime(value: str, field_name: str) -> datetime:
    cleaned = value.strip()
    if not cleaned:
        raise BadRequestError(f"`{field_name}` is required.")

    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BadRequestError(
            f"Invalid `{field_name}` format. Expected ISO 8601 timestamp with timezone."
        ) from exc

    if parsed.tzinfo is None:
        raise BadRequestError(
            f"Invalid `{field_name}` format. Expected ISO 8601 timestamp with timezone."
        )

    return parsed.astimezone(UTC)


def format_iso8601_utc_output(value: datetime) -> str:
    utc_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return utc_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
