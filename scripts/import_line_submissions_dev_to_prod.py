#!/usr/bin/env python3
"""
Move real LINE submissions from the DEV database into PROD.

Why this exists
---------------
The LINE channel webhook was still registered against `https://api.geppdata.com/v1-dev`,
so every photo sent to the ESG OA was processed by DEV-GEPPPlatform and written to
the dev database. On dev, the sending LINE users are bound to **org 35**
(`esg_users.organization_id`), and the webhook resolves the tenant from that
binding — so the submissions landed in org 35, not the demo org.

On prod the same LINE user ids are bound to **org 2783**, so once the webhook URL
is repointed new submissions arrive in the right place. This script is only for
the submissions already stranded on dev.

What it does
------------
Copies, for a bounded date window, from dev org 35 → prod org 2783:
  * esg_organization_data_extraction   (parent)
  * esg_records                        (child: extraction_id remapped)
  * esg_line_messages                  (independent)

Remaps that matter — the two databases have independent sequences:
  * organization_id : 35 → TARGET_ORG
  * user_id         : dev esg_users.id → prod esg_users.id, matched on
                      platform_user_id (the LINE user id, stable across DBs)
  * extraction_id   : dev id → the newly-inserted prod id

S3 is NOT copied: both lambdas use the same bucket
(`prod-gepp-platform-assets`) and file_key/evidence_image_url are absolute
`s3://` URIs, so the images already resolve from prod.

Idempotent: every inserted id is recorded in `esg_mock_seed_ids` under
`imported_*` entity names, and rows already imported (matched on natural keys —
source_message_id / line_message_id) are skipped. The `imported_*` prefix keeps
them clear of `unseed_esg_mock.sql`, which only removes the demo seed.

Usage:
  .venv/bin/python scripts/import_line_submissions_dev_to_prod.py --since 2026-08-19 --dry-run
  .venv/bin/python scripts/import_line_submissions_dev_to_prod.py --since 2026-08-19 --commit
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

SOURCE_ORG = 35
TARGET_ORG = 2783
BACKEND = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def connect(env: dict):
    return psycopg2.connect(
        host=env['DB_HOST'], port=env.get('DB_PORT', 5432),
        dbname=env['DB_NAME'], user=env['DB_USER'], password=env['DB_PASSWORD'],
    )


def cols(cur, table: str) -> list:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
    """, (table,))
    return [r[0] for r in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', required=True,
                    help='only copy rows with created_date >= this date (YYYY-MM-DD)')
    ap.add_argument('--commit', action='store_true',
                    help='actually write; default is a dry run')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    commit = args.commit and not args.dry_run

    dev = connect(load_env(BACKEND / 'migrations' / '.env.development'))
    prod = connect(load_env(BACKEND / 'migrations' / '.env'))
    dcur = dev.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    pcur = prod.cursor()

    print(f"window: created_date >= {args.since}   dev org {SOURCE_ORG} -> prod org {TARGET_ORG}")
    print(f"mode  : {'COMMIT' if commit else 'DRY RUN'}\n")

    pcur.execute("""
        CREATE TABLE IF NOT EXISTS esg_mock_seed_ids (
          id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL,
          entity VARCHAR(48) NOT NULL, entity_id BIGINT NOT NULL,
          created_date TIMESTAMPTZ NOT NULL DEFAULT NOW())
    """)

    # ── user id remap: dev esg_users.id -> prod esg_users.id, via LINE user id ──
    dcur.execute("SELECT id, platform_user_id FROM esg_users WHERE platform='line'")
    dev_users = {r['id']: r['platform_user_id'] for r in dcur.fetchall()}
    pcur.execute("SELECT id, platform_user_id FROM esg_users WHERE platform='line' AND organization_id=%s",
                 (TARGET_ORG,))
    prod_by_uid = {puid: pid for pid, puid in pcur.fetchall()}
    user_map = {did: prod_by_uid[puid] for did, puid in dev_users.items() if puid in prod_by_uid}
    print(f"user remap: {len(user_map)} dev esg_users resolve to prod org {TARGET_ORG}")
    for did, pid in sorted(user_map.items()):
        print(f"  dev esg_users.{did} -> prod esg_users.{pid}  ({dev_users[did][:14]}...)")
    print()

    def insert(table, row, skip=(), override=None):
        """Insert row into prod minus `skip` cols, with `override` applied. Returns new id."""
        data = {k: v for k, v in row.items() if k not in skip and k != 'id'}
        data.update(override or {})
        # JSONB columns come back from RealDictCursor already parsed into
        # dict/list. psycopg2 has no adapter for those going the other way
        # ("can't adapt type 'dict'"), so wrap them for the write. Affects
        # extractions/datapoint_matches/refs/structured_data on extractions and
        # datapoints/ghg_missing_fields on records.
        data = {
            k: (psycopg2.extras.Json(v) if isinstance(v, (dict, list)) else v)
            for k, v in data.items()
        }
        keys = list(data.keys())
        sql = (f"INSERT INTO {table} ({', '.join(keys)}) "
               f"VALUES ({', '.join(['%s'] * len(keys))}) RETURNING id")
        pcur.execute(sql, [data[k] for k in keys])
        new_id = pcur.fetchone()[0]
        pcur.execute("INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id) VALUES (%s,%s,%s)",
                     (TARGET_ORG, f'imported_{table}', new_id))
        return new_id

    # ── 1. extractions (parents) ───────────────────────────────────────────
    ex_cols = [c for c in cols(dev.cursor(), 'esg_organization_data_extraction')]
    dcur.execute(f"""
        SELECT {', '.join(ex_cols)} FROM esg_organization_data_extraction
        WHERE organization_id=%s AND created_date >= %s ORDER BY id
    """, (SOURCE_ORG, args.since))
    extractions = dcur.fetchall()

    pcur.execute("""SELECT source_message_id FROM esg_organization_data_extraction
                    WHERE organization_id=%s AND source_message_id IS NOT NULL""", (TARGET_ORG,))
    already_ex = {r[0] for r in pcur.fetchall()}

    ex_map = {}
    ex_new = ex_skip = 0
    for r in extractions:
        if r.get('source_message_id') and r['source_message_id'] in already_ex:
            ex_skip += 1
            continue
        if commit:
            ex_map[r['id']] = insert('esg_organization_data_extraction', r,
                                     override={'organization_id': TARGET_ORG})
        else:
            # Record the mapping even on a dry run, otherwise every child row
            # below looks orphaned and the dry-run report lies about what a
            # real run would do.
            ex_map[r['id']] = -1
        ex_new += 1
    print(f"extractions : {ex_new} to insert, {ex_skip} already present (skipped)")

    # ── 2. records (children — extraction_id + user_id remapped) ───────────
    rec_cols = cols(dev.cursor(), 'esg_records')
    dcur.execute(f"""
        SELECT {', '.join(rec_cols)} FROM esg_records
        WHERE organization_id=%s AND created_date >= %s ORDER BY id
    """, (SOURCE_ORG, args.since))
    records = dcur.fetchall()

    pcur.execute("""SELECT record_label, entry_date FROM esg_records
                    WHERE organization_id=%s""", (TARGET_ORG,))
    already_rec = {(a, b) for a, b in pcur.fetchall()}

    rec_new = rec_skip = rec_orphan = 0
    for r in records:
        if (r['record_label'], r['entry_date']) in already_rec:
            rec_skip += 1
            continue
        ov = {'organization_id': TARGET_ORG}
        if r.get('extraction_id'):
            if r['extraction_id'] in ex_map:
                ov['extraction_id'] = ex_map[r['extraction_id']]
            else:
                # Parent outside the window — drop the FK rather than point it
                # at a dev id that means something else on prod.
                ov['extraction_id'] = None
                rec_orphan += 1
        if r.get('user_id'):
            ov['user_id'] = user_map.get(r['user_id'])
        if commit:
            insert('esg_records', r, override=ov)
        rec_new += 1
    print(f"records     : {rec_new} to insert, {rec_skip} already present, "
          f"{rec_orphan} had extraction_id cleared (parent outside window)")

    # ── 3. line messages ───────────────────────────────────────────────────
    msg_cols = cols(dev.cursor(), 'esg_line_messages')
    dcur.execute(f"""
        SELECT {', '.join(msg_cols)} FROM esg_line_messages
        WHERE organization_id=%s AND created_date >= %s ORDER BY id
    """, (SOURCE_ORG, args.since))
    messages = dcur.fetchall()

    pcur.execute("SELECT line_message_id FROM esg_line_messages WHERE organization_id=%s",
                 (TARGET_ORG,))
    already_msg = {r[0] for r in pcur.fetchall()}

    msg_new = msg_skip = 0
    for r in messages:
        if r['line_message_id'] in already_msg:
            msg_skip += 1
            continue
        if commit:
            insert('esg_line_messages', r, override={'organization_id': TARGET_ORG})
        msg_new += 1
    print(f"messages    : {msg_new} to insert, {msg_skip} already present (skipped)")

    if commit:
        prod.commit()
        print("\nCOMMITTED.")
        pcur.execute("""SELECT entity, count(*) FROM esg_mock_seed_ids
                        WHERE organization_id=%s AND entity LIKE 'imported_%%'
                        GROUP BY entity ORDER BY entity""", (TARGET_ORG,))
        for e, n in pcur.fetchall():
            print(f"  registry {e}: {n}")
    else:
        prod.rollback()
        print("\nDRY RUN — nothing written. Re-run with --commit.")

    dev.close()
    prod.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
