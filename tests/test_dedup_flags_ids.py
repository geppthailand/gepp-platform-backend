"""The audit list resolves each duplicate's source transaction id at read
time, so rows deduped before this existed carry it too."""

from GEPPPlatform.services.cores.epr_ai_audit.api.service import (
    _with_dup_transaction_ids,
)


def test_source_ids_are_attached_by_embeded_id():
    flags = {
        "dedup_at": "x",
        "duplicates": [
            {"id": 746, "embeded_id": 746, "legacy_id": None},
            {"id": 151008, "embeded_id": 727, "legacy_id": 151008},
            {"id": 999, "embeded_id": 999, "legacy_id": None},  # row gone
        ],
    }
    out = _with_dup_transaction_ids(flags, {746: "151030", 727: "151008"})
    assert [d["transaction_id"] for d in out["duplicates"]] == [
        "151030", "151008", None,
    ]
    assert out["dedup_at"] == "x"


def test_flags_without_duplicates_pass_through():
    assert _with_dup_transaction_ids(None, {}) is None
    assert _with_dup_transaction_ids({"duplicates": []}, {}) == {"duplicates": []}
