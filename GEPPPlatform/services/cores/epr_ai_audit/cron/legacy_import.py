"""
Per-project legacy import from the MySQL Gepp_new DB into our Postgres.
Builds each project's dedup **comparison corpus** by sampling legacy
transactions according to the project's `epr_project_ai_audit_setting` row
(legacy MySQL). Imported rows are comparison-only — they are NOT themselves
audited (no dedup job is enqueued for them).

Public entry point: `ensure_imported(legacy_conn, conn, project_id)`.
Returns ('complete', count) once nothing more needs importing this tick
(sample target reached, legacy source exhausted, or no sampling configured),
or ('in_progress', count) when more chunks remain. The caller (worker)
decides what to do with each status.

Sampling modes (read fresh from the setting on EVERY call — see
`_get_sampling_setting`):
  - `interval` — import ALL legacy txs whose `created_date` falls in
    [interval_start, interval_end] that aren't already imported. `sample_amount`
    is ignored. Missing either bound → import nothing.
  - `latest`   — top up to `sample_amount` rows with the newest-by-created_date
    legacy txs not already imported. If we already have ≥ sample_amount, no-op.
  - `random`   — same as latest but `ORDER BY RAND()`.
  - no row / unrecognized type / missing required params → import nothing.

The selection always excludes already-imported ids and only ever ADDS rows
(never removes), so a changed setting self-heals on the next tick: switching
type or params simply tops up the missing rows without duplicating existing
ones. Because the setting is re-read every call, there is no stored
"applied setting" — the live legacy data + current imported set are the only
inputs.

Resumability: each legacy transaction's import (parent row + image rows
+ inline LLM extraction) is committed before the next is picked. If the
cron Lambda crashes mid-import, the next tick re-queries for un-imported
rows and continues. `last_imported_legacy_id` is kept for observability
only — it's no longer used to drive selection. `epr_project_import_state`
is used for partial-import cleanup, counts, and observability only — its
`status` no longer gates whether a project is re-checked.

Scope:
  - parent-level only (transactions + transaction_images)
  - record-level images (epr_transaction_records / epr_transaction_record_images)
    are skipped at MVP; add a second loop here when needed.

Marker: imported rows get is_active=FALSE to distinguish them from
API-inserted rows. Downstream queries filter on `deleted_date IS NULL`
rather than is_active so legacy rows still surface as dedup candidates.
"""

import logging
from typing import Optional, Tuple

from psycopg2.extras import Json

from . import worker

logger = logging.getLogger(__name__)

CHUNK_SIZE = 10  # legacy transactions per ensure_imported call

# Recognized sampling strategies in `epr_project_ai_audit_setting.type`.
SAMPLE_TYPE_INTERVAL = "interval"
SAMPLE_TYPE_LATEST = "latest"
SAMPLE_TYPE_RANDOM = "random"
_VALID_SAMPLE_TYPES = (SAMPLE_TYPE_INTERVAL, SAMPLE_TYPE_LATEST, SAMPLE_TYPE_RANDOM)


