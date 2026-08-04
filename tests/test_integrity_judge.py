"""Python-side integrity judging from LLM sightings.

These are the cases the old design handled with prompt rules plus the
_clean_false_positive_issues() phrase filter. Here they are arithmetic, so
they can simply be asserted.
"""

import pytest

from GEPPPlatform.services.cores.epr_ai_audit.cron import worker


def sightings(dates=(), numbers=(), content="printed tax invoice", type_ok=None):
    return {
        "dates_seen": [{"label": lbl, "value": val} for lbl, val in dates],
        "numbers_seen": [{"label": lbl, "value": val} for lbl, val in numbers],
        "image_content": content,
        "matches_stated_type": type_ok,
    }


def judge(payload, s, expected_type=None):
    return worker._judge_sightings(payload, s, expected_type=expected_type)


def fields(result):
    return set(result["matched_fields"]), {i["field"] for i in result["issues"]}


# ── formatting is not data ─────────────────────────────────────────────────

@pytest.mark.parametrize("payload_val,image_val", [
    ("29540", "29,540"),
    ("29540", "29,540.00"),
    (2040, "2,040 บาท"),
    ("12", "12.00"),
    ("1,234.56", "1234.56"),
    (27320, "27,320 kg"),
])
def test_thousands_separators_and_units_match(payload_val, image_val):
    r = judge({"totalPrice": payload_val},
              sightings(numbers=[("รวมทั้งสิ้น", image_val)]))
    matched, issued = fields(r)
    assert "totalPrice" in matched
    assert not issued
    assert r["verdict"] == "passed"


# ── Buddhist era ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload_date,image_date", [
    ("2025-11-26", "26/11/2568"),
    ("2025-11-26", "26/11/68"),
    ("2024-03-15", "15/3/67"),
    ("2025-10-27", "27/10/2568"),
])
def test_buddhist_years_convert_before_comparing(payload_date, image_date):
    r = judge({"transactionDate": payload_date},
              sightings(dates=[("วันที่", image_date)]))
    matched, issued = fields(r)
    assert "transactionDate" in matched, r
    assert not issued


def test_one_day_tolerance():
    for img in ("26/10/2025", "28/10/2025"):
        r = judge({"transactionDate": "2025-10-27T17:00:00"},
                  sightings(dates=[("Date", img)]))
        assert "transactionDate" in fields(r)[0], img


def test_any_matching_date_on_a_multi_date_document_wins():
    r = judge({"transactionDate": "2025-03-31"},
              sightings(dates=[("ออกใบ", "29/03/2568"), ("ส่งของ", "31/03/2568")]))
    assert "transactionDate" in fields(r)[0]


def test_genuinely_wrong_date_flags():
    r = judge({"transactionDate": "2025-10-27"},
              sightings(dates=[("วันที่", "27/11/2568")]))
    matched, issued = fields(r)
    assert issued == {"transactionDate"}
    assert r["verdict"] == "flagged"


# ── cannot verify is never a mismatch ──────────────────────────────────────

def test_no_dates_on_image_is_cant_verify_not_mismatch():
    r = judge({"transactionDate": "2025-10-27"}, sightings())
    matched, issued = fields(r)
    assert not issued
    assert "transactionDate" not in matched
    assert r["verdict"] == "passed"


def test_no_numbers_on_image_is_cant_verify():
    r = judge({"totalPrice": 5000}, sightings())
    matched, issued = fields(r)
    assert not issued and not matched


def test_null_payload_fields_are_skipped_entirely():
    r = judge({"transactionDate": None, "totalPrice": "", "totalQuantity": None},
              sightings(numbers=[("Total", "999")]))
    matched, issued = fields(r)
    assert not issued and not matched


# ── a field is never in both buckets ───────────────────────────────────────

def test_field_never_in_both_buckets():
    r = judge({"transactionDate": "2025-03-31", "totalPrice": "29540",
               "totalQuantity": "27320", "pricePerUnit": "8"},
              sightings(dates=[("วันที่", "31/03/2568")],
                        numbers=[("รวมทั้งสิ้น", "29,540"), ("น้ำหนัก", "27,320 kg"),
                                 ("", "13,750 x 8 = 110,000")]))
    matched, issued = fields(r)
    assert not (matched & issued), (matched, issued)


# ── the 0.00 placeholder case ──────────────────────────────────────────────

