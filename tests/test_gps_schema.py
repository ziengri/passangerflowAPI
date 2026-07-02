from __future__ import annotations

from sqlalchemy import text


def test_gps_tables_and_hypertable_are_created(db_engine) -> None:
    with db_engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename IN ('bus_trackers', 'gps_timeline', 'gps_current_position')
                    """
                )
            )
        }
        hypertables = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    """
                    SELECT hypertable_name, compression_enabled
                    FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'gps_timeline'
                    """
                )
            )
        }
        jobs = {
            (row[0], row[1])
            for row in connection.execute(
                text(
                    """
                    SELECT proc_name, hypertable_name
                    FROM timescaledb_information.jobs
                    WHERE hypertable_name = 'gps_timeline'
                      AND proc_name IN ('policy_compression', 'policy_retention')
                    """
                )
            )
        }
        geom_columns = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT f_table_name
                    FROM geometry_columns
                    WHERE f_table_name IN ('gps_timeline', 'gps_current_position')
                    """
                )
            )
        }
        columns = {
            (row[0], row[1])
            for row in connection.execute(
                text(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name IN ('gps_timeline', 'gps_current_position')
                    """
                )
            )
        }

    assert tables == {"bus_trackers", "gps_timeline", "gps_current_position"}
    assert hypertables == {"gps_timeline": True}
    assert ("policy_compression", "gps_timeline") in jobs
    assert ("policy_retention", "gps_timeline") in jobs
    assert geom_columns == {"gps_timeline", "gps_current_position"}
    assert ("gps_current_position", "raw_json") not in columns


def test_gps_foreign_keys_and_indexes_exist(db_engine) -> None:
    with db_engine.connect() as connection:
        constraints = {
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    """
                    SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE connamespace = 'public'::regnamespace
                      AND conrelid::regclass::text IN ('bus_trackers', 'gps_timeline', 'gps_current_position')
                    """
                )
            )
        }
        indexes = {
            (row[0], row[1])
            for row in connection.execute(
                text(
                    """
                    SELECT tablename, indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename IN ('bus_trackers', 'gps_timeline', 'gps_current_position')
                    """
                )
            )
        }

    assert ("bus_trackers", "bus_trackers_pkey", "PRIMARY KEY (device_id)") in constraints
    assert any(
        table == "bus_trackers" and "FOREIGN KEY (bus_number) REFERENCES buses(bus_number) ON UPDATE CASCADE ON DELETE SET NULL" in definition
        for table, _name, definition in constraints
    )
    assert ("bus_trackers", "bus_trackers_bus_number_idx") in indexes
    assert ("gps_timeline", "gps_timeline_device_time_idx") in indexes
    assert ("gps_current_position", "gps_current_position_geom_gix") in indexes
