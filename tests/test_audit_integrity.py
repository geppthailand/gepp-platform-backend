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
])
def test_columns(col, record, expected):
    assert I.check(col, record, [TICKET])["outcome"] == expected


def test_numbers_are_compared_not_string_matched():
    # compare returns the MATCHING VALUE, not a bool, so a pass can say what
    # it was based on
    assert I.compare("origin_weight_kg", ["925.00"], 925) == "925.00"
    assert I.compare("origin_weight_kg", ["1,430 kg"], 1430) == "1,430 kg"
    assert I.compare("origin_weight_kg", ["92"], 925) is None


def test_tolerance_is_zero_like_the_llm_prompt_says():
    # the prompt template states 0% — a deterministic path must not be looser
    assert I.NUMERIC_TOLERANCE == 0.0
    assert I.compare("origin_weight_kg", ["8.50"], 8.40) is None


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
    assert I.to_date("") is None


@pytest.mark.parametrize("printed,expected", [
    ("2026-01-24", "2026-01-24"),      # ISO
    ("24/1/2026", "2026-01-24"),       # what documents actually write
    ("24/01/2026", "2026-01-24"),
    ("07/03/69", "2026-03-07"),        # two-digit Buddhist year
    ("9/3/69", "2026-03-09"),
    ("25 ส.ค. 2568", "2025-08-25"),    # Thai short month, Buddhist year
    ("5 มีนาคม 2568", "2025-03-05"),
    ("08-May-25", "2025-05-08"),       # English abbreviation
])
def test_to_date_reads_what_documents_print(printed, expected):
    """Accepting only ISO meant no evidence date ever parsed, so every date
    comparison fell through to mismatch — the bug that flagged paperwork whose
    dates were in fact identical."""
    assert str(I.to_date(printed)) == expected


def test_identical_dates_written_differently_still_match():
    assert I.check("transaction_date", "2026-01-24",
                   [_d("24/1/2026")])["outcome"] == I.MATCH


def test_junk_is_not_a_date():
    assert I.to_date("n/a") is None
    assert I.to_date("31/31/2026") is None      # not a real day


# ── dates: the earliest document anchors the transaction ──────────────────

def _d(day, doc="invoice", fid=1):
    return {"extracted_data": {"date": day}, "extract_list": WEIGHT_TICKET,
            "file_id": fid, "document_type_name": doc}


def test_the_earliest_document_dates_the_transaction():
    """11, 13, 14, 16 December: the goods moved on the 11th and the rest is
    settlement. Anchor on the earliest, accept everything after."""
    ev = [_d("13/12/2026"), _d("14/12/2026"), _d("16/12/2026"),
          _d("11/12/2026", "product_weighing_sheet", 4)]
    r = I.check("transaction_date", "2026-12-11", ev)
    assert r["outcome"] == I.MATCH
    assert r["evidence"]["document_type_name"] == "product_weighing_sheet"


def test_later_paperwork_has_no_upper_limit():
    # a voucher paid three weeks after delivery is normal, not a discrepancy
    ev = [_d("11/12/2026", "product_weighing_sheet"), _d("02/01/2027", "payment_voucher")]
    assert I.check("transaction_date", "2026-12-11", ev)["outcome"] == I.MATCH


def test_a_document_before_the_transaction_is_flagged():
    """The real signal: evidence that predates the transaction it is filed
    under usually belongs to a different delivery."""
    ev = [_d("11/12/2026", "product_weighing_sheet"), _d("02/09/2026", "qc_file")]
    r = I.check("transaction_date", "2026-12-11", ev)
    assert r["outcome"] == I.MISMATCH
    assert "predate" in r["reason"]


def test_the_record_must_agree_with_its_first_document():
    # earliest doc is the 11th but the record claims the 14th: either the
    # record is dated too late, or that file belongs to another delivery
    ev = [_d("11/12/2026", "product_weighing_sheet"), _d("14/12/2026")]
    r = I.check("transaction_date", "2026-12-25", ev)      # beyond the grace
    assert r["outcome"] == I.MISMATCH
    assert "predate" in r["reason"]


