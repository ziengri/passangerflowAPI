from __future__ import annotations

from datetime import datetime, timezone

from app.errors import BadRequestError


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

    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def format_iso8601_utc_output(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
