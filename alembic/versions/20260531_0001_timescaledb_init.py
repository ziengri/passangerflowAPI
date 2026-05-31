from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260531_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "buses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bus_number", sa.String(length=64), nullable=False),
        sa.Column("camera_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("camera_count > 0", name="ck_buses_camera_count_positive"),
    )
    op.create_index("ix_buses_bus_number", "buses", ["bus_number"], unique=True)

    op.create_table(
        "device_current_status",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bus_number", sa.String(length=64), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_device_current_status_bus_number",
        "device_current_status",
        ["bus_number"],
        unique=True,
    )

    op.create_table(
        "passenger_timeline",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("bus_number", sa.String(length=64), nullable=False),
        sa.Column("camera_number", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("in_count", sa.Integer(), nullable=False),
        sa.Column("out_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("camera_number >= 1", name="ck_timeline_camera_number_min"),
        sa.CheckConstraint("in_count >= 0", name="ck_timeline_in_count_non_negative"),
        sa.CheckConstraint("out_count >= 0", name="ck_timeline_out_count_non_negative"),
        sa.ForeignKeyConstraint(["bus_number"], ["buses.bus_number"], ondelete="CASCADE"),
    )
    op.create_index("ix_passenger_timeline_bus_number", "passenger_timeline", ["bus_number"])
    op.create_index(
        "ix_passenger_timeline_bus_cam_event",
        "passenger_timeline",
        ["bus_number", "camera_number", "event_date"],
    )

    op.create_table(
        "device_events",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("bus_number", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=128), nullable=False),
        sa.Column("component", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_device_events_bus_number", "device_events", ["bus_number"])
    op.create_index("ix_device_events_bus_event_id", "device_events", ["bus_number", "event_id"])
    op.create_index(
        "ix_device_events_bus_occurred_at",
        "device_events",
        ["bus_number", "occurred_at"],
    )

    op.execute(
        """
        SELECT create_hypertable(
            'passenger_timeline',
            by_range('event_date', INTERVAL '1 day'),
            if_not_exists => TRUE,
            migrate_data => TRUE
        )
        """
    )
    op.execute(
        """
        ALTER TABLE passenger_timeline SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'bus_number,camera_number',
            timescaledb.compress_orderby = 'event_date DESC'
        )
        """
    )
    op.execute(
        "SELECT add_compression_policy('passenger_timeline', INTERVAL '30 days', if_not_exists => TRUE)"
    )

    op.execute(
        """
        SELECT create_hypertable(
            'device_events',
            by_range('occurred_at', INTERVAL '1 day'),
            if_not_exists => TRUE,
            migrate_data => TRUE
        )
        """
    )
    op.execute(
        """
        ALTER TABLE device_events SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'bus_number',
            timescaledb.compress_orderby = 'occurred_at DESC'
        )
        """
    )
    op.execute(
        "SELECT add_compression_policy('device_events', INTERVAL '30 days', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    op.execute("SELECT remove_compression_policy('device_events', if_exists => TRUE)")
    op.execute("SELECT remove_compression_policy('passenger_timeline', if_exists => TRUE)")
    op.drop_index("ix_device_events_bus_occurred_at", table_name="device_events")
    op.drop_index("ix_device_events_bus_event_id", table_name="device_events")
    op.drop_index("ix_device_events_bus_number", table_name="device_events")
    op.drop_table("device_events")
    op.drop_index("ix_passenger_timeline_bus_cam_event", table_name="passenger_timeline")
    op.drop_index("ix_passenger_timeline_bus_number", table_name="passenger_timeline")
    op.drop_table("passenger_timeline")
    op.drop_index("ix_device_current_status_bus_number", table_name="device_current_status")
    op.drop_table("device_current_status")
    op.drop_index("ix_buses_bus_number", table_name="buses")
    op.drop_table("buses")
