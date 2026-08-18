"""Auto-flagging a duplicate takes an exact document_number AND the same day.

Two separate false-positive sources are pinned here:
  - the vendor/date/total triple, which fires on ordinary recurring pickups
  - a permit/licence number pre-printed on every form, which the extractor
    reads as document_number and which then matches across months of
    unrelated shipments
"""

from GEPPPlatform.services.cores.epr_ai_audit.cron.duplicates import (
    _confidence, _payload_date,
)


def _signals(doc_numbers=(), identifiers=(), triples=()):
    return {
        "matched_document_numbers": list(doc_numbers),
        "matched_identifiers": list(identifiers),
        "matched_doc_triples": list(triples),
    }


def test_document_number_same_day_is_high():
    assert _confidence(_signals(doc_numbers=["INV-001"]), None) == "high"


def test_document_number_different_day_does_not_auto_flag():
    # The real case: one permit number (MY0220260617...) shared by four
    # shipments on 06-09, 06-10, 06-11 and 05-06.
    assert _confidence(
        _signals(doc_numbers=["MY02202606170001281680"]), None, same_day=False,
    ) == "medium"


def test_unknown_day_still_auto_flags():
    # A missing payload date must not silently downgrade a real duplicate —
    # find_duplicates passes same_day=True when either side is unknown.
    assert _confidence(_signals(doc_numbers=["INV-001"]), None, same_day=True) == "high"


def test_payload_date_takes_the_calendar_day():
    assert _payload_date("2026-06-11T00:00:00.000Z") == "2026-06-11"
    assert _payload_date(None) is None
    assert _payload_date("") is None
    assert _payload_date("2026-06") is None


def test_doc_triple_alone_does_not_auto_flag():
    triple = [["acme co", "2026-08-13", 3070.0]]
    assert _confidence(_signals(triples=triple), None) == "medium"


def test_shared_tax_ids_alone_do_not_auto_flag():
    assert _confidence(_signals(identifiers=["3812081724"]), None) == "medium"


def test_near_identical_photos_alone_do_not_auto_flag():
    assert _confidence(_signals(), 0.9661736520154616) == "medium-fuzzy"


def test_no_signal_is_none():
    assert _confidence(_signals(), None) is None
    assert _confidence(_signals(), 0.5) is None
