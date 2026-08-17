"""
LLM-extraction-based duplicate detection for EPR transactions, with a fuzzy
visual_description similarity fallback for close (non-exact) matches.

Signals, in decreasing order of strength:

  1. document_number    — exact match across any image pair (HIGH confidence)
  2. (vendor, date, total) triple — all three match across any image pair (HIGH)
  3. key_identifiers    — set intersection across any image pair (MEDIUM)
  4. description_similarity — cosine on description_embedding via HNSW (MEDIUM-FUZZY
                              if ≥ 0.85; LOW-FUZZY if ≥ 0.70). New in migration 009.

A candidate with no signal at all is omitted. Stronger signals override weaker
ones in the confidence label; weaker signals are still surfaced so callers can
see all reasoning.

Scope: same epr_project_id, excludes self and soft-deleted rows. Format-agnostic
by design — PDFs and images compare against each other via the same JSONB.
"""

import logging
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

PROJECT_SCAN_LIMIT = 200       # max candidates pulled from the same project
DESC_TOP_K = 10                # per-image ANN fetch depth for description similarity
DESC_SIM_MEDIUM_FUZZY = 0.85   # cosine threshold for "medium-fuzzy" confidence
DESC_SIM_LOW_FUZZY = 0.70      # cosine threshold for "low-fuzzy" confidence


def _collect_extractions(rows) -> List[dict]:
    return [r[0] for r in rows if r[0] is not None]


def _identifiers(extraction: dict) -> Set[str]:
    """Union of document_number and key_identifiers, normalized."""
    ids = set()
    dn = extraction.get("document_number")
    if dn:
        ids.add(str(dn).strip())
    for k in extraction.get("key_identifiers") or []:
        if k:
            ids.add(str(k).strip())
    return ids


def _doc_triple(extraction: dict):
    vendor = extraction.get("vendor_name")
    date = extraction.get("document_date")
    total = extraction.get("total_amount")
    if vendor and date and total is not None:
        return (str(vendor).strip().lower(), str(date).strip(), float(total))
    return None


def _exact_signals(target_imgs: List[dict], cand_imgs: List[dict]) -> dict:
    """The original exact-match signals: doc_number, identifier intersection, triple."""
    target_id_sets = [_identifiers(e) for e in target_imgs]
    cand_id_sets = [_identifiers(e) for e in cand_imgs]

    matched_ids = set()
    for ts in target_id_sets:
        for cs in cand_id_sets:
            matched_ids |= ts & cs

    target_doc_nos = {str(e.get("document_number")).strip()
                      for e in target_imgs if e.get("document_number")}
    cand_doc_nos = {str(e.get("document_number")).strip()
                    for e in cand_imgs if e.get("document_number")}
    matched_doc_numbers = target_doc_nos & cand_doc_nos

    target_triples = {t for t in (_doc_triple(e) for e in target_imgs) if t}
    cand_triples = {t for t in (_doc_triple(e) for e in cand_imgs) if t}
    matched_triples = list(target_triples & cand_triples)

    return {
        "matched_document_numbers": sorted(matched_doc_numbers),
        "matched_identifiers": sorted(matched_ids),
        "matched_doc_triples": [list(t) for t in matched_triples],
    }


def _payload_date(raw_date) -> Optional[str]:
    """Calendar day ('YYYY-MM-DD') of a payload transactionDate, or None.

    Payload dates are ISO strings like '2026-06-11T00:00:00.000Z', so the
    first 10 characters are the day. Anything shorter/odd yields None and the
    caller treats the day as unknown."""
    if not raw_date:
        return None
    day = str(raw_date).strip()[:10]
    return day if len(day) == 10 else None


