from __future__ import annotations

from alembic import op

revision = "20260702_0006"
down_revision = "20260701_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE gps_current_position
        DROP COLUMN IF EXISTS raw_json
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE gps_current_position
        ADD COLUMN IF NOT EXISTS raw_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
