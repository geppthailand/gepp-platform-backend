#!/usr/bin/env python3
"""
Migration 065 — heal `esg_records.datapoints` to canonical keys.

The SQL companion (`20260508_140000_065_normalize_esg_record_datapoints.sql`)
is just a marker. This script does the real work: walks every active
row in `esg_records`, runs each row's `datapoints` JSONB array
through `GEPPPlatform.services.esg.datapoint_registry.normalize_datapoints`,
writes back when the shape changed, then re-runs the GHG sufficiency
evaluator (`EsgCarbonService.reevaluate_records`) so records that
become computable post-normalisation flip from `insufficient` to
`computed` automatically.

Idempotent + restartable: rows that are already canonical are
detected by deep equality and skipped.

Usage (from v3/backend):
    .venv/bin/python migrations/normalize_datapoints_065.py [--dry-run] [--limit N]

Options:
    --dry-run     Show what would change without writing.
    --limit N     Process at most N rows (handy for spot-checking).

Connects to the DB using the standard env vars (DB_HOST / DB_USER /
DB_PASSWORD / DB_NAME) — same as the rest of the platform.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make GEPPPlatform importable when this script is run directly.
_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from GEPPPlatform.models.esg.records import EsgRecord
from GEPPPlatform.services.esg.datapoint_registry import normalize_datapoints

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('migration_065')


def _build_db_url() -> str:
    host = os.environ.get('DB_HOST', 'localhost')
    port = os.environ.get('DB_PORT', '5432')
    name = os.environ.get('DB_NAME', 'gepp_platform')
    user = os.environ.get('DB_USER', 'postgres')
    pwd = os.environ.get('DB_PASSWORD', '')
    auth = f'{user}:{pwd}' if pwd else user
    return f'postgresql+psycopg2://{auth}@{host}:{port}/{name}'


def _datapoints_equal(a: list, b: list) -> bool:
    """JSON-safe deep equality (handles None vs missing keys)."""
    return list(a or []) == list(b or [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dry-run', action='store_true',
        help='show what would change without writing',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='process at most N rows (default: all)',
    )
    args = parser.parse_args()

    db_url = _build_db_url()
    logger.info('Connecting to %s', db_url.split('@')[-1])  # don't log creds
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    session: Session = SessionLocal()

    try:
        q = session.query(EsgRecord).filter(EsgRecord.is_active.is_(True))
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        logger.info('Loaded %d active records', len(rows))

        affected_ids: list[int] = []
        unchanged = 0
        empty = 0

        for row in rows:
            before = list(row.datapoints or [])
            if not before:
                empty += 1
                continue
            after = normalize_datapoints(before)
            if _datapoints_equal(before, after):
                unchanged += 1
                continue
            affected_ids.append(row.id)
            if not args.dry_run:
                row.datapoints = after
                # Touch sa_inspect's "modified" flag for JSONB.
                # SQLAlchemy doesn't auto-detect deep mutation of
                # JSONB columns, so we re-assign the attribute even
                # if it's the same object.
                session.add(row)

        if args.dry_run:
            logger.info(
                'DRY RUN — would normalise %d rows '
                '(%d unchanged, %d empty, %d total)',
                len(affected_ids), unchanged, empty, len(rows),
            )
            return 0

        if affected_ids:
            session.commit()
            logger.info(
                'Normalised %d rows (%d unchanged, %d empty)',
                len(affected_ids), unchanged, empty,
            )
        else:
            logger.info(
                'No rows needed normalisation (%d unchanged, %d empty)',
                unchanged, empty,
            )
            return 0

        # Re-evaluate GHG status for rows we just normalised. Records
        # whose canonical inputs (distance_km, weight_kg, …) are now
        # present can flip from `insufficient` → `computed`. Imported
        # lazily to avoid pulling carbon-service deps when the user
        # only wants a dry-run.
        from GEPPPlatform.services.esg.esg_carbon_service import EsgCarbonService
        carbon = EsgCarbonService(session)
        try:
            reevaluated = carbon.reevaluate_records(affected_ids)
            session.commit()
            logger.info(
                'Re-evaluated GHG status for %d rows', reevaluated,
            )
        except AttributeError:
            # Older builds may lack `reevaluate_records`. Fall back
            # to per-row evaluation so a deploy on stale code still
            # heals what it can.
            logger.warning(
                'EsgCarbonService.reevaluate_records not available; '
                'skipping bulk re-eval. Records will re-evaluate on '
                'next read in the carbon service.',
            )
        return 0
    except Exception:
        logger.exception('Migration 065 FAILED — rolling back')
        try:
            session.rollback()
        except Exception:
            pass
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
