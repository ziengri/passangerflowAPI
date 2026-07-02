from __future__ import annotations

from collections.abc import Generator
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
import pytest
from fastapi.testclient import TestClient

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["API_AUTH_KEY"] = "test-api-key"
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://app_user:j0lxEv0sljXa@localhost:5432/app_db_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.main import app
from app.migrations import run_migrations


def _build_admin_url(database_url: str) -> URL:
    return make_url(database_url).set(database="postgres")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@pytest.fixture(scope="session")
def db_engine():
    database_url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(
        _build_admin_url(TEST_DATABASE_URL).render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )

    with admin_engine.connect() as connection:
        connection.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :database_name
                  AND pid <> pg_backend_pid()
                """
            ),
            {"database_name": database_url.database},
        )
        connection.execute(text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_url.database)}"))
        connection.execute(text(f"CREATE DATABASE {_quote_identifier(database_url.database)}"))

    run_migrations(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_url.database},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_url.database)}"))
        admin_engine.dispose()


@pytest.fixture()
def client(db_engine) -> Generator[TestClient, None, None]:
    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    device_current_status,
                    device_events,
                    passenger_timeline,
                    gps_current_position,
                    gps_timeline,
                    bus_trackers,
                    buses
                RESTART IDENTITY CASCADE
                """
            )
        )
    with TestClient(app) as test_client:
        yield test_client
