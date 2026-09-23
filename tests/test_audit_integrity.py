"""Deterministic integrity checks, and the four outcomes.

The point of the four outcomes is that "the photo was too blurry" and "the
numbers disagree" used to be the same result. Most of these tests exist to keep
them apart.
"""

import pytest

from GEPPPlatform.prompts.ai_audit_v1.default.scripts import integrity as I

# Real extract_lists, from the seeded ai_audit_document_types.
WEIGHT_TICKET = {
    "ticket_number": "Ticket or reference number",
    "date": "Transaction date (YYYY-MM-DD)",
    "buyer_name": "Buyer name",
    "materials": {
        "material_name": "Material sub-type",
        "weight_kg": "Net weight in kg",
        "price_per_unit": "Price per kg",
        "total": "Line total",
    },
}
WASTE_PHOTO = {
    "waste_type": "Type of waste visible",
    "contamination": "Contamination level",
    "estimated_volume": "Estimated volume",
}


def ev(extracted, extract_list=WEIGHT_TICKET):
    return {"extracted_data": extracted, "extract_list": extract_list}


TICKET = ev({
    "ticket_number": "WB-5521",
    "date": "2025-08-25",
    "materials": [
        {"material_name": "PET", "weight_kg": "925", "price_per_unit": "27.00", "total": "24,975.00"},
        {"material_name": "HDPE", "weight_kg": "40", "price_per_unit": "13.00", "total": "520.00"},
    ],
})


# ── the four outcomes ──────────────────────────────────────────────────────

def test_match_finds_a_value_nested_in_a_list():
    assert I.check("origin_weight_kg", 925, [TICKET])["outcome"] == I.MATCH


def test_mismatch_when_the_document_says_something_else():
    assert I.check("origin_weight_kg", 999, [TICKET])["outcome"] == I.MISMATCH


def test_not_expected_when_no_document_type_carries_the_field():
    # a waste photo never prints a weight — that is not the transaction's fault
    photo = ev({"waste_type": "plastic"}, WASTE_PHOTO)
    assert I.check("origin_weight_kg", 925, [photo])["outcome"] == I.NOT_EXPECTED


def test_unreadable_when_the_right_document_yielded_nothing():
    # a weight ticket SHOULD print a weight; this one gave us nothing
    blank = ev({}, WEIGHT_TICKET)
    assert I.check("origin_weight_kg", 925, [blank])["outcome"] == I.UNREADABLE


def test_unreadable_is_not_mismatch():
    """The distinction this whole module exists for."""
    blank = ev({}, WEIGHT_TICKET)
    assert I.check("origin_weight_kg", 925, [blank])["outcome"] != I.MISMATCH
    assert I.check("origin_weight_kg", 999, [TICKET])["outcome"] != I.UNREADABLE


def test_a_readable_document_beats_a_blank_one():
    blank = ev({}, WEIGHT_TICKET)
    assert I.check("origin_weight_kg", 925, [blank, TICKET])["outcome"] == I.MATCH


# ── comparison behaviour ───────────────────────────────────────────────────

@pytest.mark.parametrize("col,record,expected", [
    ("origin_weight_kg", 925, I.MATCH),
    ("origin_price_per_unit", 27, I.MATCH),
    ("total_amount", 24975, I.MATCH),          # commas in the document
    ("total_amount", 520, I.MATCH),            # the second line, not the first
    ("transaction_date", "2025-08-25", I.MATCH),
    ("transaction_date", "2025-08-24", I.MISMATCH),
])
def test_columns(col, record, expected):
    assert I.check(col, record, [TICKET])["outcome"] == expected


def test_numbers_are_compared_not_string_matched():
    assert I.compare("origin_weight_kg", ["925.00"], 925) is True
    assert I.compare("origin_weight_kg", ["1,430 kg"], 1430) is True
    assert I.compare("origin_weight_kg", ["92"], 925) is False


def test_tolerance_is_zero_like_the_llm_prompt_says():
    # the prompt template states 0% — a deterministic path must not be looser
    assert I.NUMERIC_TOLERANCE == 0.0
    assert I.compare("origin_weight_kg", ["8.50"], 8.40) is False


def test_name_columns_are_left_to_the_llm():
    # fuzzy Thai/English matching is not arithmetic
    assert "material_id" not in I.DETERMINISTIC_COLUMNS
    assert "origin_id" not in I.DETERMINISTIC_COLUMNS
    assert I.check("material_id", "PET", [TICKET])["outcome"] is None


def test_missing_record_value_is_never_a_match():
    assert I.check("origin_weight_kg", None, [TICKET])["outcome"] == I.MISMATCH


# ── helpers ────────────────────────────────────────────────────────────────

def test_collect_field_reaches_into_nested_lists():
    assert I.collect_field(TICKET["extracted_data"], ["weight_kg"]) == ["925", "40"]


def test_collect_field_drops_blanks():
    data = {"materials": [{"weight_kg": None}, {"weight_kg": ""}, {"weight_kg": "5"}]}
    assert I.collect_field(data, ["weight_kg"]) == ["5"]


def test_expects_column_reads_the_declaration_not_the_data():
    assert I.expects_column("origin_weight_kg", WEIGHT_TICKET) is True
    assert I.expects_column("origin_weight_kg", WASTE_PHOTO) is False
    assert I.expects_column("total_amount", WEIGHT_TICKET) is True


def test_to_number_and_to_date():
    assert I.to_number("24,975.00") == 24975.0
    assert I.to_number("925 kg") == 925.0
    assert I.to_number(None) is None
    assert I.to_number(True) is None            # a bool is not a measurement
    assert str(I.to_date("2025-08-25")) == "2025-08-25"
    assert I.to_date("25/08/2025") is None      # evidence dates are ISO by prompt
    assert I.to_date("") is None
