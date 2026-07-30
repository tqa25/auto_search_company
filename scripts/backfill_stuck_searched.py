"""One-time backfill for companies stuck in status='searched'.

Root cause (see completion_audit / get_top_scored_links dedup fix): filtered_links
were re-inserted on every pipeline run, so the scraper's top-N budget was consumed
by duplicate copies of one or two URLs. Most stuck companies only ever scraped a
single distinct URL, so the strict completion audit could never be satisfied and
the jobs churned as 'failed' -> reset to 'searched'.

This script triages the stuck companies:
  * Companies that already have usable contacts (phone or address) are marked
    'done' directly -- no API re-call needed.
  * Companies with no contacts are re-queued so the (now dedup-aware) pipeline can
    scrape the full set of distinct top URLs and extract contacts.

Run:  venv/bin/python scripts/backfill_stuck_searched.py [--db PATH] [--apply]
Without --apply it only prints the plan (dry run).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.time_utils import vn_timestamp


def _has_usable_contact(db: DatabaseManager, company_id: int) -> bool:
    row = db.fetch_one(
        """
        SELECT COUNT(*) AS n
        FROM extracted_contacts
        WHERE company_id = ?
          AND (
              (phone IS NOT NULL AND TRIM(phone) != '')
              OR (address IS NOT NULL AND TRIM(address) != '')
          )
        """,
        (company_id,),
    )
    return bool(row and row.get("n", 0) > 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/company_data.db"))
    parser.add_argument("--apply", action="store_true", help="Perform changes (default: dry run).")
    args = parser.parse_args(argv)

    db = DatabaseManager(args.db)
    stuck = db.fetch_all("SELECT id FROM companies WHERE status = 'searched'")
    stuck_ids = [row["id"] for row in stuck]

    to_done: list[int] = []
    to_requeue: list[int] = []
    for cid in stuck_ids:
        (to_done if _has_usable_contact(db, cid) else to_requeue).append(cid)

    print(f"DB: {args.db}")
    print(f"Stuck in 'searched': {len(stuck_ids)}")
    print(f"  -> mark done (have phone/address):     {len(to_done)}")
    print(f"  -> re-queue (no contact, need scrape): {len(to_requeue)}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to make changes.")
        return 0

    now = vn_timestamp()
    for cid in to_done:
        db.update_company(cid, status="done")
        db.update_pipeline_job(
            cid,
            status="done",
            current_step="Done",
            checkpoint="done",
            progress=100,
            finished_at=now,
            requested_action=None,
            last_error="backfill: had usable contacts; completed by dedup fix",
        )
    print(f"\nMarked {len(to_done)} companies done.")

    if to_requeue:
        result = db.enqueue_pipeline_jobs(to_requeue)
        print(f"Re-queued {len(result['queued'])} companies (skipped {len(result['skipped'])}).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
