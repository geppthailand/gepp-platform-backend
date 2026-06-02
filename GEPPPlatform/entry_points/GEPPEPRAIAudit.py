"""
Lambda entrypoint for the EPR AI Audit dedup cron.

Ported from gepp-v2-backend (GEPPV2.handlers.dedup_cron). Point AWS Lambda's
Handler config at:

    GEPPPlatform.entry_points.GEPPEPRAIAudit.handler

Trigger via EventBridge scheduled rule. Recommended schedule expressions:
  - rate(1 minute)   for low-latency dedup (1440 invocations/day)
  - rate(5 minutes)  balanced (288 invocations/day) — good default
  - rate(15 minutes) sparse, for low traffic

Each invocation:
  1. Reaps any jobs stuck in 'processing' from a previous crashed Lambda
  2. Claims up to CRON_BATCH_SIZE pending 'embedding' jobs
  3. For each: calls worker.process_transaction
       - normal report  -> jobs.mark_done(result)
       - retry_later    -> jobs.release_job (sends back to pending, no attempt bump)
       - exception      -> jobs.mark_failed (auto-retries up to MAX_ATTEMPTS=3)
  4. Returns a summary

Test mode: invoke this Lambda with event payload
    {"test_mode": "integrity_project_41"}
to run 5 random project-41 txs through the integrity pipeline instead of the
normal cron tick. See _run_test_integrity_project_41 for details.

Tuning knobs (env vars, all optional):
  CRON_BATCH_SIZE                   how many jobs to claim per tick (default 3)
  CRON_STAGE                        which queue stage to process (default 'embedding')
  JOB_REAP_AFTER_SECONDS            recover jobs stuck in 'processing' for this
                                    long (default 1200 = 20 min, min 60)
  AI_AUDIT_API_BASE_URL             base URL of the deployed API (the EPR AI
                                    audit Lambda) used by the integrity test
                                    to POST /api/epr/ai_audit/embed-transaction.

Required env vars (same as the API Lambda):
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
  OPENROUTER_API_KEY
  LEGACY_DB_HOST, LEGACY_DB_PORT, LEGACY_DB_NAME, LEGACY_DB_USER, LEGACY_DB_PASS

IAM role needs the same DB access (VPC + Secrets Manager if applicable) plus
CloudWatch Logs write. No extra permissions beyond the API Lambda.
"""

import logging
import os
import random
import time
import traceback

import requests

from GEPPPlatform.libs.legacy_db import get_legacy_connection
from GEPPPlatform.services.cores.epr_ai_audit.cron import (
    jobs,
    legacy_import,
    worker,
)
from GEPPPlatform.services.cores.epr_ai_audit.cron.db import get_connection

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _batch_size() -> int:
    try:
        return max(1, int(os.environ.get("CRON_BATCH_SIZE", "3")))
    except (TypeError, ValueError):
        return 3


def _stage() -> str:
    return os.environ.get("CRON_STAGE") or jobs.STAGE_EMBEDDING


def handler(event, context):
    """Lambda entry: route between normal cron tick and test invocations.

    Invoke shapes:
      {}                                      → normal cron tick (EventBridge default)
      {"test_mode": "integrity_project_41"}   → run 5 random project-41 txs through
                                                the integrity pipeline and report results
    """
    if isinstance(event, dict) and event.get("test_mode") == "integrity_project_41":
        return _run_test_integrity_project_41()
    return _normal_cron_tick()


def _reap_after_seconds() -> int:
    """How long a job can stay in `processing` before it's considered stuck
    and the reaper recovers it. Default 1200s (20 min) = Lambda's 15-min hard
    timeout + a 5-min safety margin so we don't reap a still-running worker."""
    try:
        return max(60, int(os.environ.get("JOB_REAP_AFTER_SECONDS", "1200")))
    except ValueError:
        return 1200


