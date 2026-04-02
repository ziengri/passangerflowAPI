from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
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
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    timeline_entries: Mapped[list["PassengerTimeline"]] = relationship(
        back_populates="bus",
        cascade="all, delete-orphan",
        passive_deletes=True,
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
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    in_count: Mapped[int] = mapped_column(Integer, nullable=False)
    out_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    bus: Mapped[Bus] = relationship(back_populates="timeline_entries")
