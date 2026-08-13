"""Only an exact document_number auto-flags a transaction as a duplicate.

The vendor/date/total triple used to return "high", which auto-flagged every
recurring same-vendor/same-day/same-amount pickup. Guard against it creeping
back up a tier.
"""

from GEPPPlatform.services.cores.epr_ai_audit.cron.duplicates import _confidence


def _signals(doc_numbers=(), identifiers=(), triples=()):
    return {
        "matched_document_numbers": list(doc_numbers),
        "matched_identifiers": list(identifiers),
        "matched_doc_triples": list(triples),
    }


def test_document_number_is_high():
    assert _confidence(_signals(doc_numbers=["INV-001"]), None) == "high"


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