def _normal_cron_tick():
    """The EventBridge handler body — claims and processes a batch of pending
    dedup jobs. Reaps any jobs stuck in `processing` from a previous Lambda
    timeout before claiming new work."""
    batch_size = _batch_size()
    stage = _stage()
    reap_after = _reap_after_seconds()
    logger.info(
        "dedup_cron tick: stage=%s batch_size=%d reap_after=%ds",
        stage, batch_size, reap_after,
    )

    summary = {
        "stage": stage,
        "reaped_reset": 0,
        "reaped_failed": 0,
        "claimed": 0,
        "done": 0,
        "released": 0,
        "failed": 0,
    }

    conn = get_connection()
    try:
        # Step 0: reap orphaned 'processing' jobs from prior killed Lambdas
        # back into the pool. This runs every tick so stuck jobs recover
        # within one cron interval after the timeout window elapses.
        with conn:
            reset_count, failed_count = jobs.reap_stale_processing_jobs(
                conn, stage, stale_after_seconds=reap_after,
            )
        summary["reaped_reset"] = reset_count
        summary["reaped_failed"] = failed_count
        if reset_count or failed_count:
            logger.info(
                "dedup_cron: reaper reset=%d failed=%d (threshold=%ds)",
                reset_count, failed_count, reap_after,
            )

        with conn:
            claimed = jobs.claim_next_jobs(conn, stage, batch_size=batch_size)
        summary["claimed"] = len(claimed)

        if not claimed:
            logger.info("dedup_cron: no pending jobs")
            return summary

        for job_id, tx_id in claimed:
            try:
                report = worker.process_transaction(conn, tx_id)
                with conn:
                    if report and report.get("retry_later"):
                        jobs.release_job(conn, job_id)
                        summary["released"] += 1
                        logger.info(
                            "dedup_cron: job=%s tx=%s released (%s)",
                            job_id, tx_id, report.get("reason"),
                        )
                    else:
                        jobs.mark_done(
                            conn, job_id, report or {"missing": True},
                            new_stage=jobs.STAGE_DEDUP_DONE,
                        )
                        summary["done"] += 1
                        logger.info(
                            "dedup_cron: job=%s tx=%s done (reason=%s, candidates=%d)",
                            job_id, tx_id,
                            (report or {}).get("reason", "ok"),
                            len((report or {}).get("candidates") or []),
                        )
            except Exception as exc:
                # Per-job error — record on the job row, keep going.
                logger.exception("dedup_cron: job=%s tx=%s FAILED: %s", job_id, tx_id, exc)
                try:
                    with conn:
                        jobs.mark_failed(
                            conn, job_id,
                            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                        )
                except Exception as inner:
                    # mark_failed itself errored — log and move on. The job
                    # row stays in 'processing'; the next claim won't pick it
                    # up until manually released, but we don't crash the tick.
                    logger.exception(
                        "dedup_cron: mark_failed errored for job=%s: %s",
                        job_id, inner,
                    )
                summary["failed"] += 1
    finally:
        conn.close()

    logger.info("dedup_cron summary: %s", summary)
    return summary


# ─── Test mode ──────────────────────────────────────────────────────────────

_TEST_PROJECT_ID = 41
_TEST_SAMPLE_SIZE = 5           # how many random legacy txs to pull and exercise integrity on
_TEST_SEED = 42                 # fixed seed so the same ids are picked every run (set to None for fresh randomness)

# Override AI_AUDIT_API_BASE_URL per environment. The test mode POSTs to
# /api/epr/ai_audit/embed-transaction on the deployed platform Lambda, so the
# URL must point at an environment that runs GEPPPlatform.entry_points.GEPPPlatform.
_DEFAULT_API_BASE_URL = ""

# How long to wait for the API Lambda to respond to a single POST. The
# embed endpoint is fast (no LLM work — just inserts + enqueue), but
# cold-start can take a few seconds.
_EMBED_REQUEST_TIMEOUT = 30


def _api_base_url() -> str:
    return os.environ.get("AI_AUDIT_API_BASE_URL", _DEFAULT_API_BASE_URL).rstrip("/")