def _confidence(exact: dict, max_desc_sim: Optional[float],
                same_day: bool = True) -> Optional[str]:
    """Translate raw signals into a confidence label, or None if nothing matched.

    HIGH (= auto-flags the transaction) requires an exact document_number match
    AND both transactions landing on the same calendar day. Two things forced
    that pairing:

    - The vendor/date/total triple used to be HIGH on its own, but recurring
      pickups from the same vendor on the same day for the same amount are
      normal here, so it fired constantly on legitimate transactions.
    - document_number alone isn't reliable either: extractors routinely pick up
      a permit/licence number pre-printed on every form, which then looks like
      one document number shared across months of unrelated shipments.

    A genuine double-entry is same-document AND same-day. Everything weaker
    stays at medium — surfaced for review, no auto-flag.

    `same_day` is True when the day is unknown on either side, so a missing
    payload date doesn't silently downgrade a real duplicate.
    """
    if exact["matched_document_numbers"] and same_day:
        return "high"
    if (exact["matched_document_numbers"]
            or exact["matched_doc_triples"]
            or exact["matched_identifiers"]):
        return "medium"
    if max_desc_sim is not None:
        if max_desc_sim >= DESC_SIM_MEDIUM_FUZZY:
            return "medium-fuzzy"
        if max_desc_sim >= DESC_SIM_LOW_FUZZY:
            return "low-fuzzy"
    return None


def _collect_description_similarities(conn, tx_id, target_project_id) -> dict:
    """For each description_embedding the target has, run an HNSW ANN search
    within the same project. Return {candidate_tx_id: max_similarity}.

    Two-step query: first get target's description_embeddings (only ones the
    LLM successfully embedded), then for each run a top-K cosine search."""
    sims_by_tx: dict[int, float] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT description_embedding::text FROM epr_transaction_image "
            "WHERE transaction_id = %s "
            "AND description_embedding IS NOT NULL",
            (tx_id,),
        )
        target_vecs = [r[0] for r in cur.fetchall()]
        if not target_vecs:
            return sims_by_tx

        for vec_literal in target_vecs:
            cur.execute(
                "SELECT i.transaction_id, "
                "       1 - (i.description_embedding <=> %s::vector) AS sim "
                "FROM epr_transaction_image i "
                "JOIN epr_transactions_embeded t ON t.id = i.transaction_id "
                "WHERE i.transaction_id != %s "
                "AND i.description_embedding IS NOT NULL "
                "AND t.deleted_date IS NULL "
                "AND t.epr_project_id = %s "
                "ORDER BY i.description_embedding <=> %s::vector "
                "LIMIT %s",
                (vec_literal, tx_id, target_project_id, vec_literal, DESC_TOP_K),
            )
            for cand_tx_id, sim in cur.fetchall():
                # Keep the max similarity per candidate across all target images.
                prev = sims_by_tx.get(cand_tx_id, 0.0)
                if sim > prev:
                    sims_by_tx[cand_tx_id] = float(sim)
    return sims_by_tx


