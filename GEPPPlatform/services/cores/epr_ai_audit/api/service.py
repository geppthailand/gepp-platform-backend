"""EPR AI Audit service — embed/list/update transaction handlers.

Ported from gepp-v2-backend (GEPPV2.services.ai_audit.__init__). Uses a
SQLAlchemy session instead of raw psycopg2 but preserves the SQL and the
endpoint semantics.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from GEPPPlatform.libs.exceptions import BadRequestException, NotFoundException
from . import jobs

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


class EprAiAuditService:
    def __init__(self, db: Session):
        self.db = db

    # ── GET /api/epr/ai_audit/transactions ───────────────────────────────────

    def list_transactions(self, query_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Paginated list of active, non-deleted embedded transactions.

        Always filters: is_active = TRUE AND deleted_date IS NULL.
        Optional query params: project_id, status, page (>=1), page_size (1..100).
        """
        qp = query_params or {}
        where_clauses = ["t.is_active = TRUE", "t.deleted_date IS NULL"]
        params: Dict[str, Any] = {}

        project_id_raw = qp.get("project_id")
        if project_id_raw is not None and project_id_raw != "":
            try:
                params["project_id"] = int(project_id_raw)
            except (TypeError, ValueError):
                raise BadRequestException(
                    f"project_id must be an integer, got {project_id_raw!r}"
                )
            where_clauses.append("t.epr_project_id = :project_id")

        status_raw = qp.get("status")
        if status_raw is not None and status_raw != "":
            params["status"] = str(status_raw)
            where_clauses.append("t.status = :status")

        page_raw = qp.get("page")
        if page_raw is None or page_raw == "":
            page = 1
        else:
            try:
                page = int(page_raw)
            except (TypeError, ValueError):
                raise BadRequestException(f"page must be an integer, got {page_raw!r}")
            if page < 1:
                raise BadRequestException(f"page must be >= 1, got {page}")

        page_size_raw = qp.get("page_size")
        if page_size_raw is None or page_size_raw == "":
            page_size = _DEFAULT_PAGE_SIZE
        else:
            try:
                page_size = int(page_size_raw)
            except (TypeError, ValueError):
                raise BadRequestException(
                    f"page_size must be an integer, got {page_size_raw!r}"
                )
            if page_size < 1:
                raise BadRequestException(f"page_size must be >= 1, got {page_size}")
            if page_size > _MAX_PAGE_SIZE:
                raise BadRequestException(
                    f"page_size must be <= {_MAX_PAGE_SIZE}, got {page_size}"
                )

        offset = (page - 1) * page_size
        where_sql = "WHERE " + " AND ".join(where_clauses)

        total = self.db.execute(
            text(f"SELECT COUNT(*) FROM epr_transactions_embeded t {where_sql}"),
            params,
        ).scalar() or 0

        rows = self.db.execute(
            text(
                f"""
                SELECT t.id, t.is_active, t.raw_data, t.epr_project_id,
                       t.ai_score, t.status, t.flags,
                       t.created_date, t.updated_date, t.deleted_date,
                       COUNT(r.id) AS records_count
                FROM epr_transactions_embeded t
                LEFT JOIN epr_transaction_records_embeded r ON r.transaction_id = t.id
                {where_sql}
                GROUP BY t.id
                ORDER BY t.id DESC
                LIMIT :page_size OFFSET :offset
                """
            ),
            {**params, "page_size": page_size, "offset": offset},
        ).fetchall()

        tx_ids = [r[0] for r in rows]
        records_by_tx: Dict[int, List[Dict[str, Any]]] = {}
        if tx_ids:
            rr_rows = self.db.execute(
                text(
                    """
                    SELECT id, transaction_id, is_active, raw_data,
                           ai_score, status, flags,
                           created_date, updated_date, deleted_date
                    FROM epr_transaction_records_embeded
                    WHERE transaction_id = ANY(:tx_ids)
                    AND deleted_date IS NULL
                    ORDER BY id ASC
                    """
                ),
                {"tx_ids": tx_ids},
            ).fetchall()
            for rr in rr_rows:
                records_by_tx.setdefault(rr[1], []).append({
                    "id": rr[0],
                    "is_active": rr[2],
                    "raw_data": rr[3],
                    "ai_score": float(rr[4]) if rr[4] is not None else None,
                    "status": rr[5],
                    "flags": rr[6],
                    "timestamps": _timestamps_obj(rr[7], rr[8], rr[9]),
                })

        transactions = [
            {
                "id": r[0],
                "is_active": r[1],
                "raw_data": r[2],
                "epr_project_id": r[3],
                "ai_score": float(r[4]) if r[4] is not None else None,
                "status": r[5],
                "flags": r[6],
                "timestamps": _timestamps_obj(r[7], r[8], r[9]),
                "records_count": r[10],
                "records": records_by_tx.get(r[0], []),
            }
            for r in rows
        ]
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
            "transactions": transactions,
        }

    # ── POST /api/epr/ai_audit/embed-transaction ─────────────────────────────

    def embed_transaction(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest one EPR transaction: persist parent + records + image rows
        and enqueue a dedup job. Vision-LLM extraction is done later by the
        cron worker (see worker.process_transaction in v2)."""
        if not isinstance(body, dict) or not body:
            raise BadRequestException("POST body must be a non-empty JSON object")

        epr_project_id = body.get("eprProjectId")
        if epr_project_id is None:
            raise BadRequestException("Missing required field: eprProjectId")

        materials = body.get("eprMaterials") or []
        parent_raw = {k: v for k, v in body.items() if k != "eprMaterials"}

        tx_id = self.db.execute(
            text(
                "INSERT INTO epr_transactions_embeded (epr_project_id, raw_data) "
                "VALUES (:project_id, CAST(:raw AS JSONB)) RETURNING id"
            ),
            {"project_id": int(epr_project_id), "raw": json.dumps(parent_raw)},
        ).scalar_one()

        tx_image_ids = [
            self._insert_image_row(
                "epr_transaction_image", "transaction_id", tx_id, img
            )
            for img in (body.get("images") or [])
        ]

        # Same transaction as the inserts above — an enqueue failure rolls back
        # the whole thing.
        jobs.enqueue_job(self.db, tx_id, jobs.STAGE_EMBEDDING)

        record_ids: List[int] = []
        record_image_ids: List[List[int]] = []
        for material in materials:
            rid = self.db.execute(
                text(
                    "INSERT INTO epr_transaction_records_embeded "
                    "(transaction_id, raw_data) "
                    "VALUES (:tx_id, CAST(:raw AS JSONB)) RETURNING id"
                ),
                {"tx_id": tx_id, "raw": json.dumps(material)},
            ).scalar_one()
            record_ids.append(rid)
            record_image_ids.append([
                self._insert_image_row(
                    "epr_transaction_record_image",
                    "epr_transaction_record_id",
                    rid,
                    img,
                )
                for img in (material.get("images") or [])
            ])

        self.db.commit()

        return {
            "status": "ingested",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "transaction": {"db_id": tx_id, "image_ids": tx_image_ids},
            "records": [
                {"db_id": rid, "image_ids": riids}
                for rid, riids in zip(record_ids, record_image_ids)
            ],
        }

    # ── PUT /api/epr/ai_audit/embed-transaction/{source_id} ──────────────────

    def update_transaction(self, source_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Replace an existing transaction's payload (keyed by SOURCE id) and
        re-trigger dedup.

        `source_id` is the caller's transaction id — the same value that arrived
        in `body["id"]` on the original POST and is now stored in
        `raw_data->>'id'`. NOT our internal BIGSERIAL.
        """
        if not isinstance(body, dict) or not body:
            raise BadRequestException("PUT body must be a non-empty JSON object")

        epr_project_id = body.get("eprProjectId")
        if epr_project_id is None:
            raise BadRequestException("Missing required field: eprProjectId")

        materials = body.get("eprMaterials") or []
        parent_raw = {k: v for k, v in body.items() if k != "eprMaterials"}

        row = self.db.execute(
            text(
                "SELECT id FROM epr_transactions_embeded "
                "WHERE raw_data->>'id' = :source_id AND deleted_date IS NULL "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"source_id": str(source_id)},
        ).fetchone()
        if row is None:
            raise NotFoundException(
                f"Transaction with source id {source_id!r} not found"
            )
        tx_id = row[0]

        self.db.execute(
            text(
                "UPDATE epr_transactions_embeded "
                "SET raw_data = CAST(:raw AS JSONB), "
                "    epr_project_id = :project_id, "
                "    updated_date = NOW() "
                "WHERE id = :id"
            ),
            {"raw": json.dumps(parent_raw), "project_id": int(epr_project_id), "id": tx_id},
        )

        # Wipe children so we can re-insert from the new payload.
        # CASCADE on epr_transaction_records_embeded handles its images.
        self.db.execute(
            text("DELETE FROM epr_transaction_image WHERE transaction_id = :id"),
            {"id": tx_id},
        )
        self.db.execute(
            text(
                "DELETE FROM epr_transaction_records_embeded WHERE transaction_id = :id"
            ),
            {"id": tx_id},
        )

        tx_image_ids = [
            self._insert_image_row(
                "epr_transaction_image", "transaction_id", tx_id, img
            )
            for img in (body.get("images") or [])
        ]

        jobs.enqueue_job(self.db, tx_id, jobs.STAGE_EMBEDDING)

        record_ids: List[int] = []
        record_image_ids: List[List[int]] = []
        for material in materials:
            rid = self.db.execute(
                text(
                    "INSERT INTO epr_transaction_records_embeded "
                    "(transaction_id, raw_data) "
                    "VALUES (:tx_id, CAST(:raw AS JSONB)) RETURNING id"
                ),
                {"tx_id": tx_id, "raw": json.dumps(material)},
            ).scalar_one()
            record_ids.append(rid)
            record_image_ids.append([
                self._insert_image_row(
                    "epr_transaction_record_image",
                    "epr_transaction_record_id",
                    rid,
                    img,
                )
                for img in (material.get("images") or [])
            ])

        self.db.commit()

        return {
            "status": "updated",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "transaction": {"db_id": tx_id, "image_ids": tx_image_ids},
            "records": [
                {"db_id": rid, "image_ids": riids}
                for rid, riids in zip(record_ids, record_image_ids)
            ],
        }

    # ── PATCH /api/epr/ai_audit/transactions/{source_id}/status ──────────────

    _AUDIT_DECISIONS = ("approved", "rejected")

    def update_status(self, source_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Audit decision: mark a transaction as `approved` or `rejected`.

        Keyed by the caller's SOURCE id (the `id` field on the original POST
        payload, stored in `raw_data->>'id'`) — same convention as the PUT
        endpoint. If multiple rows share that source id, the most recent
        (highest BIGSERIAL) wins.

        Missing rows are a no-op — returns `{"found": false}` with 200 instead
        of raising 404. Callers can treat audit decisions as fire-and-forget
        without first checking the row exists.

        Preserves the prior status under `flags.review.prior_status` so the
        original AI verdict (`flagged` / `passed` / `skipped`) isn't lost.
        An optional `note` field is recorded under `flags.review.note`.
        """
        if not isinstance(body, dict):
            raise BadRequestException("PATCH body must be a JSON object")

        new_status = body.get("status")
        if new_status not in self._AUDIT_DECISIONS:
            raise BadRequestException(
                f"status must be one of {list(self._AUDIT_DECISIONS)}, got {new_status!r}"
            )

        row = self.db.execute(
            text(
                "SELECT id, status, flags FROM epr_transactions_embeded "
                "WHERE raw_data->>'id' = :source_id AND deleted_date IS NULL "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"source_id": str(source_id)},
        ).fetchone()
        if row is None:
            # No-op — the source id doesn't (yet) map to an embedded transaction.
            # Likely the embed-transaction POST never ran for this id, or it
            # was soft-deleted. Either way, fire-and-forget: return success so
            # the caller doesn't have to special-case it.
            return {
                "found": False,
                "source_id": str(source_id),
                "status": new_status,
            }
        tx_id, prior_status, prior_flags = row

        decided_at = datetime.now(timezone.utc).isoformat()
        review_block = {
            "prior_status": prior_status,
            "decided_at": decided_at,
        }
        note = body.get("note")
        if note:
            review_block["note"] = str(note)

        merged = dict(prior_flags or {})
        merged["review"] = review_block

        self.db.execute(
            text(
                "UPDATE epr_transactions_embeded "
                "SET status = :status, "
                "    flags = CAST(:flags AS JSONB), "
                "    updated_date = NOW() "
                "WHERE id = :id"
            ),
            {"status": new_status, "flags": json.dumps(merged), "id": tx_id},
        )
        self.db.commit()

        return {
            "found": True,
            "source_id": str(source_id),
            "id": tx_id,
            "status": new_status,
            "prior_status": prior_status,
            "decided_at": decided_at,
            "note": review_block.get("note"),
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _insert_image_row(self, table: str, fk_column: str, fk_value: int, img: Dict[str, Any]) -> int:
        """Persist one image entry from the inbound payload — fast, no LLM calls.

        Only basic columns are populated here. `extracted_data` and
        `description_embedding` are left NULL and filled later by the cron
        worker (see worker.process_transaction in gepp-v2-backend).

        `table` and `fk_column` are hardcoded literals from the caller — not
        user input — so f-string interpolation is safe.
        """
        type_obj = img.get("type") or {}
        type_name = type_obj.get("name") if isinstance(type_obj, dict) else None
        type_id_raw = type_obj.get("id") if isinstance(type_obj, dict) else None
        try:
            type_id = int(type_id_raw) if type_id_raw is not None else None
        except (TypeError, ValueError):
            type_id = None

        return self.db.execute(
            text(
                f"INSERT INTO {table} "
                f"({fk_column}, is_active, name, image_url, type, type_id) "
                "VALUES (:fk, :is_active, :name, :url, :type, :type_id) "
                "RETURNING id"
            ),
            {
                "fk": fk_value,
                "is_active": img.get("isActive", True),
                "name": img.get("name"),
                "url": img.get("imageURL"),
                "type": type_name,
                "type_id": type_id,
            },
        ).scalar_one()


def _timestamps_obj(created, updated, deleted) -> Dict[str, Any]:
    return {
        "created_date": created.isoformat() if created else None,
        "updated_date": updated.isoformat() if updated else None,
        "deleted_date": deleted.isoformat() if deleted else None,
    }
