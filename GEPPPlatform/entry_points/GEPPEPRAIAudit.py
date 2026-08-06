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
       - exception      -> jobs.mark_failed (auto-retries up to MAX_ATTEMPTS=3)
  4. Returns a summary

Test mode: invoke this Lambda with event payload
    {"test_mode": "ocr_random"}
to dump one random embedded transaction's files at the OCR reader instead of
running the normal cron tick. See _run_test_ocr_random for details.

Tuning knobs (env vars, all optional):
  CRON_BATCH_SIZE                   how many jobs to claim per tick (default 3)
  CRON_STAGE                        which queue stage to process (default 'embedding')
  JOB_REAP_AFTER_SECONDS            recover jobs stuck in 'processing' for this
                                    long (default 1200 = 20 min, min 60)

Required env vars (same as the API Lambda):
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
  OPENROUTER_API_KEY
  LEGACY_DB_HOST, LEGACY_DB_PORT, LEGACY_DB_NAME, LEGACY_DB_USER, LEGACY_DB_PASS
    (still needed — the worker reads each project's ai_audit on/off flag from
     epr_project_ai_audit_setting in the legacy DB)

IAM role needs the same DB access (VPC + Secrets Manager if applicable) plus
CloudWatch Logs write. No extra permissions beyond the API Lambda.
"""

import logging
import os
import random
import traceback

from GEPPPlatform.services.cores.epr_ai_audit.cron import jobs, worker
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
      {}                          → normal cron tick (EventBridge default)
      {"test_mode": "ocr_random"} → run one transaction's files through the OCR
                                    reader and report what was extracted
    """
    if isinstance(event, dict) and event.get("test_mode") == "ocr_random":
        return _run_test_ocr_random(event)
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

# Default form used by the OCR test when the event doesn't supply one.
# Mirrors the real frontend payload shape (txn-level fields + one record_field).
_OCR_TEST_FIELDS = [
    {"name": "invoiceNo", "type": "text"},
    {"name": "transactionDate", "type": "text"},
    {"name": "weight", "type": "text"},
    {"name": "invoice/tax_invoice/cash_bill/payment_voucher/id_card", "type": "file"},
    {"record_field": [
        {"name": "weight", "type": "text"},
        {"name": "pricePerUnit", "type": "text"},
        {"name": "totalPrice", "type": "text"},
        {"name": "transactionDate", "type": "text"},
        {"name": "Baling", "type": "tags", "options": ["Non-Baled", "Baled"]},
        {"name": "product_weighing_sheet/product_weighing_image", "type": "file"},
        {"name": "product_image", "type": "file"},
    ]},
]


def _run_test_ocr_random(event):
    """OCR test: pick a random embedded transaction that has files, dump ALL
    its files (transaction-level + every record's) at the OCR reader, and
    return what the vision LLM extracts.

    Event knobs (all optional):
      {"test_mode": "ocr_random", "project_id": 41, "transaction_id": 123,
       "fields": [...custom form...]}
    """
    from GEPPPlatform.services.cores.epr_ai_audit.api.ocr import read_transaction

    project_id = event.get("project_id")
    tx_id = event.get("transaction_id")
    fields = event.get("fields") or _OCR_TEST_FIELDS

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if tx_id is None:
                # random tx that actually has at least one file (either level)
                where = "t.deleted_date IS NULL"
                params = []
                if project_id is not None:
                    where += " AND t.epr_project_id = %s"
                    params.append(project_id)
                cur.execute(
                    f"""
                    SELECT t.id FROM epr_transactions_embeded t
                    WHERE {where} AND (
                        EXISTS (SELECT 1 FROM epr_transaction_image i
                                WHERE i.transaction_id = t.id)
                        OR EXISTS (SELECT 1 FROM epr_transaction_record_image ri
                                   JOIN epr_transaction_records_embeded r
                                     ON r.id = ri.epr_transaction_record_id
                                   WHERE r.transaction_id = t.id)
                    )
                    ORDER BY t.id
                    """,
                    params,
                )
                ids = [r[0] for r in cur.fetchall()]
                if not ids:
                    return {"test": "ocr_random", "error": "no transactions with files found"}
                tx_id = random.choice(ids)

            # transaction-level files
            cur.execute(
                "SELECT image_url FROM epr_transaction_image WHERE transaction_id = %s",
                (tx_id,),
            )
            urls = [r[0] for r in cur.fetchall() if r[0]]
            # record-level files
            cur.execute(
                """
                SELECT ri.image_url FROM epr_transaction_record_image ri
                JOIN epr_transaction_records_embeded r
                  ON r.id = ri.epr_transaction_record_id
                WHERE r.transaction_id = %s
                """,
                (tx_id,),
            )
            urls += [r[0] for r in cur.fetchall() if r[0]]
    finally:
        conn.close()

    if not urls:
        return {"test": "ocr_random", "transaction_id": tx_id, "error": "transaction has no files"}

    try:
        extracted = read_transaction(urls, fields)
    except Exception as exc:
        logger.exception("ocr_random test failed for tx=%s", tx_id)
        return {"test": "ocr_random", "transaction_id": tx_id,
                "file_count": len(urls), "error": repr(exc)}

    return {
        "test": "ocr_random",
        "transaction_id": tx_id,
        "file_count": len(urls),
        "files": urls,
        "extracted": extracted,
    }


