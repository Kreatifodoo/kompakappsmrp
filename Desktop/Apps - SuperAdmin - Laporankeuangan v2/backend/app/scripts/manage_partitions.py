"""Create future monthly partitions for journal_entries / journal_lines.

Run on a schedule (e.g. cron monthly, or Celery beat) to ensure that
partitions exist for any month a tenant might post into. Idempotent —
existing partitions are skipped.

Usage:
    python -m app.scripts.manage_partitions [--months-ahead 12]

Migration 0004 created partitions covering [min_year - 1, max_year + 1]
from the data at upgrade time. As real time advances, this script keeps
the rolling future window populated.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import write_engine

PARTITIONED_TABLES = ("journal_entries", "journal_lines")


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


async def _partition_exists(conn: AsyncConnection, name: str) -> bool:
    row = (
        await conn.execute(
            text("SELECT 1 FROM pg_class WHERE relname = :n LIMIT 1"),
            {"n": name},
        )
    ).first()
    return row is not None


async def _ensure_month_partition(conn: AsyncConnection, table: str, year: int, month: int) -> bool:
    """Create the YYYY-MM partition for `table` if missing. Returns True if created."""
    name = f"{table}_y{year}_m{month:02d}"
    if await _partition_exists(conn, name):
        return False

    start = date(year, month, 1)
    end = _next_month(start)
    await conn.execute(
        text(
            f"CREATE TABLE {name} PARTITION OF {table} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        )
    )
    return True


async def ensure_future_partitions(months_ahead: int = 12) -> dict[str, int]:
    """Ensure partitions exist for every month from `today` through
    `today + months_ahead`. Returns {table: created_count}."""
    created: dict[str, int] = {t: 0 for t in PARTITIONED_TABLES}
    cursor = date.today().replace(day=1)
    horizon = cursor
    for _ in range(months_ahead):
        horizon = _next_month(horizon)

    async with write_engine.begin() as conn:
        d = cursor
        while d <= horizon:
            for table in PARTITIONED_TABLES:
                if await _ensure_month_partition(conn, table, d.year, d.month):
                    created[table] += 1
            d = _next_month(d)
    return created


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--months-ahead",
        type=int,
        default=12,
        help="How many months past today to keep covered (default: 12)",
    )
    args = p.parse_args()
    created = asyncio.run(ensure_future_partitions(args.months_ahead))
    total = sum(created.values())
    if total == 0:
        print("All partitions already exist — nothing to do.")
    else:
        for table, count in created.items():
            if count:
                print(f"  ✓ {table}: created {count} new partition(s)")


if __name__ == "__main__":
    main()
