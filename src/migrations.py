"""
Simple database migration system.

Tracks applied migrations via a `schema_version` table and applies
pending SQL statements in order.  Each migration is a (version, sql)
tuple.  Migrations are idempotent — re-running is safe because
applied versions are recorded and skipped.

Usage:
    from src.migrations import run_migrations
    run_migrations(db)          # db = DatabaseManager instance
"""

import logging

logger = logging.getLogger(__name__)

from src.time_utils import vn_iso

# ──────────────────────────────────────────────────────────────
# Migration registry — append new migrations at the bottom.
# Version format: "NNN" (zero-padded, monotonically increasing).
# ──────────────────────────────────────────────────────────────
MIGRATIONS: list[tuple[str, str]] = [
    # 001: future schema changes go here
    # ("001", "ALTER TABLE companies ADD COLUMN maps_phone TEXT"),
]


def run_migrations(db) -> int:
    """Apply pending migrations and return the number applied.

    Args:
        db: A DatabaseManager instance (must expose execute_query / fetch_all).

    Returns:
        Number of newly-applied migrations.
    """
    # Ensure the version-tracking table exists
    db.execute_query(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )

    applied = {
        row["version"]
        for row in db.fetch_all("SELECT version FROM schema_version")
    }

    applied_count = 0
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        try:
            db.execute_query(sql)
            db.execute_query(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, vn_iso()),
            )
            applied_count += 1
            logger.info(f"Migration {version} applied successfully.")
        except Exception as e:
            logger.error(f"Migration {version} FAILED: {e}")
            raise

    if applied_count:
        logger.info(f"Migrations complete: {applied_count} applied.")
    return applied_count
