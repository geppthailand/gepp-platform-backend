"""Queue helpers for the epr_dedup_jobs table (SQLAlchemy port).

Ported from gepp-v2-backend (GEPPV2.services.ai_audit.jobs) — same semantics,
but works against a SQLAlchemy Session instead of a raw psycopg2 connection.
"""

import json
import logging
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

STAGE_EMBEDDING = "embedding"
STAGE_DEDUP_DONE = "dedup_done"

PENDING = "pending"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"

MAX_ATTEMPTS = 3
ERROR_MSG_MAX_LEN = 2000


def enqueue_job(db, transaction_id: int, stage: str) -> None:
    """Insert a pending job for (transaction_id, stage). Idempotent."""
    db.execute(
        text(
            "INSERT INTO epr_dedup_jobs (transaction_id, stage) "
            "VALUES (:tx_id, :stage) "
            "ON CONFLICT (transaction_id, stage) DO NOTHING"
        ),
        {"tx_id": transaction_id, "stage": stage},
    )


def claim_next_jobs(db, stage: str, batch_size: int = 10):
    """Claim up to `batch_size` pending jobs for `stage`, marking them 'processing'.

    Uses FOR UPDATE SKIP LOCKED so parallel workers won't grab the same rows.
    Returns: list of (job_id, transaction_id) tuples.
    """
    result = db.execute(
        text(
            "UPDATE epr_dedup_jobs "
            "SET status = :proc, "
            "    started_date = NOW(), "
            "    attempts = attempts + 1 "
            "WHERE id IN ("
            "  SELECT id FROM epr_dedup_jobs "
            "  WHERE status = :pending AND stage = :stage "
            "  ORDER BY created_date "
            "  LIMIT :batch_size "
            "  FOR UPDATE SKIP LOCKED"
            ") "
            "RETURNING id, transaction_id"
        ),
        {"proc": PROCESSING, "pending": PENDING, "stage": stage, "batch_size": batch_size},
    )
    return result.fetchall()


def mark_done(db, job_id: int, result: dict, new_stage: Optional[str] = None) -> None:
    """Mark a job done and store its result. If `new_stage` is given, also
    relabel the stage column."""
    if new_stage is not None:
        db.execute(
            text(
                "UPDATE epr_dedup_jobs "
                "SET status = :done, result = CAST(:result AS JSONB), "
                "    completed_date = NOW(), stage = :stage "
                "WHERE id = :id"
            ),
            {"done": DONE, "result": json.dumps(result), "stage": new_stage, "id": job_id},
        )
    else:
        db.execute(
            text(
                "UPDATE epr_dedup_jobs "
                "SET status = :done, result = CAST(:result AS JSONB), "
                "    completed_date = NOW() "
                "WHERE id = :id"
            ),
            {"done": DONE, "result": json.dumps(result), "id": job_id},
        )


def release_job(db, job_id: int) -> None:
    """Send a claimed job back to 'pending' without bumping the attempts counter."""
    db.execute(
        text(
            "UPDATE epr_dedup_jobs "
            "SET status = :pending, "
            "    started_date = NULL, "
            "    attempts = GREATEST(attempts - 1, 0) "
            "WHERE id = :id"
        ),
        {"pending": PENDING, "id": job_id},
    )


def mark_failed(db, job_id: int, error_msg: str) -> None:
    """Mark a job failed — but re-queue (status='pending') if attempts < MAX_ATTEMPTS."""
    db.execute(
        text(
            "UPDATE epr_dedup_jobs "
            "SET status = CASE WHEN attempts >= :max THEN :failed ELSE :pending END, "
            "    last_error = :err, "
            "    completed_date = CASE WHEN attempts >= :max THEN NOW() ELSE NULL END "
            "WHERE id = :id"
        ),
        {
            "max": MAX_ATTEMPTS,
            "failed": FAILED,
            "pending": PENDING,
            "err": (error_msg or "")[:ERROR_MSG_MAX_LEN],
            "id": job_id,
        },
    )