def test_a_record_dated_before_every_document_is_flagged():
    ev = [_d("11/12/2026", "product_weighing_sheet"), _d("14/12/2026")]
    r = I.check("transaction_date", "2026-12-01", ev)
    assert r["outcome"] == I.MISMATCH
    assert "nothing supports" in r["reason"]


def test_one_document_is_still_an_anchor():
    assert I.check("transaction_date", "2026-12-11", [_d("11/12/2026")])["outcome"] == I.MATCH


def test_dates_written_any_way_still_anchor():
    ev = [_d("9/3/69", "invoice"), _d("7/3/2026", "qc_file", 2)]
    r = I.check("transaction_date", "2026-03-07", ev)
    assert r["outcome"] == I.MATCH
    assert r["evidence"]["document_type_name"] == "qc_file"


def test_no_readable_date_anywhere_is_unreadable_not_mismatch():
    ev = [{"extracted_data": {"date": "n/a"}, "extract_list": WEIGHT_TICKET,
           "file_id": 1, "document_type_name": "invoice"}]
    assert I.check("transaction_date", "2026-12-11", ev)["outcome"] == I.UNREADABLE


def test_the_backdating_grace_matches_the_measured_lead_time():
    """0 flagged 49% of real transactions: QC and weighing legitimately predate
    the record, which is typed up after the goods arrive. 5 passes all 46
    normal cases and still catches the 9 outliers."""
    assert I.BACKDATE_GRACE_DAYS == 5


def test_a_normal_lead_time_passes():
    ev = [_d("11/12/2026", "qc_file"), _d("16/12/2026", "invoice")]
    assert I.check("transaction_date", "2026-12-14", ev)["outcome"] == I.MATCH


def test_a_document_months_early_is_still_flagged():
    ev = [_d("15/12/2025", "product_weighing_sheet"), _d("05/06/2026", "invoice")]
    r = I.check("transaction_date", "2026-06-05", ev)
    assert r["outcome"] == I.MISMATCH
    assert "predate" in r["reason"]


# ── why did it pass ────────────────────────────────────────────────────────

def test_a_pass_names_the_document_and_the_value():
    """An approved audit used to carry no explanation, so it could not be
    re-traced without re-running it."""
    r = I.check("origin_weight_kg", 925, [
        {"extracted_data": TICKET["extracted_data"], "extract_list": WEIGHT_TICKET,
         "file_id": 77, "document_type_name": "Weight Ticket"}])
    assert r["outcome"] == I.MATCH
    assert r["evidence"] == {"file_id": 77, "document_type_name": "Weight Ticket",
                             "value": "925"}
    assert "925" in r["reason"] and "Weight Ticket" in r["reason"]


def test_a_date_pass_names_the_anchor_and_the_trail():
    r = I.check("transaction_date", "2026-12-11",
                [_d("11/12/2026", "product_weighing_sheet"), _d("16/12/2026", "invoice")])
    assert r["outcome"] == I.MATCH
    assert "earliest" in r["reason"] and "2026-12-16" in r["reason"]


def test_a_mismatch_shows_both_sides():
    r = I.check("origin_weight_kg", 999, [
        {"extracted_data": TICKET["extracted_data"], "extract_list": WEIGHT_TICKET,
         "file_id": 77, "document_type_name": "Weight Ticket"}])
    assert r["outcome"] == I.MISMATCH
    assert "999" in r["reason"] and "925" in r["reason"]


def test_the_closest_date_wins_not_the_first():
    """Several documents carry a date and they differ by design. Reporting the
    invoice's 3-day gap when the weighing sheet is exact makes a sound pass
    look borderline."""
    invoice = {"extracted_data": {"date": "27/1/2026"}, "extract_list": WEIGHT_TICKET,
               "file_id": 1, "document_type_name": "invoice"}
    sheet = {"extracted_data": {"date": "24/1/2026"}, "extract_list": WEIGHT_TICKET,
             "file_id": 2, "document_type_name": "product_weighing_sheet"}
    r = I.check("transaction_date", "2026-01-24", [invoice, sheet])
    assert r["outcome"] == I.MATCH
    assert r["evidence"]["document_type_name"] == "product_weighing_sheet"
    assert "3 day" not in r["reason"]
