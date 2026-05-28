"""
Per-project legacy import from the MySQL Gepp_new DB into our Postgres.
Picks a RANDOM sample of legacy transactions (capped by
LEGACY_IMPORT_MAX_PER_PROJECT) so each project has a representative dedup
comparison set without re-importing the entire history.

Public entry point: `ensure_imported(legacy_conn, conn, project_id)`.
Returns ('complete', count) once the project's import is fully done
(cap hit OR legacy source exhausted), or ('in_progress', count) when more
chunks remain. The caller (worker) decides what to do with each status.

Sampling: `_fetch_legacy_chunk` does `ORDER BY RAND() LIMIT n` against the
legacy `transactions` table, excluding any ids already in our DB (looked up
via `raw_data->>'_legacy_id'` on `epr_transactions_embeded`). So:
  - Re-running the import never re-picks an already-imported row.
  - The same project may end up with a different random sample if you reset
    its `epr_project_import_state` row and re-run.

Resumability: each legacy transaction's import (parent row + image rows
+ inline LLM extraction) is committed before the next is picked. If the
cron Lambda crashes mid-import, the next tick re-queries for un-imported
rows and continues. `last_imported_legacy_id` is kept for observability
only — it's no longer used to drive selection.

Scope:
  - parent-level only (transactions + transaction_images)
  - record-level images (epr_transaction_records / epr_transaction_record_images)
    are skipped at MVP; add a second loop here when needed.

Marker: imported rows get is_active=FALSE to distinguish them from
API-inserted rows. Downstream queries filter on `deleted_date IS NULL`
rather than is_active so legacy rows still surface as dedup candidates.
"""

import logging
import os
from typing import Optional, Tuple

from psycopg2.extras import Json

from . import worker

logger = logging.getLogger(__name__)

CHUNK_SIZE = 10  # legacy transactions per ensure_imported call

# Default cap on the number of legacy transactions imported per project.
# Overridable via the LEGACY_IMPORT_MAX_PER_PROJECT env var. Set to 0 to
# disable the cap and import the full history. The cap is enforced against
# `epr_project_import_state.imported_count`, so increasing the env var on a
# running project simply unlocks more chunks on subsequent ticks.
MAX_PER_PROJECT_DEFAULT = 5


def _max_per_project() -> int:
    """Read the per-project import cap from the LEGACY_IMPORT_MAX_PER_PROJECT
    env var, falling back to MAX_PER_PROJECT_DEFAULT. Returns 0 to mean
    'no cap' (import the full legacy history)."""
    raw = os.environ.get("LEGACY_IMPORT_MAX_PER_PROJECT")
    if raw is None or raw == "":
        return MAX_PER_PROJECT_DEFAULT
    try:
        v = int(raw)
        return max(0, v)
    except ValueError:
        logger.warning(
            "LEGACY_IMPORT_MAX_PER_PROJECT=%r is not an integer, using default %d",
            raw, MAX_PER_PROJECT_DEFAULT,
        )
        return MAX_PER_PROJECT_DEFAULT


def _get_state(conn, project_id):
    """Return (status, last_imported_legacy_id, imported_count) for the
    project, or None if no state row exists yet. Uses FOR UPDATE so
    concurrent callers serialize."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, last_imported_legacy_id, imported_count "
            "FROM epr_project_import_state "
            "WHERE epr_project_id = %s "
            "FOR UPDATE",
            (project_id,),
        )
        return cur.fetchone()


def _init_state(conn, project_id):
    """Create the state row if it doesn't exist. Idempotent (ON CONFLICT)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO epr_project_import_state (epr_project_id) "
            "VALUES (%s) ON CONFLICT (epr_project_id) DO NOTHING",
            (project_id,),
        )


# How long a partially-imported legacy tx must sit untouched before the
# cleanup pass deletes it. Default 1200s (20 min) matches the job reaper's
# threshold (Lambda's 15-min timeout + 5-min safety margin) so a worker
# that's still mid-import won't have its rows ripped out from under it.
PARTIAL_IMPORT_STALE_SECONDS = 1200


