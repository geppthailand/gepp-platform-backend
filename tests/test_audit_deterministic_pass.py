"""The deterministic pass, and where unreadable evidence ends up.

Two things must hold:
  - a column the machine can settle never reaches the LLM
  - an unreadable REQUIRED field goes to a person, not to 'rejected'
"""

import pytest

from GEPPPlatform.prompts.ai_audit_v1.default.scripts import integrity as I
from GEPPPlatform.prompts.ai_audit_v1.default.scripts.audit_scripts import (
    REVIEW_UNREADABLE,
    _deterministic_pass,
)

TICKET_SPEC = {
    "date": "Transaction date",
    "materials": {"material_name": "m", "weight_kg": "w", "price_per_unit": "p", "total": "t"},
}
PHOTO_SPEC = {"waste_type": "t", "contamination": "c"}

TICKET = {
    "file_id": 1,
    "extract_list": TICKET_SPEC,
    "extracted_data": {
        "date": "2025-08-25",
        "materials": [{"material_name": "PET", "weight_kg": "925",
                       "price_per_unit": "27.00", "total": "24975.00"}],
    },
}
BLANK_TICKET = {"file_id": 2, "extract_list": TICKET_SPEC, "extracted_data": {}}
PHOTO = {"file_id": 3, "extract_list": PHOTO_SPEC, "extracted_data": {"waste_type": "plastic"}}

RECORD = {"record_id": 1, "origin_weight_kg": 925.0, "origin_price_per_unit": 27.0,
          "total_amount": 24975.0, "transaction_date": "2025-08-25"}

COLS = ["origin_weight_kg", "total_amount", "material_id"]


def _fresh(cols=COLS):
    return {c: {"match": False, "found": False, "error": None} for c in cols}


def test_machine_checkable_columns_never_reach_the_llm():
    checklist = _fresh()
    settled = _deterministic_pass(COLS, [RECORD], [TICKET], checklist)
    assert settled == {"origin_weight_kg", "total_amount"}
    assert checklist["origin_weight_kg"]["match"] is True
    assert checklist["origin_weight_kg"]["source"] == "deterministic"
    # names are fuzzy — still the LLM's job
    assert "material_id" not in settled


def test_a_real_mismatch_is_settled_without_the_llm():
    checklist = _fresh()
    bad = {**RECORD, "origin_weight_kg": 800.0}
    settled = _deterministic_pass(COLS, [bad], [TICKET], checklist)
    assert "origin_weight_kg" in settled
    assert checklist["origin_weight_kg"]["match"] is False
    assert checklist["origin_weight_kg"]["found"] is True      # evidence exists
    assert checklist["origin_weight_kg"]["outcome"] == I.MISMATCH
    assert checklist["origin_weight_kg"]["error"]              # a Thai message


def test_unreadable_is_not_settled_but_is_recorded():
    checklist = _fresh()
    settled = _deterministic_pass(COLS, [RECORD], [BLANK_TICKET], checklist)
    # not settled: the LLM still gets a chance at it
    assert "origin_weight_kg" not in settled
    # but the reason is remembered, so the final decision can route to review
    assert checklist["origin_weight_kg"]["outcome"] == I.UNREADABLE
    assert checklist["origin_weight_kg"]["match"] is False


def test_a_photo_alone_is_not_expected_to_carry_a_weight():
    checklist = _fresh()
    settled = _deterministic_pass(COLS, [RECORD], [PHOTO], checklist)
    assert "origin_weight_kg" not in settled
    assert checklist["origin_weight_kg"]["outcome"] == I.NOT_EXPECTED


def test_every_record_must_be_backed_not_just_one():
    checklist = _fresh()
    other = {**RECORD, "record_id": 2, "origin_weight_kg": 555.0}
    settled = _deterministic_pass(COLS, [RECORD, other], [TICKET], checklist)
    # record 2's weight is not on the ticket -> the column cannot pass
    assert checklist["origin_weight_kg"]["match"] is False
    assert checklist["origin_weight_kg"]["outcome"] == I.MISMATCH


def test_a_column_absent_from_the_record_is_left_alone():
    checklist = _fresh(["origin_quantity"])
    settled = _deterministic_pass(["origin_quantity"], [RECORD], [TICKET], checklist)
    assert settled == set()
    assert checklist["origin_quantity"] == {"match": False, "found": False, "error": None}


def test_review_is_the_default_for_unreadable():
    # a blurry photo is not fraud; flipping this constant restores the old
    # behaviour of rejecting outright
    assert REVIEW_UNREADABLE is True