def find_duplicates(conn, tx_id: int) -> Optional[dict]:
    """Find duplicate + close-match candidates for one transaction.

    Returns None if tx_id doesn't exist or is soft-deleted. Otherwise:
      {
        "transaction_id": int,
        "target_image_count": int,
        "candidates": [
          {
            "id": int,
            "confidence": "high" | "medium" | "medium-fuzzy" | "low-fuzzy",
            "matched_document_numbers": [...],
            "matched_identifiers": [...],
            "matched_doc_triples": [[vendor, date, total], ...],
            "description_similarity": float | None,
          }, ...
        ]
      }
    Candidates without any signal omitted. Sorted by confidence rank, then
    by description_similarity desc.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT epr_project_id, raw_data->>'transactionDate' "
            "FROM epr_transactions_embeded "
            "WHERE id = %s AND deleted_date IS NULL",
            (tx_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        target_project_id = row[0]
        target_day = _payload_date(row[1])
        if target_project_id is None:
            return {"transaction_id": tx_id, "target_image_count": 0, "candidates": []}

        cur.execute(
            "SELECT extracted_data FROM epr_transaction_image "
            "WHERE transaction_id = %s",
            (tx_id,),
        )
        target_imgs = _collect_extractions(cur.fetchall())

        # 1) Exact-match candidate set: the PROJECT_SCAN_LIMIT most recent
        #    txns in the project. Bounded because step 2 loads every one of
        #    their extractions into memory for the Python-side comparison.
        cur.execute(
            "SELECT id FROM epr_transactions_embeded "
            "WHERE id != %s "
            "AND deleted_date IS NULL "
            "AND epr_project_id = %s "
            "ORDER BY id DESC "
            "LIMIT %s",
            (tx_id, target_project_id, PROJECT_SCAN_LIMIT),
        )
        candidate_ids = [r[0] for r in cur.fetchall()]

        # 1b) document_number is the strongest signal (HIGH confidence), so it
        #     gets full-project coverage rather than being capped at the recent
        #     window: an indexed lookup pulls in matches of any age. Cheap —
        #     idx_epr_transaction_image_doc_no serves it directly.
        #     The weaker signals (key_identifiers, vendor/date/total) stay
        #     bounded by the window above; missing an old fuzzy match is
        #     low-stakes, and widening them means an unbounded in-memory scan.
        target_doc_nos = sorted({
            str(e["document_number"]).strip()
            for e in target_imgs
            if e.get("document_number")
        })
        if target_doc_nos:
            # ponytail: matches the stored value as-is. The extractor returns
            # trimmed JSON, so an untrimmed stored doc number would be missed
            # here — btrim() in the predicate would defeat the index. If that
            # ever shows up, index btrim(extracted_data->>'document_number').
            cur.execute(
                "SELECT DISTINCT i.transaction_id "
                "FROM epr_transaction_image i "
                "JOIN epr_transactions_embeded t ON t.id = i.transaction_id "
                "WHERE i.extracted_data->>'document_number' = ANY(%s) "
                "AND i.transaction_id != %s "
                "AND t.deleted_date IS NULL "
                "AND t.epr_project_id = %s",
                (target_doc_nos, tx_id, target_project_id),
            )
            known = set(candidate_ids)
            candidate_ids += [r[0] for r in cur.fetchall() if r[0] not in known]

        # 2) Pull their extracted_data, group by tx.
        extractions_by_tx: dict[int, List[dict]] = {}
        if candidate_ids:
            cur.execute(
                "SELECT transaction_id, extracted_data FROM epr_transaction_image "
                "WHERE transaction_id = ANY(%s) "
                "AND extracted_data IS NOT NULL",
                (candidate_ids,),
            )
            for cand_tx_id, ed in cur.fetchall():
                extractions_by_tx.setdefault(cand_tx_id, []).append(ed)

        # 2b) Payload transaction day per candidate — gates HIGH confidence
        #     (see _confidence). Cheap: one indexed lookup over the same ids.
        day_by_tx: dict[int, Optional[str]] = {}
        if candidate_ids:
            cur.execute(
                "SELECT id, raw_data->>'transactionDate' "
                "FROM epr_transactions_embeded WHERE id = ANY(%s)",
                (candidate_ids,),
            )
            day_by_tx = {r[0]: _payload_date(r[1]) for r in cur.fetchall()}

    # 3) Description-similarity sweep (separate connection scope to keep the
    #    queries small and re-use HNSW per call). Returns max sim per cand tx.
    sims_by_tx = _collect_description_similarities(conn, tx_id, target_project_id)

    # 4) Score every candidate that has either kind of signal. Union of:
    #      - candidates with any extraction overlap with target
    #      - candidates with a non-trivial description_similarity hit
    all_cand_ids = set(extractions_by_tx.keys()) | set(sims_by_tx.keys())

    candidates = []
    for cand_id in all_cand_ids:
        cand_imgs = extractions_by_tx.get(cand_id, [])
        exact = _exact_signals(target_imgs, cand_imgs) if target_imgs and cand_imgs \
                else {"matched_document_numbers": [], "matched_identifiers": [], "matched_doc_triples": []}
        max_sim = sims_by_tx.get(cand_id)
        # Only consider description_similarity if it's above the LOW threshold,
        # else treat it as not a signal at all.
        effective_sim = max_sim if (max_sim is not None and max_sim >= DESC_SIM_LOW_FUZZY) else None

        cand_day = day_by_tx.get(cand_id)
        same_day = (target_day is None or cand_day is None
                    or target_day == cand_day)

        conf = _confidence(exact, effective_sim, same_day=same_day)
        if conf is None:
            continue

        candidates.append({
            "id": cand_id,
            "confidence": conf,
            **exact,
            "same_payload_day": same_day,
            "description_similarity": float(max_sim) if max_sim is not None else None,
        })

    # Rank: high → medium → medium-fuzzy → low-fuzzy. Tie-break by sim desc.
    rank = {"high": 0, "medium": 1, "medium-fuzzy": 2, "low-fuzzy": 3}
    candidates.sort(key=lambda c: (rank[c["confidence"]],
                                   -(c["description_similarity"] or 0.0)))

    return {
        "transaction_id": tx_id,
        "target_image_count": len(target_imgs),
        "candidates": candidates,
    }