def _cleanup_partial_imports(conn, project_id: int, stale_after_seconds: int = PARTIAL_IMPORT_STALE_SECONDS):
    """Delete legacy-imported transactions for this project whose extraction
    loop never finished — i.e., the parent row is present but raw_data lacks
    the `_extraction_complete: true` marker AND the row hasn't been updated
    in `stale_after_seconds`.

    Catches the failure mode: Lambda dies mid-extraction of legacy tx N → tx N
    has its parent + image rows inserted, some extracted_data still NULL, no
    completion marker. Without this sweep, the random sampler permanently
    skips tx N (because the parent IS in our DB) and its missing extractions
    never get filled. With this sweep, the row gets removed and the random
    sampler is free to re-pick it on the next chunk fetch.

    Cascade on `epr_transactions_embeded` handles dependent image rows.

    Returns the count of cleaned-up parent rows.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM epr_transactions_embeded "
            "WHERE epr_project_id = %s "
            "AND raw_data ? '_legacy_id' "
            "AND COALESCE(raw_data->>'_extraction_complete', 'false') != 'true' "
            "AND updated_date < NOW() - (%s || ' seconds')::interval "
            "RETURNING id",
            (project_id, stale_after_seconds),
        )
        cleaned = cur.fetchall()
    return len(cleaned)


def _resync_imported_count(conn, project_id: int) -> None:
    """Recompute `imported_count` in state from the actual number of
    legacy-tagged rows in our DB. Called after `_cleanup_partial_imports`
    so the cap check uses the real number, not a stale one inflated by
    rows we just deleted."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_project_import_state s "
            "SET imported_count = ("
            "  SELECT COUNT(*) FROM epr_transactions_embeded t "
            "  WHERE t.epr_project_id = s.epr_project_id "
            "  AND t.raw_data ? '_legacy_id' "
            "), "
            "updated_at = NOW() "
            "WHERE s.epr_project_id = %s",
            (project_id,),
        )


