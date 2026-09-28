"""Async OCR jobs — start one, poll it, run it.

Reading a stack of documents takes 20-45s. API Gateway HTTP APIs cut the
connection at 30s and that limit cannot be raised, so the synchronous endpoint
returned 503 on anything but a small upload even though the Lambda had
succeeded. Making the model think less halves the latency but costs 13 points
of accuracy, so the wait is real and the API has to stop pretending otherwise.

Flow:

    POST /ocr/jobs  -> create_job()  writes a row, COMMITS, self-invokes -> {job_id}
    (second invocation)              run_job() does the OCR, writes the result
    GET  /ocr/jobs/{id} -> get_job() returns status, and result once done

A second invocation of this same Lambda is the whole mechanism: no queue, no
worker, no new infrastructure, and a 600s budget instead of 30.
"""

import json
import logging
import os
import secrets
from typing import Any, Dict, List, Optional

import boto3
from sqlalchemy import text

logger = logging.getLogger(__name__)

PENDING = "pending"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"

KIND_TRANSACTION = "transaction"
KIND_AUDIT = "audit"

# The event key the entry point watches for. Anything with this set is a
# self-invocation, not an HTTP request, and is routed before main() touches
# requestContext — which a self-invoke event does not have.
ASYNC_TASK = "epr_ocr_job"

ERROR_MAX_LEN = 2000


# ── create ─────────────────────────────────────────────────────────────────

def create_job(db, files: List[str], fields: List[Dict],
               kind: str = KIND_TRANSACTION) -> Dict[str, Any]:
    """Write a pending job, commit it, then hand it to a second invocation.

    The COMMIT before dispatch is load-bearing: the other invocation opens its
    own session and would not see an uncommitted row.
    """
    job_id = "ocr_" + secrets.token_hex(16)
    db.execute(
        text("INSERT INTO epr_ocr_jobs (id, kind, status, request) "
             "VALUES (:id, :kind, :status, CAST(:request AS JSONB))"),
        {"id": job_id, "kind": kind, "status": PENDING,
         "request": json.dumps({"files": files, "fields": fields})},
    )
    db.commit()

    try:
        _dispatch(job_id)
    except Exception as exc:
        # A job nobody is running would sit at 'pending' until the caller's
        # 2-minute timeout, with nothing saying why. Fail it now, loudly.
        logger.exception("OCR job %s: dispatch failed", job_id)
        fail_job(db, job_id, f"could not start the job: {type(exc).__name__}: {exc}")
        return {"job_id": job_id, "status": FAILED,
                "error": "could not start the job"}

    return {"job_id": job_id, "status": PENDING}


def _dispatch(job_id: str) -> None:
    """Invoke this same Lambda again, without waiting for it."""
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        raise RuntimeError(
            "AWS_LAMBDA_FUNCTION_NAME is not set — async OCR only works inside Lambda"
        )
    boto3.client("lambda").invoke(
        FunctionName=function_name,
        InvocationType="Event",          # fire and forget
        Payload=json.dumps({"async_task": ASYNC_TASK, "job_id": job_id}).encode(),
    )
    logger.info("OCR job %s: dispatched to %s", job_id, function_name)


# ── read ───────────────────────────────────────────────────────────────────

def get_job(db, job_id: str) -> Optional[Dict[str, Any]]:
    """Job state for the poller. None if there is no such job."""
    row = db.execute(
        text("SELECT id, kind, status, result, error FROM epr_ocr_jobs WHERE id = :id"),
        {"id": job_id},
    ).fetchone()
    if row is None:
        return None
    return {
        "job_id": row[0],
        "kind": row[1],
        "status": row[2],
        "result": row[3],
        "error": row[4],
    }


# ── write ──────────────────────────────────────────────────────────────────

def finish_job(db, job_id: str, result: Dict[str, Any]) -> None:
    db.execute(
        text("UPDATE epr_ocr_jobs SET status = :status, "
             "result = CAST(:result AS JSONB), completed_date = NOW() "
             "WHERE id = :id"),
        {"status": DONE, "result": json.dumps(result, default=str), "id": job_id},
    )
    db.commit()


def fail_job(db, job_id: str, error: str) -> None:
    db.execute(
        text("UPDATE epr_ocr_jobs SET status = :status, error = :error, "
             "completed_date = NOW() WHERE id = :id"),
        {"status": FAILED, "error": (error or "")[:ERROR_MAX_LEN], "id": job_id},
    )
    db.commit()


# ── run (second invocation) ────────────────────────────────────────────────

def run_job(job_id: str) -> Dict[str, Any]:
    """Do the OCR for one job. Called by the self-invocation, not by HTTP.

    Opens its own session — the request that created the job is long gone.
    Every failure is written to the row: an exception that only reached the
    Lambda logs would leave the caller polling a job stuck at 'processing'.
    """
    from GEPPPlatform.libs.database import get_session
    from .ocr import read_audit, read_transaction

    with get_session() as db:
        row = db.execute(
            text("SELECT kind, status, request FROM epr_ocr_jobs WHERE id = :id"),
            {"id": job_id},
        ).fetchone()
        if row is None:
            logger.error("OCR job %s: no such job", job_id)
            return {"job_id": job_id, "status": "missing"}

        kind, status, request = row[0], row[1], row[2]
        if status != PENDING:
            # Lambda retries an async invocation on failure, so this can be a
            # second delivery of the same event. Do not redo paid work.
            logger.warning("OCR job %s: already %s, skipping", job_id, status)
            return {"job_id": job_id, "status": status}

        db.execute(
            text("UPDATE epr_ocr_jobs SET status = :status, started_date = NOW() "
                 "WHERE id = :id"),
            {"status": PROCESSING, "id": job_id},
        )
        db.commit()

        try:
            reader = read_audit if kind == KIND_AUDIT else read_transaction
            result = reader(request.get("files") or [], request.get("fields") or [])
        except Exception as exc:
            logger.exception("OCR job %s: failed", job_id)
            fail_job(db, job_id, f"{type(exc).__name__}: {exc}")
            return {"job_id": job_id, "status": FAILED}

        finish_job(db, job_id, result)
        logger.info("OCR job %s: done", job_id)
        return {"job_id": job_id, "status": DONE}
