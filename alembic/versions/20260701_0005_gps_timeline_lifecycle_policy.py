from __future__ import annotations

from alembic import op
from sqlalchemy import exc as sa_exc

revision = "20260701_0005"
down_revision = "20260701_0004"
branch_labels = None
depends_on = None


def _is_apache_license(connection) -> bool:
    license_name = connection.exec_driver_sql(
        "SELECT current_setting('timescaledb.license', true)"
    ).scalar_one_or_none()
    return (license_name or "").strip().lower() == "apache"


def _is_apache_feature_error(error: sa_exc.DBAPIError) -> bool:
    message = str(getattr(error, "orig", error)).lower()
    return "functionality not supported under the current \"apache\" license" in message


def upgrade() -> None:
    connection = op.get_bind()
    context = op.get_context()

    if not _is_apache_license(connection):
        try:
            with connection.begin_nested():
                connection.exec_driver_sql(
                    """
                    ALTER TABLE gps_timeline SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'device_id',
                        timescaledb.compress_orderby = 'navigation_time DESC'
                    )
                    """
                )
                connection.exec_driver_sql(
                    "SELECT add_compression_policy('gps_timeline', INTERVAL '30 days', if_not_exists => TRUE)"
                )
        except sa_exc.DBAPIError as error:
            if not _is_apache_feature_error(error):
                raise
            context.config.print_stdout(
                "Skipping gps_timeline compression policy: unsupported under current TimescaleDB Apache license."
            )
    else:
        context.config.print_stdout(
            "Skipping gps_timeline compression policy: current TimescaleDB license is apache."
        )

    op.execute(
        "SELECT add_retention_policy('gps_timeline', INTERVAL '3 months', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('gps_timeline', if_exists => TRUE)")
    op.execute("SELECT remove_compression_policy('gps_timeline', if_exists => TRUE)")
