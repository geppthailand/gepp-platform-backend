"""
Re-run the "approved → traceability group" step for given transactions.

When to use: a bulk approve committed the approvals but its traceability-group step failed.
Example: 2026-10-06 on DEV, org 35. Migration 101 had not been run, the batch insert aborted
the request's DB transaction, and the group upsert after it was skipped (fixed since: the
upsert now runs first and the batch step has its own savepoint).

Safe to repeat: the step only adds record ids that are not in a group yet.

Usage:
  python scripts/reupsert_traceability_groups.py --env .env.dev --ids 101436,108622,...
      → read-only: how many approved records of these transactions are in no group
  python scripts/reupsert_traceability_groups.py --env .env.dev --ids ... --apply
      → run the upsert for the approved ones, then report again
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

_UNGROUPED_SQL = """
    SELECT count(*) FROM transaction_records r
    WHERE r.created_transaction_id = ANY(:ids)
      AND r.status = 'approved' AND r.is_active AND r.deleted_date IS NULL
      AND NOT EXISTS (
        SELECT 1 FROM traceability_transaction_group g
        WHERE r.id = ANY(g.transaction_record_id) AND g.deleted_date IS NULL
      )
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', required=True, help='comma-separated transaction ids')
    ap.add_argument('--env', default='.env.local')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    ids = sorted({int(x) for x in a.ids.split(',') if x.strip()})

    from dotenv import load_dotenv
    load_dotenv(a.env)
    from sqlalchemy import text
    from GEPPPlatform.libs.database import get_session
    from GEPPPlatform.services.cores.transaction_audit.manual_audit_handlers import (
        _bulk_upsert_traceability_groups_on_approve,
    )

    with get_session() as db:
        approved = [r[0] for r in db.execute(
            text("SELECT id FROM transactions WHERE id = ANY(:ids) AND status = 'approved' AND deleted_date IS NULL"),
            {'ids': ids}).fetchall()]
        before = db.execute(text(_UNGROUPED_SQL), {'ids': ids}).scalar()
        print(f"{len(ids)} ids, {len(approved)} approved; approved records in no traceability group: {before}")
        if not a.apply:
            print('read-only (add --apply to fix)')
            return 0
        _bulk_upsert_traceability_groups_on_approve(db, approved)
        after = db.execute(text(_UNGROUPED_SQL), {'ids': ids}).scalar()
        print(f"after: approved records in no traceability group: {after}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