def _already_imported_legacy_ids(conn, project_id: int) -> set:
    """Return the set of legacy_ids we've already imported into our DB for
    this project, read from `raw_data->>'_legacy_id'`. Used to filter
    random samples so we don't re-pick the same rows."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT (raw_data->>'_legacy_id')::bigint "
            "FROM epr_transactions_embeded "
            "WHERE epr_project_id = %s "
            "AND raw_data ? '_legacy_id'",
            (project_id,),
        )
        return {r[0] for r in cur.fetchall()}


def _fetch_legacy_chunk(legacy_conn, project_id: int, exclude_ids: set, limit: int):
    """SELECT a RANDOM chunk of legacy transactions for this project,
    excluding any ids in `exclude_ids` (already imported into our DB).

    Uses `ORDER BY RAND() LIMIT n`. MySQL has to score every candidate row,
    so this is O(N) per query — fine for projects with up to ~100k legacy
    txs. Run on much larger tables, swap to a seeded-pick strategy.

    Returns list of (legacy_tx_id, raw_dict).
    """
    sql = (
        "SELECT id, invoice_no, note, total_quantity, transaction_date, "
        "       status, epr_project_id, is_active, "
        "       created_date, updated_date, deleted_date "
        "FROM transactions "
        "WHERE epr_project_id = %s "
        "AND deleted_date IS NULL "
    )
    params: list = [project_id]
    if exclude_ids:
        # IN-list of already-imported ids. psycopg2/mysql.connector
        # accept a tuple for IN; build it inline so empty set is a no-op.
        placeholders = ",".join(["%s"] * len(exclude_ids))
        sql += f"AND id NOT IN ({placeholders}) "
        params.extend(sorted(exclude_ids))
    sql += "ORDER BY RAND() LIMIT %s"
    params.append(limit)

    with legacy_conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

    out = []
    for r in rows:
        legacy_id, invoice_no, note, total_quantity, transaction_date, \
            status, epr_project_id, is_active, \
            created_date, updated_date, deleted_date = r
        raw = {
            "_legacy_id": legacy_id,
            "_source": "legacy_import",
            "invoiceNo": invoice_no,
            "note": note,
            "totalQuantity": float(total_quantity) if total_quantity is not None else None,
            "transactionDate": transaction_date.isoformat() if transaction_date else None,
            "status": status,
            "eprProjectId": epr_project_id,
            "isActive": bool(is_active),
            "createdDate": created_date.isoformat() if created_date else None,
            "updatedDate": updated_date.isoformat() if updated_date else None,
            "deletedDate": deleted_date.isoformat() if deleted_date else None,
        }
        out.append((legacy_id, raw))
    return out


def _fetch_legacy_images(legacy_conn, legacy_tx_id: int):
    """Fetch images for one legacy transaction, joined with image-type id+name.

    Returns list of dicts shaped like our API payload's `images[]` entries so
    we can reuse the same field-mapping pattern. Includes the type id so it
    flows through to our DB and surfaces in integrity-check flags.
    """
    with legacy_conn.cursor() as cur:
        cur.execute(
            "SELECT i.id, i.name, i.image_url, i.is_active, "
            "       i.is_cache, i.created_date, "
            "       t.id AS type_id, t.name AS type_name "
            "FROM transaction_images i "
            "LEFT JOIN transaction_image_types t ON t.id = i.type "
            "WHERE i.transaction_id = %s "
            "AND i.deleted_date IS NULL "
            "ORDER BY i.id ASC",
            (legacy_tx_id,),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        type_obj = None
        if r[6] is not None or r[7]:
            type_obj = {}
            if r[6] is not None:
                type_obj["id"] = str(r[6])
            if r[7]:
                type_obj["name"] = r[7]
        out.append({
            "id": str(r[0]),
            "name": r[1],
            "imageURL": r[2],
            # User's rule: imported rows are is_active=FALSE in our DB regardless
            # of their legacy is_active value.
            "isActive": False,
            "isCache": bool(r[4]) if r[4] is not None else False,
            "type": type_obj,
        })
    return out


def _import_one_legacy_tx(legacy_conn, conn, project_id, legacy_tx_id, raw):
    """Import one legacy transaction: insert parent + images, then run inline
    LLM extraction. Commits the inserts first so the per-image UPDATEs (via
    worker._update_image) operate on durable rows.

    Returns the new tx_id (or None if no images survived insertion).
    """
    images = _fetch_legacy_images(legacy_conn, legacy_tx_id)

    with conn.cursor() as cur:
        # Parent row, marked is_active=FALSE per the import convention.
        cur.execute(
            "INSERT INTO epr_transactions_embeded "
            "(epr_project_id, is_active, raw_data) "
            "VALUES (%s, FALSE, %s) RETURNING id",
            (int(project_id), Json(raw)),
        )
        new_tx_id = cur.fetchone()[0]

        # Image rows (raw fields only, extracted_data NULL — filled by next step).
        image_ids = []
        for img in images:
            type_obj = img.get("type") or {}
            type_name = type_obj.get("name") if isinstance(type_obj, dict) else None
            cur.execute(
                "INSERT INTO epr_transaction_image "
                "(transaction_id, is_active, name, image_url, type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (new_tx_id, img.get("isActive", False),
                 img.get("name"), img.get("imageURL"), type_name),
            )
            image_ids.append((cur.fetchone()[0], img.get("imageURL")))
    conn.commit()  # parent + images durable before we run slow LLM calls

    # Inline LLM extraction + description embedding per image. Each call
    # commits independently inside worker._update_image, so partial progress
    # survives a crash.
    for img_id, image_url in image_ids:
        if image_url:
            worker._update_image(conn, "epr_transaction_image", img_id, image_url)

    # All images extracted (or attempted, fail-soft). Stamp the parent row
    # with `_extraction_complete = true` so the partial-cleanup scan knows
    # this tx is fully imported and shouldn't be deleted. If the worker died
    # before reaching this point, the marker is absent and the row gets
    # swept on the next tick (after the stale threshold).
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_transactions_embeded "
            "SET raw_data = raw_data || '{\"_extraction_complete\": true}'::jsonb, "
            "    updated_date = NOW() "
            "WHERE id = %s",
            (new_tx_id,),
        )
    conn.commit()

    return new_tx_id


def _advance_checkpoint(conn, project_id, last_imported_legacy_id, count_delta):
    """Bump the state row's checkpoint after one legacy tx is fully imported."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_project_import_state "
            "SET last_imported_legacy_id = %s, "
            "    imported_count = imported_count + %s, "
            "    updated_at = NOW() "
            "WHERE epr_project_id = %s",
            (last_imported_legacy_id, count_delta, project_id),
        )
    conn.commit()


def _mark_complete(conn, project_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_project_import_state "
            "SET status = 'complete', completed_at = NOW(), updated_at = NOW() "
            "WHERE epr_project_id = %s",
            (project_id,),
        )
    conn.commit()


