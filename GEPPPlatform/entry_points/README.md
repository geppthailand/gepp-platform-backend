# Lambda Entry Points

Deployment-facing handlers live here. Keep this package thin: route Lambda
events into services, but keep reusable business logic in `GEPPPlatform.services`
or shared helpers in `GEPPPlatform.libs`.

| Lambda purpose | Handler |
| --- | --- |
| Main HTTP API | `GEPPPlatform.entry_points.GEPPPlatform.main` |
| AI audit cron | `GEPPPlatform.entry_points.audit_cron.cron_process_audits` |
| IoT health cron | `GEPPPlatform.entry_points.iot_health_cron.cron_iot_health_snapshot` |
| PDF export hub | `GEPPPlatform.entry_points.GEPPGenerateV3Report.lambda_handler` |
| Scheduled reports | `GEPPPlatform.entry_points.GEPPScheduleNotiReport.lambda_handler` |
| CRM campaign scheduler | `GEPPPlatform.entry_points.campaign_scheduler.lambda_handler` |
| CRM profile refresher | `GEPPPlatform.entry_points.profile_refresher.lambda_handler` |
| BMA Google-Sheet cron | `GEPPPlatform.entry_points.GEPPV3BMAGsheetCron.lambda_handler` |

## Cron functions

| Handler | Function name | Schedule | Notes |
| --- | --- | --- | --- |
| `audit_cron.cron_process_audits` | `<ENV>-GEPPPlatform-AUDITCRON` | frequent | Needs `OPENROUTER_API_KEY` |
| `iot_health_cron.cron_iot_health_snapshot` | `<ENV>-GEPPPlatform-IOTHEALTHCRON` | `rate(5 minutes)` | Feeds the Fleet online% chart |
| `GEPPV3BMAGsheetCron.lambda_handler` | `<ENV>-GEPPV3BMAGsheetCron` | `cron(0 19 ? * SUN *)` | Writes ไม่เทรวม figures to the BMA sheet |

### BMA Google-Sheet cron

Pushes the ไม่เทรวม (BKK Zero Waste, org 67) figures into the BMA workbook,
replacing what used to be typed in by hand. One weekly run refreshes three
things:

| Tab(s) | Grain | Service |
| --- | --- | --- |
| `All data-GEPP` | month × เขต, this year and last | `bma_gsheet_service.py` |
| `Origin`, `Overall Project` | reporting site, monthly averages | `bma_gsheet_service.py` |
| `[Origin] <category>` × 7 | **origin × month, 2023-01 onwards** | `bma_origin_monthly_service.py` |

`bma_gsheet_service.py` documents the `All data-GEPP` column formulas (recovered
by regression against the sheet's own rows) and how เขต is resolved from
`user_locations.district_id`.

Weekly rather than monthly because every one of those recomputes history rather
than appending to it — records get back-dated, corrected and soft-deleted long
after the month they belong to.

#### The seven `[Origin] <category>` tabs

One tab per category column of `All data-GEPP`, each laid out as:

| A | B | C | D | E… |
| --- | --- | --- | --- | --- |
| location id | location parent | location name | **baseline** | 2023-01, 2023-02, … |

Rows are origins — every location with transactions, no roll-up, so a floor gets
its own row unlike on `Origin`. Two rules make the tabs safe to put formulas in,
and both are enforced by `tests/test_bma_origin_monthly.py`:

* **column D is never written** except once, to set its header, and only while
  that cell is blank. Ops keeps formulas there and they address rows by
  position, so every write is split into `A:C` and `E:…`.
* **rows are append-only.** An origin keeps the row it first got. One that stops
  reporting is not removed — it reads 0 — because deleting it would renumber
  everything below and silently re-point every baseline.

Nothing is cleared: the block only grows (a column per month, a row per new
origin), so `values.update` on the exact rectangle leaves the rest alone.

Totals reconcile with `All data-GEPP` to the cent — summing a tab over the
origins of one เขต reproduces that เขต's column, and `CONSTRUCTION`/`RUBBER`
fold into `general waste` in both.

Environment:

| Variable | Required | Purpose |
| --- | --- | --- |
| `BMA_GSHEET_SA_SECRET_ID` | one of these | Secrets Manager id holding the service-account JSON |
| `BMA_GSHEET_SA_JSON` | one of these | The service-account JSON inline |
| `BMA_GSHEET_SA_FILE` | one of these | Path to the key file (local dev only) |
| `BMA_GSHEET_ID` | no | Target sheet; defaults to the live workbook |

The sheet must be shared with the service account's `client_email` as an
**Editor** — a service account can see nothing until it is invited like any
other user.

**Layer: `layers/bmagsheet-min.txt` — psycopg2-binary only, ~4 MB zipped.**

Measured, not assumed: the function was run with `sqlalchemy`, `pgvector`,
`numpy`, `geoalchemy2`, `google*`, `cryptography`, `bcrypt`, `pyjwt` and
`pillow` all blocked at import time, and completed normally. `psycopg2` is the
only third-party module it loads.

| | unzipped | zipped |
| --- | --- | --- |
| `platform.txt` + Google SDK | ~71 MB | — |
| `bmagsheet-min.txt` | 11 MB | **4.1 MB** |

Three things make that possible:

- **Raw SQL, no ORM.** The entry point calls `psycopg2.connect` directly instead
  of `libs.database`, which imports every model at module scope and so drags in
  pgvector → numpy and geoalchemy2 (~40 MB) that this job never touches.
- **One paramstyle.** Queries use psycopg2's `%(name)s`, which `exec_driver_sql`
  also accepts — so `BMAGSheetService` takes *either* a bare DBAPI connection
  (cron) or a SQLAlchemy `Session` (platform Lambda) and returns identical rows.
- **Standard-library Google.** `libs/google_sa_auth.py` does RS256 + REST with
  nothing but stdlib; `boto3` ships with the runtime. See `layers/bmagsheet.txt`
  and `tests/test_google_sa_auth.py`.

`platform.txt` also works if you would rather share one layer.

Test without writing anything:

```bash
aws lambda invoke --function-name DEV-GEPPV3BMAGsheetCron \
  --payload '{"dry_run": true}' --cli-binary-format raw-in-base64-out \
  /dev/stdout --profile gepp
```

Narrow a run to part of the job:

```bash
# only the seven per-origin tabs
--payload '{"replace_years": [], "skip_origin": true}'
# only one of them
--payload '{"skip_origin": true, "origin_monthly_columns": ["general waste"]}'
# everything except them
--payload '{"skip_origin_monthly": true}'
```

Deploy: `bash update_function.sh DEV bma-gsheet-cron "--profile gepp"`

