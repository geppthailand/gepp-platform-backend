"""Each surfaced duplicate carries the source transaction id, not just our
internal ids — reviewers look duplicates up in the EPR app by that id."""

from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import (
    _summarize_candidates_for_flags,
)


def _candidate(cid):
    return {"id": cid, "confidence": "high", "matched_document_numbers": ["INV-1"]}


def test_legacy_and_source_ids_are_surfaced():
    out = _summarize_candidates_for_flags(
        [_candidate(727)], {727: (151008, "151008")}
    )
    assert out[0]["id"] == 151008
    assert out[0]["embeded_id"] == 727
    assert out[0]["legacy_id"] == 151008
    assert out[0]["transaction_id"] == "151008"


def test_api_inserted_candidate_keeps_source_id_without_legacy_id():
    out = _summarize_candidates_for_flags(
        [_candidate(746)], {746: (None, "151030")}
    )
    assert out[0]["id"] == 746
    assert out[0]["legacy_id"] is None
    assert out[0]["transaction_id"] == "151030"


def test_missing_row_degrades_to_nulls():
    out = _summarize_candidates_for_flags([_candidate(999)], {})
    assert out[0]["id"] == 999
    assert out[0]["transaction_id"] is None