def ensure_imported(
    legacy_conn,
    conn,
    project_id: int,
    chunk_size: int = CHUNK_SIZE,
    max_per_project: Optional[int] = None,
) -> Tuple[str, int]:
    """Drive one chunk of legacy import for `project_id`. Idempotent + resumable.

    `max_per_project` caps how many legacy transactions we ever import for
    this project. None = read from LEGACY_IMPORT_MAX_PER_PROJECT env var
    (default MAX_PER_PROJECT_DEFAULT). 0 = no cap (import the full history).
    The check runs against `imported_count` in state, so raising the cap on
    a project that previously hit it simply unlocks more chunks next tick.

    Returns ('complete', count) when the project's import is done — either
    because we ran out of legacy rows OR because we hit the cap. Returns
    ('in_progress', count) when more chunks remain on subsequent cron ticks.

    Per-tx checkpoint commits make this safe under crashes: re-running picks
    up from `last_imported_legacy_id` without re-importing anything.
    """
    _init_state(conn, project_id)

    # Sweep partially-imported legacy txs (Lambda died mid-extraction last
    # time around). Deleting them frees their `_legacy_id` so the random
    # sampler can re-pick the same tx and start fresh. Stale threshold
    # protects a currently-running parallel worker.
    cleaned = _cleanup_partial_imports(conn, project_id)
    if cleaned:
        # The state row's imported_count is now stale (we just deleted N
        # rows it was counting). Sync it back to the actual count so the
        # cap check below isn't fooled by ghost imports.
        _resync_imported_count(conn, project_id)
        logger.info(
            "legacy import for project_id=%s: cleaned %d partial(s), resynced count",
            project_id, cleaned,
        )
    conn.commit()

    state = _get_state(conn, project_id)
    if state is None:
        # Should not happen after _init_state, but defensive
        return ("in_progress", 0)
    status, last_id, imported_count = state
    if status == "complete":
        return ("complete", 0)

    cap = _max_per_project() if max_per_project is None else max(0, int(max_per_project))
    if cap > 0:
        remaining = cap - (imported_count or 0)
        if remaining <= 0:
            # Already at/over the cap — mark complete so future ticks skip
            # this project entirely.
            _mark_complete(conn, project_id)
            logger.info(
                "legacy import for project_id=%s already at cap (%d/%d), marking complete",
                project_id, imported_count, cap,
            )
            return ("complete", 0)
        effective_chunk = min(chunk_size, remaining)
    else:
        effective_chunk = chunk_size

    # Random sampling — pick `effective_chunk` legacy txs NOT yet in our DB.
    # No monotonic checkpoint; resumability is "anything already imported is
    # excluded from the next random pick."
    already_imported = _already_imported_legacy_ids(conn, project_id)
    chunk = _fetch_legacy_chunk(legacy_conn, project_id, already_imported, effective_chunk)
    if not chunk:
        # Nothing left in legacy that we haven't imported — done.
        _mark_complete(conn, project_id)
        return ("complete", 0)

    imported = 0
    for legacy_tx_id, raw in chunk:
        try:
            _import_one_legacy_tx(legacy_conn, conn, project_id, legacy_tx_id, raw)
            # `last_imported_legacy_id` no longer drives selection (we use the
            # excluded-set instead), but we still bump it for observability —
            # it's the id of the most recent tx we touched.
            _advance_checkpoint(conn, project_id, legacy_tx_id, 1)
            imported += 1
        except Exception as exc:
            conn.rollback()
            logger.warning(
                "legacy import failed for project_id=%s legacy_tx_id=%s: %s — "
                "leaving checkpoint as-is for retry",
                project_id, legacy_tx_id, exc,
            )
            raise

    # Done if (a) we hit the cap, or (b) the legacy source has no more
    # un-imported rows (chunk smaller than requested = exhausted).
    new_count = (imported_count or 0) + imported
    if cap > 0 and new_count >= cap:
        _mark_complete(conn, project_id)
        logger.info(
            "legacy import for project_id=%s reached cap (%d/%d), marking complete",
            project_id, new_count, cap,
        )
        return ("complete", imported)
    if len(chunk) < effective_chunk:
        _mark_complete(conn, project_id)
        return ("complete", imported)
    return ("in_progress", imported)
