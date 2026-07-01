from __future__ import annotations

from alembic import op

revision = "20260701_0004"
down_revision = "20260701_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gps_timeline_geom_gix")


def downgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS gps_timeline_geom_gix
        ON gps_timeline USING GIST(geom)
        """
    )
