from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://app_user:j0lxEv0sljXa@localhost:5432/app_db"


def _resolve_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


DATABASE_URL = _resolve_database_url()

# Defaults sized for account burst traffic. With 2 uvicorn workers keep
# workers * (pool_size + max_overflow) comfortably under Postgres max_connections (100).
engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=_env_int("DB_POOL_SIZE", 15),
    max_overflow=_env_int("DB_MAX_OVERFLOW", 25),
    pool_timeout=_env_int("DB_POOL_TIMEOUT", 10),
    pool_recycle=_env_int("DB_POOL_RECYCLE", 1800),
)


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        # Read-only handlers never commit; rollback releases idle-in-transaction
        # before the connection returns to the pool.
        db.rollback()
        db.close()


def init_db() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