def _post_embed_transaction(payload: dict) -> dict:
    """POST `payload` to the deployed API's /api/epr/ai_audit/embed-transaction
    route and return the parsed JSON body. Raises requests.HTTPError on non-2xx."""
    base = _api_base_url()
    if not base:
        raise ValueError(
            "AI_AUDIT_API_BASE_URL is not set — test mode requires the URL of "
            "a deployed platform Lambda running GEPPPlatform.entry_points.GEPPPlatform"
        )
    url = f"{base}/api/epr/ai_audit/embed-transaction"
    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=_EMBED_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_legacy_payload(mysql_conn, tx_id: int) -> dict:
    """Build an API-shaped payload from a legacy transaction + its images + its records."""
    with mysql_conn.cursor() as cur:
        cur.execute(
            "SELECT id, invoice_no, note, total_quantity, transaction_date, epr_project_id "
            "FROM transactions WHERE id = %s",
            (tx_id,),
        )
        tx_row = cur.fetchone()
        cur.execute(
            "SELECT i.id, i.name, i.image_url, t.name "
            "FROM transaction_images i LEFT JOIN transaction_image_types t ON t.id = i.type "
            "WHERE i.transaction_id = %s AND i.deleted_date IS NULL ORDER BY i.id",
            (tx_id,),
        )
        imgs = cur.fetchall()

        # Per-material records for this transaction.
        cur.execute(
            "SELECT id, quantity, price, note, transaction_date, material "
            "FROM epr_transaction_records "
            "WHERE transaction_id = %s AND deleted_date IS NULL "
            "ORDER BY id ASC",
            (tx_id,),
        )
        record_rows = cur.fetchall()

        # Record-level images, batched by record id.
        record_ids = [r[0] for r in record_rows]
        rec_imgs_by_record: dict[int, list[tuple]] = {}
        if record_ids:
            cur.execute(
                "SELECT ri.id, ri.name, ri.image_url, ri.epr_transaction_record_id, t.name "
                "FROM epr_transaction_record_images ri "
                "LEFT JOIN transaction_image_types t ON t.id = ri.type "
                "WHERE ri.epr_transaction_record_id IN %s "
                "AND ri.deleted_date IS NULL "
                "ORDER BY ri.id ASC",
                (tuple(record_ids),),
            )
            for r in cur.fetchall():
                rec_imgs_by_record.setdefault(r[3], []).append(r)

    legacy_id, invoice_no, note, total_quantity, transaction_date, epr_project_id = tx_row

    materials = []
    for rec in record_rows:
        rec_id, quantity, price, rec_note, rec_date, material_id = rec
        materials.append({
            "id": str(rec_id),
            "quantity": float(quantity) if quantity is not None else None,
            "price": float(price) if price is not None else None,
            "note": rec_note,
            "transactionDate": rec_date.isoformat() if rec_date else None,
            "material": material_id,
            "images": [
                {
                    "id": str(ri[0]), "isActive": True, "name": ri[1], "imageURL": ri[2],
                    "type": {"name": ri[4]} if ri[4] else None,
                }
                for ri in rec_imgs_by_record.get(rec_id, [])
            ],
        })

    return {
        "id": str(legacy_id),
        "invoiceNo": invoice_no,
        "note": note,
        "totalQuantity": float(total_quantity) if total_quantity is not None else None,
        "transactionDate": transaction_date.isoformat() if transaction_date else None,
        "eprProjectId": epr_project_id,
        "images": [
            {
                "id": str(r[0]), "isActive": True, "name": r[1], "imageURL": r[2],
                "type": {"name": r[3]} if r[3] else None,
            }
            for r in imgs
        ],
        "eprMaterials": materials,
    }