def test_zero_placeholder_does_not_beat_a_sighting_elsewhere():
    """Labelled 'ราคา/กก. 0.00' is an unfilled template field. The handwritten
    8 in '13,750 x 8 = 110,000' is the real price."""
    r = judge({"pricePerUnit": 8},
              sightings(numbers=[("ราคา/กก.", "0.00"), ("", "13750"),
                                 ("", "8"), ("", "110,000")]))
    matched, issued = fields(r)
    assert "pricePerUnit" in matched
    assert not issued


def test_unit_price_sighted_anywhere_matches():
    for entry in [("@", "12/kg"), ("", "270 x 12 = 2,040"), ("", "12 บาท")]:
        r = judge({"pricePerUnit": 12}, sightings(numbers=[entry]))
        assert "pricePerUnit" in fields(r)[0], entry


# ── labelled totals are authoritative ──────────────────────────────────────

def test_labelled_total_beats_an_incidental_sighting():
    """5000 appears as a line item, but the labelled grand total is 9999.
    That is a real mismatch, not a lucky sighting."""
    r = judge({"totalPrice": 5000},
              sightings(numbers=[("", "5000"), ("รวมทั้งสิ้น", "9999")]))
    matched, issued = fields(r)
    assert issued == {"totalPrice"}, r


def test_quantity_one_percent_tolerance():
    assert "totalQuantity" in fields(judge(
        {"totalQuantity": 1000}, sightings(numbers=[("น้ำหนัก", "1005")])))[0]
    assert "totalQuantity" in fields(judge(
        {"totalQuantity": 1000}, sightings(numbers=[("น้ำหนัก", "1200")])))[1]


# ── imageType ──────────────────────────────────────────────────────────────

def test_generic_image_types_are_skipped():
    for t in ("product_image", "photo", "other", "image"):
        r = judge({}, sightings(type_ok=False, content="a pile of bottles"),
                  expected_type=t)
        assert not r["issues"], t


def test_specific_type_mismatch_flags():
    r = judge({}, sightings(type_ok=False, content="an invoice"),
              expected_type="national_id")
    assert {i["field"] for i in r["issues"]} == {"imageType"}


def test_specific_type_match_counts():
    r = judge({}, sightings(type_ok=True, content="a printed tax invoice"),
              expected_type="tax_invoice")
    assert "imageType" in r["matched_fields"]


def test_ambiguous_type_is_cant_verify():
    r = judge({}, sightings(type_ok=None), expected_type="tax_invoice")
    assert not r["issues"] and "imageType" not in r["matched_fields"]


# ── determinism + bilingual explanations ───────────────────────────────────

def test_same_input_same_verdict():
    payload = {"totalPrice": 100, "transactionDate": "2025-01-01"}
    s = sightings(dates=[("วันที่", "05/01/2568")], numbers=[("Total", "999")])
    assert judge(payload, s) == judge(payload, s)


def test_issues_carry_both_languages():
    r = judge({"totalPrice": 100}, sightings(numbers=[("Total", "999")]))
    for issue in r["issues"]:
        assert issue["explanation"]["en"] and issue["explanation"]["th"]
        assert issue["payload_value"] is not None
        assert issue["image_indicates"]


def test_flag_only_when_issues_exist():
    assert judge({"totalPrice": 100},
                 sightings(numbers=[("Total", "100")]))["verdict"] == "passed"
    assert judge({"totalPrice": 100},
                 sightings(numbers=[("Total", "999")]))["verdict"] == "flagged"


def test_malformed_sightings_do_not_crash():
    for bad in (None, {}, {"dates_seen": None, "numbers_seen": None},
                {"numbers_seen": ["not-a-dict"]},
                {"dates_seen": [{"value": None}]}):
        r = judge({"totalPrice": 5, "transactionDate": "2025-01-01"}, bad)
        assert r["verdict"] in ("passed", "flagged")


# ── the flag ───────────────────────────────────────────────────────────────

def test_judge_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EPR_INTEGRITY_JUDGE", raising=False)
    assert worker._use_python_judge() is False
    monkeypatch.setenv("EPR_INTEGRITY_JUDGE", "python")
    assert worker._use_python_judge() is True
    monkeypatch.setenv("EPR_INTEGRITY_JUDGE", "llm")
    assert worker._use_python_judge() is False
