from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth import verify_api_key
from app.db import init_db
from app.errors import AppHTTPError
from app.routes import buses, monitoring, passengers, timeline, trackers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Passenger Flow API",
    version="1.0.0",
    description="API for bus passenger timeline accounting",
    lifespan=lifespan,
)


@app.exception_handler(AppHTTPError)
def handle_app_http_error(_request: Request, exc: AppHTTPError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    messages: list[str] = []
    for error in exc.errors():
        raw_location = error.get("loc", ())
        location = ".".join(str(part) for part in raw_location if part not in {"body"})
        message = error.get("msg", "Validation error")
        messages.append(f"{location}: {message}" if location else message)

    detail = "; ".join(messages) if messages else "Validation error"
    return JSONResponse(status_code=400, content={"detail": detail})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(buses.router, dependencies=[Depends(verify_api_key)])
app.include_router(trackers.router, dependencies=[Depends(verify_api_key)])
app.include_router(timeline.router, dependencies=[Depends(verify_api_key)])
app.include_router(passengers.router, dependencies=[Depends(verify_api_key)])
app.include_router(monitoring.router, dependencies=[Depends(verify_api_key)])
