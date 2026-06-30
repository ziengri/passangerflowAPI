"""
Inspect a legacy SQLite database: show tables, schema, row counts, and sample data.

Usage:
    python scripts/inspect_sqlite.py legacy.db
    python scripts/inspect_sqlite.py legacy.db --table passenger_timeline
    python scripts/inspect_sqlite.py legacy.db --table passenger_timeline --limit 20
    python scripts/inspect_sqlite.py legacy.db --buses
    python scripts/inspect_sqlite.py legacy.db --table passenger_timeline --bus 1234
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _print_separator(char: str = "-", width: int = 72) -> None:
    print(char * width)


def cmd_overview(conn: sqlite3.Connection) -> None:
    tables = _get_tables(conn)
    if not tables:
        print("No tables found.")
        return

    print("\n=== Tables ===")
    for table in tables:
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"  {table:<40} {count:>10} rows")

    for table in tables:
        print(f"\n=== Schema: {table} ===")
        cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        for col in cols:
            pk = " PK" if col["pk"] else ""
            notnull = " NOT NULL" if col["notnull"] else ""
            default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] is not None else ""
            print(f"  {col['cid']:>2}  {col['name']:<30} {col['type']:<15}{pk}{notnull}{default}")

    print()


def cmd_buses(conn: sqlite3.Connection) -> None:
    tables = _get_tables(conn)

    # Try buses table first
    if "buses" in tables:
        print("\n=== buses table ===")
        rows = conn.execute("SELECT * FROM buses ORDER BY bus_number").fetchall()
        if not rows:
            print("  (empty)")
        else:
            headers = rows[0].keys()
            _print_row(headers, headers)
            _print_separator()
            for row in rows:
                _print_row(headers, row)

    # Also show distinct buses in passenger_timeline
    if "passenger_timeline" in tables:
        print("\n=== Buses in passenger_timeline ===")
        rows = conn.execute(
            """
            SELECT bus_number,
                   COUNT(*)            AS rows,
                   MIN(event_date)     AS earliest,
                   MAX(event_date)     AS latest,
                   MAX(camera_number)  AS max_cam
            FROM passenger_timeline
            GROUP BY bus_number
            ORDER BY bus_number
            """
        ).fetchall()
        if not rows:
            print("  (empty)")
        else:
            headers = rows[0].keys()
            _print_row(headers, headers)
            _print_separator()
            for row in rows:
                _print_row(headers, row)
    print()


def _print_row(headers: list[str], row: sqlite3.Row | list) -> None:
    parts = []
    for h in headers:
        val = str(row[h]) if not isinstance(row, list) else str(row[list(headers).index(h)])
        parts.append(f"{val:<20}")
    print("  " + "  ".join(parts))


def cmd_table(conn: sqlite3.Connection, table: str, limit: int, bus: str | None) -> None:
    tables = _get_tables(conn)
    if table not in tables:
        print(f"ERROR: Table '{table}' not found. Available: {', '.join(tables)}", file=sys.stderr)
        sys.exit(1)

    count_sql = f'SELECT COUNT(*) FROM "{table}"'
    params: list = []
    where = ""
    if bus and "bus_number" in [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]:
        where = " WHERE bus_number = ?"
        params.append(bus)

    total = conn.execute(count_sql + where, params).fetchone()[0]
    print(f"\n=== {table} === ({total} rows{f', bus={bus}' if bus else ''})")

    rows = conn.execute(f'SELECT * FROM "{table}"{where} ORDER BY id LIMIT ?', params + [limit]).fetchall()
    if not rows:
        print("  (no rows)")
        return

    headers = list(rows[0].keys())
    # Print header
    print("  " + "  ".join(f"{h:<20}" for h in headers))
    _print_separator()
    for row in rows:
        print("  " + "  ".join(f"{str(row[h]):<20}" for h in headers))

    if total > limit:
        print(f"  ... {total - limit} more rows (use --limit to show more)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect legacy SQLite database.")
    parser.add_argument("sqlite_path", help="Path to the SQLite database file.")
    parser.add_argument("--table", "-t", help="Show data from a specific table.")
    parser.add_argument("--bus", "-b", help="Filter by bus_number (used with --table).")
    parser.add_argument("--buses", action="store_true", help="Show all buses summary.")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max rows to display (default: 10).")
    args = parser.parse_args()

    conn = _connect(Path(args.sqlite_path))
    try:
        if args.buses:
            cmd_buses(conn)
        elif args.table:
            cmd_table(conn, args.table, args.limit, args.bus)
        else:
            cmd_overview(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
