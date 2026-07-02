from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bus(Base):
    __tablename__ = "buses"
    __table_args__ = (
        CheckConstraint("camera_count > 0", name="ck_buses_camera_count_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bus_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    camera_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    timeline_entries: Mapped[list["PassengerTimeline"]] = relationship(
        back_populates="bus",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    trackers: Mapped[list["BusTracker"]] = relationship(back_populates="bus")


class BusTracker(Base):
    __tablename__ = "bus_trackers"

    device_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    bus_number: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("buses.bus_number", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    meta_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    bus: Mapped[Bus | None] = relationship(back_populates="trackers")


class GPSTimeline(Base):
    __tablename__ = "gps_timeline"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    navigation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bus_trackers.device_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    packet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    navigation_unix_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_unix_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    speed: Mapped[int] = mapped_column(Integer, nullable=False)
    pdop: Mapped[int] = mapped_column(Integer, nullable=False)
    hdop: Mapped[int] = mapped_column(Integer, nullable=False)
    vdop: Mapped[int] = mapped_column(Integer, nullable=False)
    nsat: Mapped[int] = mapped_column(Integer, nullable=False)
    ns: Mapped[int] = mapped_column(Integer, nullable=False)
    course: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class PassengerTimeline(Base):
    __tablename__ = "passenger_timeline"
    __table_args__ = (
        CheckConstraint("camera_number >= 1", name="ck_timeline_camera_number_min"),
        CheckConstraint("in_count >= 0", name="ck_timeline_in_count_non_negative"),
        CheckConstraint("out_count >= 0", name="ck_timeline_out_count_non_negative"),
        Index("ix_passenger_timeline_bus_cam_event", "bus_number", "camera_number", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bus_number: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("buses.bus_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    in_count: Mapped[int] = mapped_column(Integer, nullable=False)
    out_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    bus: Mapped[Bus] = relationship(back_populates="timeline_entries")


class DeviceCurrentStatus(Base):
    __tablename__ = "device_current_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bus_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class DeviceEvent(Base):
    __tablename__ = "device_events"
    __table_args__ = (
        Index("ix_device_events_bus_event_id", "bus_number", "event_id"),
        Index("ix_device_events_bus_occurred_at", "bus_number", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bus_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    component: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    details_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
