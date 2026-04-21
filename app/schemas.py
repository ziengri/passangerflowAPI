from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BusItemResponse(BaseModel):
    bus: str
    cameras: list[int]


class BusCreateResponse(BaseModel):
    status: str = "ok"
    bus: str
    cameraCount: int


class BusDeleteResponse(BaseModel):
    status: str = "ok"
    bus: str


class TimelineDataResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bus: str
    cam: int
    date: str
    in_count: int = Field(alias="in")
    out_count: int = Field(alias="out")


class TimelineCreateResponse(BaseModel):
    status: str = "ok"
    data: TimelineDataResponse


class PassengerTimelinePoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    in_count: int = Field(alias="in")
    out_count: int = Field(alias="out")


class PassengerSumResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    in_count: int = Field(alias="in")
    out_count: int = Field(alias="out")


class PassengersResponse(BaseModel):
    timeline: list[PassengerTimelinePoint]
    sum: PassengerSumResponse


class MonitoringBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DeviceStatusSnapshot(MonitoringBaseModel):
    bus: str
    reported_at: str = Field(alias="reportedAt")
    connectivity: dict[str, Any] | None = None
    cameras: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    storage: dict[str, Any] | None = None
    buffers: dict[str, Any] | None = None


class DeviceStatusUpsertResponse(MonitoringBaseModel):
    status: str = "ok"
    bus: str
    reported_at: str = Field(alias="reportedAt")
    applied: bool


class DeviceEventPayload(MonitoringBaseModel):
    event_id: str = Field(alias="eventId")
    occurred_at: str = Field(alias="occurredAt")
    kind: str
    component: str
    severity: str
    message: str
    details: dict[str, Any] | None = None


class DeviceEventsBatchRequest(MonitoringBaseModel):
    bus: str
    events: list[DeviceEventPayload] = Field(default_factory=list)


class DeviceEventsBatchResponse(MonitoringBaseModel):
    status: str = "ok"
    bus: str
    received: int
    inserted: int
    duplicates: int


class DeviceEventResponse(MonitoringBaseModel):
    bus: str
    event_id: str = Field(alias="eventId")
    occurred_at: str = Field(alias="occurredAt")
    kind: str
    component: str
    severity: str
    message: str
    details: dict[str, Any] | None = None