def _run_test_integrity_project_41():
    """Integrity-only test: pull _TEST_SAMPLE_SIZE random legacy transactions
    from project 41 (with their records + images), submit them via the embed
    endpoint, run the worker synchronously, and return a focused integrity
    report for each."""
    start = time.time()
    rng = random.Random(_TEST_SEED)

    pg = get_connection()
    mysql = get_legacy_connection()
    try:
        result = {
            "test": "integrity_project_41",
            "project_id": _TEST_PROJECT_ID,
            "sample_size": _TEST_SAMPLE_SIZE,
        }

        # 1. Clean prior test state for this project
        with pg:
            with pg.cursor() as cur:
                cur.execute(
                    "DELETE FROM epr_dedup_jobs WHERE transaction_id IN ("
                    "  SELECT id FROM epr_transactions_embeded WHERE epr_project_id = %s)",
                    (_TEST_PROJECT_ID,),
                )
                cur.execute(
                    "DELETE FROM epr_project_import_state WHERE epr_project_id = %s",
                    (_TEST_PROJECT_ID,),
                )
                cur.execute(
                    "DELETE FROM epr_transactions_embeded WHERE epr_project_id = %s",
                    (_TEST_PROJECT_ID,),
                )

        # 2. Pick N random legacy tx ids
        with mysql.cursor() as cur:
            cur.execute(
                "SELECT id FROM transactions "
                "WHERE epr_project_id = %s AND deleted_date IS NULL "
                "ORDER BY id",
                (_TEST_PROJECT_ID,),
            )
            all_ids = [r[0] for r in cur.fetchall()]
        if len(all_ids) < _TEST_SAMPLE_SIZE:
            return {"error": f"project {_TEST_PROJECT_ID} has only {len(all_ids)} legacy txs, "
                             f"need ≥ {_TEST_SAMPLE_SIZE}"}
        chosen_ids = rng.sample(all_ids, _TEST_SAMPLE_SIZE)
        result["chosen_legacy_ids"] = chosen_ids

        # 3. Bypass the worker's legacy-import gate.
        legacy_import._init_state(pg, _TEST_PROJECT_ID)
        legacy_import._mark_complete(pg, _TEST_PROJECT_ID)

        # 4. Submit each via the deployed API endpoint.
        submissions = []
        submission_errors = []
        for legacy_id in chosen_ids:
            payload = _fetch_legacy_payload(mysql, legacy_id)
            try:
                resp_body = _post_embed_transaction(payload)
                # The platform-backend dispatcher wraps results as
                # {success, data: {success, data: {<service payload>}}}.
                inner = resp_body.get("data") or resp_body
                if isinstance(inner, dict) and "data" in inner:
                    inner = inner["data"]
                api_id = inner["transaction"]["db_id"]
            except (requests.RequestException, KeyError, ValueError) as exc:
                logger.warning(
                    "test: embed POST failed for legacy_id=%s: %s",
                    legacy_id, exc,
                )
                submission_errors.append({"legacy_id": legacy_id, "error": repr(exc)})
                continue
            submissions.append({
                "legacy_id": legacy_id,
                "api_tx_id": api_id,
                "image_count": len(payload.get("images") or []),
                "record_count": len(payload.get("eprMaterials") or []),
                "record_image_count": sum(
                    len(m.get("images") or [])
                    for m in (payload.get("eprMaterials") or [])
                ),
            })
        if submission_errors:
            result["submission_errors"] = submission_errors

        # 5. Drain the jobs for these txs through the worker
        api_tx_ids = [s["api_tx_id"] for s in submissions]
        with pg.cursor() as cur:
            cur.execute(
                "SELECT id, transaction_id FROM epr_dedup_jobs "
                "WHERE transaction_id = ANY(%s) AND status = 'pending'",
                (api_tx_ids,),
            )
            test_jobs = cur.fetchall()

        for job_id, tx_id in test_jobs:
            try:
                with pg:
                    with pg.cursor() as cur:
                        cur.execute(
                            "UPDATE epr_dedup_jobs SET status='processing', started_date=NOW(), "
                            "attempts=attempts+1 WHERE id=%s",
                            (job_id,),
                        )
                report = worker.process_transaction(pg, tx_id)
                with pg:
                    if report and report.get("retry_later"):
                        jobs.release_job(pg, job_id)
                    else:
                        jobs.mark_done(
                            pg, job_id, report or {"missing": True},
                            new_stage=jobs.STAGE_DEDUP_DONE,
                        )
            except Exception as exc:
                logger.exception("test: tx=%s failed: %s", tx_id, exc)
                with pg:
                    jobs.mark_failed(pg, job_id, repr(exc))

        # 6. Collect integrity findings (parent + per-record) for each submission
        for sub in submissions:
            with pg.cursor() as cur:
                cur.execute(
                    "SELECT status, result FROM epr_dedup_jobs "
                    "WHERE transaction_id = %s ORDER BY id DESC LIMIT 1",
                    (sub["api_tx_id"],),
                )
                row = cur.fetchone()
            if row is None:
                sub["job_status"] = "no-job"
                sub["parent_status"] = None
                sub["integrity"] = {}
                continue
            sub["job_status"] = row[0]
            r = row[1] or {}
            sub["parent_status"] = r.get("parent_status")

            parent_flags = r.get("parent_flags") or {}
            integrity = parent_flags.get("integrity") or {}
            sub["integrity"] = {
                "parent": {
                    "matched_fields": integrity.get("matched_fields") or [],
                    "issues_count": len(integrity.get("issues") or []),
                    "issues": integrity.get("issues") or [],
                    "checked_image_count": integrity.get("checked_image_count", 0),
                    "errors": integrity.get("errors") or [],
                },
                "records": integrity.get("records") or [],
            }

        result["submissions"] = submissions
        result["elapsed_seconds"] = round(time.time() - start, 1)
        return result
    finally:
        try:
            mysql.close()
        except Exception:
            pass
        try:
            pg.close()
        except Exception:
            pass
