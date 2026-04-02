from __future__ import annotations

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