def _get_sampling_setting(legacy_conn, project_id: int) -> Optional[dict]:
    """Read the project's AI-audit sampling config from legacy MySQL.

    Returns {type, sample_amount, interval_start, interval_end} with `type`
    lowercased/stripped (None if blank), or None when there is no setting row
    for the project. Callers validate `type` against `_VALID_SAMPLE_TYPES` and
    check that the params each mode needs are present.
    """
    with legacy_conn.cursor() as cur:
        cur.execute(
            "SELECT type, sample_amount, interval_start, interval_end "
            "FROM epr_project_ai_audit_setting "
            "WHERE epr_project_id = %s",
            (project_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    s_type, sample_amount, interval_start, interval_end = row
    return {
        "type": (str(s_type).strip().lower() or None) if s_type is not None else None,
        "sample_amount": sample_amount,
        "interval_start": interval_start,
        "interval_end": interval_end,
    }


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
    so the sample-size check uses the real number, not a stale one inflated
    by rows we just deleted."""
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
    this project, read from `raw_data->>'_legacy_id'`. Used both as the
    exclude-set (so no mode re-picks the same row) and as the current sample
    size for the latest/random count target."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT (raw_data->>'_legacy_id')::bigint "
            "FROM epr_transactions_embeded "
            "WHERE epr_project_id = %s "
            "AND raw_data ? '_legacy_id'",
            (project_id,),
        )
        return {r[0] for r in cur.fetchall()}


# Columns selected for every legacy-transaction chunk, in the order
# `_row_to_raw` unpacks them. Kept as one constant so the three sampling
# selectors stay in lock-step.
_LEGACY_TX_COLUMNS = (
    "id, invoice_no, note, total_quantity, transaction_date, "
    "status, epr_project_id, is_active, "
    "created_date, updated_date, deleted_date"
)


def _row_to_raw(r):
    """Map one legacy `transactions` row (in `_LEGACY_TX_COLUMNS` order) to
    (legacy_tx_id, raw_dict) shaped like our API payload's transaction."""
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
    return legacy_id, raw


def _fetch_chunk(legacy_conn, project_id, exclude_ids, limit,
                 *, extra_where="", extra_params=(), order_by="RAND()"):
    """SELECT a chunk of non-deleted legacy transactions for this project,
    excluding any ids in `exclude_ids` (already imported into our DB).

    `order_by` / `extra_where` are supplied only from this module's own
    constants (never user input), so the f-string interpolation is safe.
    `ORDER BY RAND()` makes MySQL score every candidate row — O(N) per query,
    fine up to ~100k legacy txs per project. Returns list of (legacy_tx_id, raw).
    """
    sql = (
        f"SELECT {_LEGACY_TX_COLUMNS} "
        "FROM transactions "
        "WHERE epr_project_id = %s "
        "AND deleted_date IS NULL "
    )
    params: list = [project_id]
    if extra_where:
        sql += extra_where + " "
        params.extend(extra_params)
    if exclude_ids:
        # IN-list of already-imported ids. mysql.connector accepts a tuple
        # for IN; build it inline so the empty set is a no-op.
        placeholders = ",".join(["%s"] * len(exclude_ids))
        sql += f"AND id NOT IN ({placeholders}) "
        params.extend(sorted(exclude_ids))
    sql += f"ORDER BY {order_by} LIMIT %s"
    params.append(limit)

    with legacy_conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_raw(r) for r in rows]


def _fetch_random_chunk(legacy_conn, project_id: int, exclude_ids: set, limit: int):
    """`random` mode — a random chunk not already imported."""
    return _fetch_chunk(legacy_conn, project_id, exclude_ids, limit, order_by="RAND()")


def _fetch_latest_chunk(legacy_conn, project_id: int, exclude_ids: set, limit: int):
    """`latest` mode — newest-by-created_date chunk not already imported."""
    return _fetch_chunk(legacy_conn, project_id, exclude_ids, limit,
                        order_by="created_date DESC")


def _fetch_interval_chunk(legacy_conn, project_id: int, exclude_ids: set,
                          start, end, limit: int):
    """`interval` mode — chunk within [start, end] by created_date, oldest
    first, not already imported."""
    return _fetch_chunk(
        legacy_conn, project_id, exclude_ids, limit,
        extra_where="AND created_date >= %s AND created_date <= %s",
        extra_params=(start, end),
        order_by="created_date ASC",
    )


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
) -> Tuple[str, int]:
    """Drive one chunk of legacy import for `project_id`. Idempotent + resumable.

    The sampling strategy is read fresh from `epr_project_ai_audit_setting`
    (legacy MySQL) on every call — see the module docstring for the three
    modes. Selection always excludes already-imported ids and only ever adds
    rows, so a changed setting self-heals by topping up; nothing is removed and
    nothing is duplicated. There is no permanent "complete" short-circuit — a
    project is re-evaluated against the live legacy data each tick.

    Returns ('complete', count) when nothing more needs importing this tick
    (target reached, source exhausted, or no/invalid sampling config), or
    ('in_progress', count) when more chunks remain on subsequent cron ticks.

    Per-tx checkpoint commits make this safe under crashes: re-running excludes
    anything already imported without re-importing it.
    """
    _init_state(conn, project_id)

    # Sweep partially-imported legacy txs (Lambda died mid-extraction last
    # time around). Deleting them frees their `_legacy_id` so the sampler can
    # re-pick the same tx and start fresh. Stale threshold protects a
    # currently-running parallel worker.
    cleaned = _cleanup_partial_imports(conn, project_id)
    if cleaned:
        # The state row's imported_count is now stale (we just deleted N rows
        # it was counting). Sync it back to the actual count.
        _resync_imported_count(conn, project_id)
        logger.info(
            "legacy import for project_id=%s: cleaned %d partial(s), resynced count",
            project_id, cleaned,
        )
    conn.commit()

    # Sampling config drives selection. No row / unrecognized type → import
    # nothing (there is no env-var random fallback anymore).
    setting = _get_sampling_setting(legacy_conn, project_id)
    if setting is None or setting["type"] not in _VALID_SAMPLE_TYPES:
        logger.info(
            "legacy import for project_id=%s: no valid sampling config (%s), skipping",
            project_id, (setting or {}).get("type"),
        )
        return ("complete", 0)
    s_type = setting["type"]

    # `already` doubles as both the exclude-set and the current sample size.
    already = _already_imported_legacy_ids(conn, project_id)
    have = len(already)

    if s_type == SAMPLE_TYPE_INTERVAL:
        start, end = setting["interval_start"], setting["interval_end"]
        if start is None or end is None:
            logger.info(
                "legacy import for project_id=%s: interval type but bounds missing "
                "(start=%s end=%s), skipping",
                project_id, start, end,
            )
            return ("complete", 0)
        effective_chunk = chunk_size  # no count target — import the whole window
        chunk = _fetch_interval_chunk(
            legacy_conn, project_id, already, start, end, effective_chunk,
        )
    else:
        amount = setting["sample_amount"]
        if amount is None or amount <= 0:
            logger.info(
                "legacy import for project_id=%s: %s type but sample_amount missing/<=0 (%s), skipping",
                project_id, s_type, amount,
            )
            return ("complete", 0)
        needed = amount - have
        if needed <= 0:
            # Already at/over target — nothing to do (covers interval→latest/
            # random where `have` is already large).
            return ("complete", 0)
        effective_chunk = min(chunk_size, needed)
        if s_type == SAMPLE_TYPE_LATEST:
            chunk = _fetch_latest_chunk(legacy_conn, project_id, already, effective_chunk)
        else:  # SAMPLE_TYPE_RANDOM
            chunk = _fetch_random_chunk(legacy_conn, project_id, already, effective_chunk)

    if not chunk:
        # Nothing left in legacy matching the strategy that we haven't imported.
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

    # A short chunk means the source is exhausted for this strategy → done.
    # For latest/random, also done once we've reached the target amount.
    if len(chunk) < effective_chunk:
        _mark_complete(conn, project_id)
        return ("complete", imported)
    if s_type != SAMPLE_TYPE_INTERVAL and (have + imported) >= setting["sample_amount"]:
        _mark_complete(conn, project_id)
        return ("complete", imported)
    return ("in_progress", imported)
