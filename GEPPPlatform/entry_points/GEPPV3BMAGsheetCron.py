"""BMA Google-Sheet cron — pushes ไม่เทรวม (BKK Zero Waste) figures weekly.

Wire this as a Lambda fired by an EventBridge rule:

    Function:    {ENV}-GEPPV3BMAGsheetCron
    Schedule:    cron(0 19 ? * SUN *)   02:00 UTC+7 every Monday
    Handler:     GEPPPlatform.entry_points.GEPPV3BMAGsheetCron.lambda_handler
    Memory:      512 MB     (a few grouped queries + Sheets writes)
    Timeout:     300 s
    Env:         BMA_GSHEET_SA_SECRET_ID  (or BMA_GSHEET_SA_JSON)
                 BMA_GSHEET_ID            (optional; defaults to the live sheet)

Three things are refreshed on every run:

  * `All data-GEPP` — (month × เขต) totals for this year and last;
  * `Origin` + `Overall Project` — per-site monthly averages and their totals;
  * `[Origin] <category>` × 7 — per-origin monthly kg from 2023-01 onwards.

Weekly rather than monthly because all three recompute history rather than
appending to it: records get back-dated, corrected and soft-deleted long after
the month they belong to, so "was last month still right?" is a question worth
asking more than once.

The body stays thin on purpose — everything real lives in
`services/integrations/bma/bma_gsheet_service.py` (which documents the recovered
column formulas and how เขต is resolved) and `bma_origin_monthly_service.py`
(which documents why the per-origin tabs are append-only and never touch their
`baseline` column).

LAYER
    This function needs **psycopg2-binary only**. It connects with psycopg2
    directly rather than through `libs.database`, because that module imports the
    whole models package at import time, which drags in pgvector -> numpy and
    geoalchemy2 (~40 MB) that a raw-SQL job never touches. SQLAlchemy is not
    needed either: the service runs on a bare DBAPI connection. Google is
    reached via `libs.google_sa_auth`, which is standard library only, and boto3
    ships with the runtime.

    See `layers/bmagsheet-min.txt`.

Deploy with:  bash update_function.sh DEV bma-gsheet-cron "--profile gepp"

**With no payload it writes THIS YEAR AND LAST** and leaves every other row in
the tab exactly as it found it. That is the intended production behaviour, so
the EventBridge rule needs no constant input at all. Two years rather than one
because data lands late — a run in January still has to close out December.

Years before `MANAGED_FROM_YEAR` (2025) are refused even if explicitly asked
for, because the cron does not own them.

That default is load-bearing, not tidiness. The `All data-GEPP` tab holds two
data sets:

  * rows we generate — categorised waste for the เขต the project operates in;
  * rows we cannot regenerate — 'general waste'-only rows covering all 50 เขต,
    sourced from BMA rather than from our transactions (v3 can only resolve เขต
    for the handful of districts with location setup done), plus hand-curated
    history from before this cron existed.

A blanket overwrite deletes the second set — ~450 tonnes across 403 rows. A
scheduled job must not be one missing parameter away from that.

Event payload (all optional):
    {}                            this year + last  <- production default
    {"dry_run": true}             build + report coverage, write nothing
    {"replace_years": [2025,2026]} overwrite just those years
    {"replace_years": "all"}      rebuild the whole tab (destructive — above)
    {"year_from": 2025}           limit which years are BUILT
    {"sheet_id": "..."}           target a copy instead of the live sheet
    {"tab": "..."}                target a different tab
    {"skip_origin": true}         leave `Origin` / `Overall Project` alone
    {"skip_origin_monthly": true} leave the seven `[Origin] <category>` tabs alone
    {"origin_monthly_columns": ["general waste"]}
                                  refresh only some of those seven

If a year in scope produces no rows the write is skipped rather than clearing
that year, so a month whose data has not landed yet cannot blank the report.
"""

import json
import logging
import os
from contextlib import contextmanager


@contextmanager
def _db_connection():
    """A read-only psycopg2 connection, opened without touching the ORM.

    Read-only is set on the session itself so the server rejects any write —
    this job only ever SELECTs, and a guarantee beats an intention.
    """
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'gepp_platform'),
        user=os.environ.get('DB_USER', 'postgres'),
        # `libs/database.py` reads DB_PASS; accept DB_PASSWORD too so the same
        # env file works for the migration runner and for this function.
        password=os.environ.get('DB_PASS') or os.environ.get('DB_PASSWORD', ''),
        connect_timeout=int(os.environ.get('DB_CONNECT_TIMEOUT', '30')),
    )
    try:
        conn.set_session(readonly=True)
        yield conn
    finally:
        conn.close()


def lambda_handler(event, context):
    """EventBridge cron entrypoint. Returns the service's stats dict."""
    logger = logging.getLogger(__name__)
    logger.info("Starting GEPPV3BMAGsheetCron")

    event = event or {}
    # EventBridge can deliver the payload as a JSON string when the rule uses a
    # constant input; accept both so a hand-made test event also works.
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except ValueError:
            event = {}

    try:
        from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
            BMAGSheetService, ORG_ID,
        )

        with _db_connection() as conn:
            svc = BMAGSheetService(conn)
            # Absent -> the service defaults to the current year only.
            # "all" is the explicit opt-in to a full, destructive rebuild.
            replace_years = event.get('replace_years')
            if isinstance(replace_years, str) and replace_years.lower() != 'all':
                replace_years = [replace_years]
            elif isinstance(replace_years, int):
                replace_years = [replace_years]
            elif isinstance(replace_years, str):
                replace_years = replace_years.lower()   # 'all'

            org_id = int(event.get('org_id') or ORG_ID)
            dry_run = bool(event.get('dry_run'))
            sheet_id = event.get('sheet_id')

            result = svc.run(
                org_id=org_id,
                year_from=event.get('year_from'),
                dry_run=dry_run,
                sheet_id=sheet_id,
                tab=event.get('tab') or 'All data-GEPP',
                replace_years=replace_years,
            )

            # `Origin` (and the `Overall Project` totals derived from it) are
            # master data, not a monthly series, so they are refreshed on the
            # same run unless explicitly skipped.
            if not event.get('skip_origin'):
                result['origin'] = svc.sync_origin_and_overall(
                    org_id=org_id, sheet_id=sheet_id, dry_run=dry_run)

            # The per-origin category tabs are their own service: same source
            # data, different grain (origin × month rather than เขต × month),
            # and an append-only write that must not disturb the `baseline`
            # column ops keeps formulas in.
            if not event.get('skip_origin_monthly'):
                from GEPPPlatform.services.integrations.bma.bma_origin_monthly_service import (
                    BMAOriginMonthlyService,
                )
                result['origin_monthly'] = BMAOriginMonthlyService(conn).sync(
                    org_id=org_id, sheet_id=sheet_id, dry_run=dry_run,
                    columns=event.get('origin_monthly_columns'))

        logger.info("GEPPV3BMAGsheetCron done: %s", json.dumps(result, default=str))
        return {'success': True, **result}

    except Exception as e:
        logger.exception("GEPPV3BMAGsheetCron failed")
        return {'success': False, 'error': str(e)}


#: Alias so the handler can also be referenced by an explicit cron-ish name,
#: matching `audit_cron.cron_process_audits` / `iot_health_cron.*`.
cron_bma_gsheet = lambda_handler
