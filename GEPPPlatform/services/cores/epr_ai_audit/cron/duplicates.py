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


def _confidence(exact: dict, max_desc_sim: Optional[float]) -> Optional[str]:
    """Translate raw signals into a confidence label, or None if nothing matched."""
    if exact["matched_document_numbers"] or exact["matched_doc_triples"]:
        return "high"
    if exact["matched_identifiers"]:
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
            "SELECT epr_project_id FROM epr_transactions_embeded "
            "WHERE id = %s AND deleted_date IS NULL",
            (tx_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        target_project_id = row[0]
        if target_project_id is None:
            return {"transaction_id": tx_id, "target_image_count": 0, "candidates": []}

        cur.execute(
            "SELECT extracted_data FROM epr_transaction_image "
            "WHERE transaction_id = %s",
            (tx_id,),
        )
        target_imgs = _collect_extractions(cur.fetchall())

        # 1) Exact-match candidate set: pull other txns in the project.
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

        conf = _confidence(exact, effective_sim)
        if conf is None:
            continue

        candidates.append({
            "id": cand_id,
            "confidence": conf,
            **exact,
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
