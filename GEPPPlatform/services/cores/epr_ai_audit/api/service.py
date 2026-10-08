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
# Each audit carries full raw_data plus every image extraction, so a response
# is large. Bounded for the same reason page_size is.
_MAX_AUDIT_IDS = 50


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

        # Filter by the LEGACY transaction id — the numeric id the transaction
        # has in the legacy database. Imported rows carry it at
        # raw_data->>'_legacy_id'; rows posted live through the API carry the
        # caller's own id at raw_data->>'id'. Match either, so one filter works
        # whichever way a transaction arrived.
        #
        # `epr_transactions_embeded.id` is this table's own key and means
        # nothing to a caller — that one is for /{id}/audit.
        transaction_id_raw = qp.get("transaction_id")
        if transaction_id_raw is not None and transaction_id_raw != "":
            ids = [v.strip() for v in str(transaction_id_raw).split(",") if v.strip()]
            if not ids:
                raise BadRequestException("transaction_id must not be blank")
            bad = [v for v in ids if not v.lstrip("-").isdigit()]
            if bad:
                raise BadRequestException(
                    f"transaction_id must be numeric, got {', '.join(bad)}"
                )
            params["transaction_ids"] = ids
            where_clauses.append(
                "(t.raw_data->>'_legacy_id' = ANY(:transaction_ids) "
                "OR t.raw_data->>'id' = ANY(:transaction_ids))"
            )

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

        dup_ids = {
            d.get("embeded_id")
            for r in rows
            for d in ((r[6] or {}).get("duplicates") or [])
            if d.get("embeded_id") is not None
        }
        dup_source_ids: Dict[int, Any] = {}
        if dup_ids:
            dup_source_ids = dict(
                self.db.execute(
                    text(
                        "SELECT id, raw_data->>'id' FROM epr_transactions_embeded "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": list(dup_ids)},
                ).fetchall()
            )

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
                # The id a caller knows this transaction by: the legacy one if
                # it was imported, otherwise whatever the POST carried. Same
                # precedence the dedup flags use.
                "transaction_id": _source_id(r[2]),
                "is_active": r[1],
                "raw_data": r[2],
                "epr_project_id": r[3],
                "ai_score": float(r[4]) if r[4] is not None else None,
                "status": r[5],
                "flags": _with_dup_transaction_ids(r[6], dup_source_ids),
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

    # ── GET /api/epr/ai_audit/transactions/{id}/audit ────────────────────────

    def get_transaction_audit(self, transaction_id: Any) -> Dict[str, Any]:
        """One or more transactions with every field, and why each check
        passed, failed or could not be verified.

        Keyed by `epr_transactions_embeded.id` — the `id` the list endpoint
        returns. Several ids comma-separated:

            /transactions/553/audit
            /transactions/553,552,551/audit

        Always returns a list, so a caller does not have to branch on how many
        it asked for. Ids that do not exist come back under `not_found` rather
        than failing the whole request — one bad id in a batch should not cost
        the other nine.

        Every query here is set-based. Looping per id would turn a page of ten
        into forty round trips.
        """
        raw = [v.strip() for v in str(transaction_id).split(",") if v.strip()]
        if not raw:
            raise BadRequestException("transaction id must not be blank")
        bad = [v for v in raw if not v.lstrip("-").isdigit()]
        if bad:
            raise BadRequestException(
                f"transaction id must be an integer, got {', '.join(bad)}"
            )
        if len(raw) > _MAX_AUDIT_IDS:
            raise BadRequestException(
                f"at most {_MAX_AUDIT_IDS} ids per request, got {len(raw)}"
            )
        # De-duplicated, original order preserved so the response lines up with
        # what was asked for.
        ids, seen = [], set()
        for v in (int(x) for x in raw):
            if v not in seen:
                seen.add(v); ids.append(v)

        rows = self.db.execute(
            text("""
                SELECT id, is_active, raw_data, epr_project_id, ai_score,
                       status, flags, created_date, updated_date, deleted_date
                FROM epr_transactions_embeded WHERE id = ANY(:ids)
            """),
            {"ids": ids},
        ).fetchall()
        by_id = {r[0]: r for r in rows}

        # Duplicates across every requested transaction, resolved in one go.
        dup_ids = [
            d.get("embeded_id")
            for r in rows
            for d in ((r[6] or {}).get("duplicates") or [])
            if d.get("embeded_id") is not None
        ]
        dup_source_ids = {}
        if dup_ids:
            dup_source_ids = dict(
                self.db.execute(
                    text("SELECT id, raw_data FROM epr_transactions_embeded "
                         "WHERE id = ANY(:ids)"),
                    {"ids": list(set(dup_ids))},
                ).fetchall()
            )
            dup_source_ids = {k: _source_id(v) for k, v in dup_source_ids.items()}

        records_by_tx: Dict[int, List[Dict[str, Any]]] = {}
        for r in self.db.execute(
            text("""
                SELECT id, transaction_id, is_active, raw_data, ai_score,
                       status, flags, created_date, updated_date, deleted_date
                FROM epr_transaction_records_embeded
                WHERE transaction_id = ANY(:ids) AND deleted_date IS NULL
                ORDER BY id ASC
            """),
            {"ids": ids},
        ).fetchall():
            records_by_tx.setdefault(r[1], []).append({
                "id": r[0],
                "is_active": r[2],
                "raw_data": r[3],
                "ai_score": _num(r[4]),
                "status": r[5],
                "flags": r[6],
                "audit": _audit_view(r[6] or {}, r[3]),
                "timestamps": _timestamps_obj(r[7], r[8], r[9]),
                "images": [],
            })

        # The images and what the vision model read off each one. For rows
        # deduped before `confirmations` existed, a pass carries only the field
        # name — but THIS is what it was judged against, and it was never
        # thrown away. A reviewer can see for themselves rather than being
        # told to trust an unexplained pass.
        images_by_tx: Dict[int, List[Dict[str, Any]]] = {}
        for i in self.db.execute(
            text("""
                SELECT transaction_id, id, name, image_url, type,
                       NULL::bigint AS record_id, extracted_data
                FROM epr_transaction_image
                WHERE transaction_id = ANY(:ids) AND deleted_date IS NULL
                UNION ALL
                SELECT r.transaction_id, ri.id, ri.name, ri.image_url, ri.type,
                       ri.epr_transaction_record_id, ri.extracted_data
                FROM epr_transaction_record_image ri
                JOIN epr_transaction_records_embeded r
                  ON r.id = ri.epr_transaction_record_id
                WHERE r.transaction_id = ANY(:ids) AND ri.deleted_date IS NULL
                ORDER BY 1, 6 NULLS FIRST, 2
            """),
            {"ids": ids},
        ).fetchall():
            images_by_tx.setdefault(i[0], []).append({
                "id": i[1],
                "name": i[2],
                "image_url": i[3],
                "type": i[4],
                "record_id": i[5],
                "extracted_data": i[6],
                "extracted": i[6] is not None,
            })

        results = []
        for tx_id in ids:
            row = by_id.get(tx_id)
            if row is None:
                continue
            flags = row[6] or {}
            dups = flags.get("duplicates") or []
            records = records_by_tx.get(tx_id, [])
            images = images_by_tx.get(tx_id, [])
            for rec in records:
                rec["images"] = [im for im in images if im["record_id"] == rec["id"]]

            results.append({
                "transaction": {
                    "id": row[0],
                    "transaction_id": _source_id(row[2]),
                    "source_id": _source_id(row[2]),      # kept: same value
                    "is_active": row[1],
                    "raw_data": row[2],
                    "epr_project_id": row[3],
                    "ai_score": _num(row[4]),
                    "status": row[5],
                    "flags": _with_dup_transaction_ids(flags, dup_source_ids),
                    "timestamps": _timestamps_obj(row[7], row[8], row[9]),
                },
                "records": records,
                "records_count": len(records),
                "images": [im for im in images if im["record_id"] is None],
                "audit": {
                    **_audit_view(flags, row[2]),
                    "duplicates": [
                        {**d, "transaction_id": dup_source_ids.get(d.get("embeded_id"))}
                        for d in dups
                    ],
                    "reason": flags.get("reason"),
                    "dedup_at": flags.get("dedup_at"),
                },
            })

        return {
            "results": results,
            "count": len(results),
            # Asked for but not in the database. Not an error — a batch should
            # not fail because one id is stale.
            "not_found": [i for i in ids if i not in by_id],
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


def _with_dup_transaction_ids(flags, source_ids) -> Optional[Dict[str, Any]]:
    """Add each duplicate's source transaction id (`raw_data->>'id'`) to
    `flags.duplicates[]`. Resolved at read time from `embeded_id`, so rows
    deduped before this existed are covered without a backfill."""
    dups = (flags or {}).get("duplicates")
    if not dups:
        return flags
    return {
        **flags,
        "duplicates": [
            {**d, "transaction_id": source_ids.get(d.get("embeded_id"))}
            for d in dups
        ],
    }


def _source_id(raw_data) -> Optional[Any]:
    """The id a caller knows this transaction by.

    Imported rows carry the legacy database's numeric id at `_legacy_id`; rows
    posted live through the API carry the caller's own `id`. The dedup flags
    already prefer the legacy one, so this matches.
    """
    raw = raw_data or {}
    legacy = raw.get("_legacy_id")
    return legacy if legacy is not None else raw.get("id")


# Payload keys the integrity judge actually examines, mapped to the name it
# reports them under. Everything else a caller submits is never compared
# against a document — see _NOT_CHECKED_REASONS.
_JUDGED_FIELDS = {
    "transactionDate": "transactionDate",
    "totalQuantity": "totalQuantity",
    "totalPrice": "totalPrice",
    # Records store the per-unit price as `price` and the quantity under
    # several legacy names; worker._payload_for_integrity coalesces them.
    "price": "pricePerUnit",
    "pricePerUnit": "pricePerUnit",
    "quantity": "totalQuantity",
    "weight": "totalQuantity",
    "materialWeight": "totalQuantity",
    "kgQuantity": "totalQuantity",
    "unitPrice": "pricePerUnit",
}

# Why a submitted field is not compared against the documents. A field with no
# entry here falls back to the generic line.
_NOT_CHECKED_REASONS = {
    "invoiceNo": {
        "en": "Not verified: this is freeform text on the transaction and "
              "rarely matches the reference numbers printed on record-level "
              "documents, so checking it produces more noise than signal.",
        "th": "ไม่ได้ตรวจสอบ: เป็นข้อความที่ผู้ใช้กรอกเอง และมักไม่ตรงกับ "
              "เลขที่เอกสารที่พิมพ์บนไฟล์แนบ",
    },
}
_NOT_CHECKED_DEFAULT = {
    "en": "Not verified against any document — no check is defined for this field.",
    "th": "ไม่ได้ตรวจสอบกับเอกสาร — ยังไม่มีการตรวจสอบสำหรับข้อมูลนี้",
}

# Structural keys in raw_data that are not user-entered values.
_NOT_A_FIELD = {
    "id", "_legacy_id", "_source", "_extraction_complete", "isActive",
    "status", "images", "materials", "auditHistory", "timestamps",
    "timestamp", "organization", "originBusinessUnit", "destinationBusinessUnit",
    "conditions", "material", "actionBy", "deviceLog", "coordinate", "journey",
}


# The judge reports four canonical names; a caller submitted something else.
# worker._payload_for_integrity coalesces in this order, so the first key
# present in raw_data is the one that supplied the value. Mirrored here rather
# than threaded through the worker: resolving at read time means rows deduped
# before this existed get their original names too, with no re-run.
_CANONICAL_SOURCES = {
    "totalQuantity": ("totalQuantity", "quantity", "weight", "materialWeight",
                      "kgQuantity"),
    "pricePerUnit": ("price", "pricePerUnit", "unitPrice"),
    "totalPrice": ("totalPrice",),
    "transactionDate": ("transactionDate",),
}


def _payload_field(canonical: str, raw_data: Any) -> Optional[str]:
    """The key the CALLER actually submitted for this canonical field.

    A record sends `price`; the verdict comes back as `pricePerUnit`. Showing
    only the canonical name leaves a reviewer matching up two vocabularies by
    eye. None when the field is not one of the remapped four (imageType is the
    judge's own, not a payload key).
    """
    raw = raw_data or {}
    for key in _CANONICAL_SOURCES.get(canonical, ()):
        v = raw.get(key)
        if v is not None and v != "":
            return key
    return None


def _label(entry: Dict[str, Any], raw_data: Any) -> Dict[str, Any]:
    """Add the submitted key alongside the canonical one."""
    submitted = _payload_field(entry.get("field"), raw_data)
    return {**entry, "payload_field": submitted or entry.get("field")}


def _not_checked(raw_data: Any, judged: set) -> List[Dict[str, Any]]:
    """Every submitted field that no check looks at.

    Without this a reviewer sees four verdicts and cannot tell whether the
    other fifteen fields passed silently or were never examined. They were
    never examined — say so per field rather than leaving a gap.
    """
    out = []
    for k, v in (raw_data or {}).items():
        if k in _NOT_A_FIELD or isinstance(v, (dict, list)):
            continue
        if _JUDGED_FIELDS.get(k) in judged:
            continue
        out.append({
            "field": k,
            "payload_field": k,          # not remapped: never judged
            "payload_value": v,
            "image_indicates": None,
            "explanation": _NOT_CHECKED_REASONS.get(k, _NOT_CHECKED_DEFAULT),
        })
    return sorted(out, key=lambda f: f["field"])


def _audit_view(flags: Dict[str, Any], raw_data: Any = None) -> Dict[str, Any]:
    """Unpack flags.integrity into the two questions a reviewer asks.

    `matched_fields` is a bare list of field names — the evidence confirmed
    these. `issues` are objects carrying the payload value, what the image
    showed instead, and a bilingual explanation. Both were already written;
    neither was ever served.
    """
    integrity = flags.get("integrity") or {}
    issues = integrity.get("issues") or []
    matched = integrity.get("matched_fields") or []

    # `confirmations` carries the same detail for a pass that `issues` does for
    # a failure. Rows deduped before it existed have only the field names, so
    # those fall back to the name alone rather than inventing a reason.
    by_field = {c.get("field"): c for c in (integrity.get("confirmations") or [])}
    passed = []
    for f in matched:
        c = by_field.get(f)
        passed.append({
            "field": f,
            "payload_field": _payload_field(f, raw_data) or f,
            "payload_value": c.get("payload_value") if c else None,
            "image_indicates": c.get("image_indicates") if c else None,
            "explanation": (c.get("explanation") or {}) if c else {},
            # False for anything checked before confirmations were recorded —
            # the pass is real, the reasoning was simply never kept.
            "explained": bool(c),
        })

    judged = ({f for f in matched}
              | {i.get("field") for i in issues}
              | {u.get("field") for u in (integrity.get("unverified") or [])})
    not_checked = _not_checked(raw_data, judged)

    return {
        "checked_at": integrity.get("checked_at"),
        "checked_image_count": integrity.get("checked_image_count", 0),
        "skipped": bool(integrity.get("skipped")),
        # Why it passed: what was submitted, what the image showed, in en/th.
        "passed": passed,
        # Why it failed: each carries both sides and an explanation in en/th.
        "failed": [
            {
                "field": i.get("field"),
                "payload_field": _payload_field(i.get("field"), raw_data) or i.get("field"),
                "payload_value": i.get("payload_value"),
                "image_indicates": i.get("image_indicates"),
                "explanation": i.get("explanation") or {},
                # Which file produced this verdict, so the UI can link it.
                "image_id": i.get("image_id"),
                "image_type": i.get("image_type"),
                "image_name": i.get("image_name"),
                "source_image_url": i.get("source_image_url"),
                "record_id": i.get("record_id"),
            }
            for i in issues
        ],
        # Submitted and examined, but the image had nothing to check it
        # against. Not a pass and not a failure — an unanswered question.
        "unverified": [_label(u, raw_data)
                       for u in (integrity.get("unverified") or [])],
        # Submitted but never examined — no check exists for these.
        "not_checked": not_checked,
        # Extraction or model errors — not a verdict on the data.
        "errors": integrity.get("errors") or [],
        "passed_count": len(matched),
        "failed_count": len(issues),
        "unverified_count": len(integrity.get("unverified") or []),
        "not_checked_count": len(not_checked),
    }


def _num(v) -> Optional[float]:
    """DECIMAL comes back as Decimal, which json.dumps refuses."""
    return float(v) if v is not None else None


def _enum_value(v) -> Optional[str]:
    """Status columns are Enums on some rows and plain strings on others."""
    return getattr(v, "value", v) if v is not None else None


def _timestamps_obj(created, updated, deleted) -> Dict[str, Any]:
    return {
        "created_date": created.isoformat() if created else None,
        "updated_date": updated.isoformat() if updated else None,
        "deleted_date": deleted.isoformat() if deleted else None,
    }
