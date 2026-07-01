from __future__ import annotations

from alembic import op

revision = "20260701_0005"
down_revision = "20260701_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE gps_timeline SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'device_id',
            timescaledb.compress_orderby = 'navigation_time DESC'
        )
        """
    )
    op.execute(
        "SELECT add_compression_policy('gps_timeline', INTERVAL '30 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('gps_timeline', INTERVAL '3 months', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('gps_timeline', if_exists => TRUE)")
    op.execute("SELECT remove_compression_policy('gps_timeline', if_exists => TRUE)")
