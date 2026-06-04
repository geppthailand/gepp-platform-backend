"""Queue helpers for the epr_dedup_jobs table — psycopg2 version.

Ported verbatim from gepp-v2-backend (GEPPV2.services.ai_audit.jobs). Used
by the cron Lambda (entry_points/GEPPEPRAIAudit.py) and the worker/legacy
import code, which all operate on raw psycopg2 connections.

The API-side equivalent (SQLAlchemy session) lives in `jobs.py` next to this
file — keep both in sync if you change job semantics.
"""

import logging
from typing import Optional

from psycopg2.extras import Json

logger = logging.getLogger(__name__)

# Stage names. New jobs land at STAGE_EMBEDDING; after a successful run the
# cron relabels them to STAGE_DEDUP_DONE so it's easy to tell at a glance
# (e.g. in a DB browser) which rows have already been processed.
STAGE_EMBEDDING = "embedding"
STAGE_DEDUP_DONE = "dedup_done"

# Job statuses
PENDING = "pending"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"

MAX_ATTEMPTS = 3
ERROR_MSG_MAX_LEN = 2000  # truncate so a runaway traceback doesn't blow up the row


def enqueue_job(conn, transaction_id: int, stage: str) -> None:
    """Insert a pending job for (transaction_id, stage). Idempotent."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO epr_dedup_jobs (transaction_id, stage) "
            "VALUES (%s, %s) "
            "ON CONFLICT (transaction_id, stage) DO NOTHING",
            (transaction_id, stage),
        )


def claim_next_jobs(conn, stage: str, batch_size: int = 10):
    """Claim up to `batch_size` pending jobs for `stage`, marking them 'processing'.

    Uses FOR UPDATE SKIP LOCKED so parallel workers won't grab the same rows.
    Increments `attempts` and stamps `started_date`. Caller is responsible for
    calling mark_done / mark_failed on each claimed job and committing.

    Returns: list of (job_id, transaction_id) tuples.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_dedup_jobs "
            "SET status = %s, "
            "    started_date = NOW(), "
            "    attempts = attempts + 1 "
            "WHERE id IN ("
            "  SELECT id FROM epr_dedup_jobs "
            "  WHERE status = %s AND stage = %s "
            "  ORDER BY created_date "
            "  LIMIT %s "
            "  FOR UPDATE SKIP LOCKED"
            ") "
            "RETURNING id, transaction_id",
            (PROCESSING, PENDING, stage, batch_size),
        )
        return cur.fetchall()


def mark_done(conn, job_id: int, result: dict, new_stage: Optional[str] = None) -> None:
    """Mark a job done and store its result. If `new_stage` is given, also
    relabel the stage column (cosmetic — makes it easier to see what's
    pending vs already-processed without joining on status)."""
    with conn.cursor() as cur:
        if new_stage is not None:
            cur.execute(
                "UPDATE epr_dedup_jobs "
                "SET status = %s, result = %s, completed_date = NOW(), stage = %s "
                "WHERE id = %s",
                (DONE, Json(result), new_stage, job_id),
            )
        else:
            cur.execute(
                "UPDATE epr_dedup_jobs "
                "SET status = %s, result = %s, completed_date = NOW() "
                "WHERE id = %s",
                (DONE, Json(result), job_id),
            )


def release_job(conn, job_id: int) -> None:
    """Send a claimed job back to 'pending' without bumping the attempts counter.

    Used when the worker did partial work (e.g., advanced a per-project import
    checkpoint) but couldn't finish the transaction's dedup yet — the same job
    should be picked up by the next cron tick and re-tried as if it had never
    been claimed. Unlike mark_failed, this doesn't count toward MAX_ATTEMPTS.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_dedup_jobs "
            "SET status = %s, "
            "    started_date = NULL, "
            "    attempts = GREATEST(attempts - 1, 0) "
            "WHERE id = %s",
            (PENDING, job_id),
        )


def reap_stale_processing_jobs(conn, stage: str, stale_after_seconds: int = 1200):
    """Recover jobs stuck in `processing` because the worker died mid-flight
    (Lambda timeout, crash, OOM, etc.).

    A job in `processing` for longer than `stale_after_seconds` (default
    20 min — Lambda's 15-min limit + 5 min safety margin) is reclaimed:
      - attempts < MAX_ATTEMPTS → reset to `pending`, the next tick re-claims it
      - attempts >= MAX_ATTEMPTS → marked `failed` with a stuck-state error
        (the claim that timed out already bumped attempts, so chronic
        timeouts on the same tx still hit the failure ceiling)

    Returns (reset_count, failed_count).

    Uses `FOR UPDATE SKIP LOCKED` so a concurrent worker that's still alive
    on the same row won't be disturbed — only truly orphaned rows are touched.
    """
    reset_ids: list = []
    failed_ids: list = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, attempts FROM epr_dedup_jobs "
            "WHERE status = %s "
            "AND stage = %s "
            "AND started_date IS NOT NULL "
            "AND started_date < NOW() - (%s || ' seconds')::interval "
            "FOR UPDATE SKIP LOCKED",
            (PROCESSING, stage, stale_after_seconds),
        )
        rows = cur.fetchall()
        for job_id, attempts in rows:
            if (attempts or 0) >= MAX_ATTEMPTS:
                failed_ids.append(job_id)
            else:
                reset_ids.append(job_id)

        if reset_ids:
            cur.execute(
                "UPDATE epr_dedup_jobs "
                "SET status = %s, started_date = NULL "
                "WHERE id = ANY(%s)",
                (PENDING, reset_ids),
            )
        if failed_ids:
            cur.execute(
                "UPDATE epr_dedup_jobs "
                "SET status = %s, "
                "    last_error = %s, "
                "    completed_date = NOW() "
                "WHERE id = ANY(%s)",
                (FAILED,
                 f"reaped: stuck in processing > {stale_after_seconds}s, "
                 f"attempts exhausted",
                 failed_ids),
            )
    return len(reset_ids), len(failed_ids)


def mark_failed(conn, job_id: int, error_msg: str) -> None:
    """Mark a job failed — but re-queue (status='pending') if attempts < MAX_ATTEMPTS.

    `attempts` was incremented when we claimed the job, so this just decides
    whether the row goes back to 'pending' for another try or stays 'failed'.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_dedup_jobs "
            "SET status = CASE WHEN attempts >= %s THEN %s ELSE %s END, "
            "    last_error = %s, "
            "    completed_date = CASE WHEN attempts >= %s THEN NOW() ELSE NULL END "
            "WHERE id = %s",
            (MAX_ATTEMPTS, FAILED, PENDING, error_msg[:ERROR_MSG_MAX_LEN], MAX_ATTEMPTS, job_id),
        )
