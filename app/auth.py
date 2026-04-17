from __future__ import annotations

import os

from fastapi import Header

from app.errors import UnauthorizedError

DEFAULT_API_AUTH_KEY = "local-dev-key"


def get_expected_api_key() -> str:
    return os.getenv("API_AUTH_KEY", DEFAULT_API_AUTH_KEY)


def verify_api_key(x_auth: str | None = Header(default=None, alias="X-AUTH")) -> None:
    expected_key = get_expected_api_key()
    if x_auth != expected_key:
        raise UnauthorizedError("Unauthorized. Invalid or missing X-AUTH header.")
