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

def test_judge_is_on_by_default(monkeypatch):
    monkeypatch.delenv("EPR_INTEGRITY_JUDGE", raising=False)
    assert worker._use_python_judge() is True
    monkeypatch.setenv("EPR_INTEGRITY_JUDGE", "python")
    assert worker._use_python_judge() is True
    # The only way back to the old LLM-compare path.
    monkeypatch.setenv("EPR_INTEGRITY_JUDGE", "llm")
    assert worker._use_python_judge() is False


# ── regressions found by running against live project-41 data ───────────────

@pytest.mark.parametrize("raw,expected", [
    ("วันที่: 21 มกราคม 2568", "2025-01-21"),
    ("21 ม.ค. 2568", "2025-01-21"),
    ("31 March 2025", "2025-03-31"),
    ("March 31, 2025", "2025-03-31"),
    ("26/11/2568", "2025-11-26"),
])
def test_month_names_parse(raw, expected):
    """Thai/English month names. tx 712 flagged a correct date because only
    numeric formats parsed."""
    assert expected in [str(d) for d in worker._extract_all_dates(raw)]


def test_unparseable_date_is_cant_verify_not_mismatch():
    r = judge({"transactionDate": "2025-01-20"},
              sightings(dates=[("x", "no-date-here")]))
    assert not r["issues"] and r["verdict"] == "passed"


def test_money_label_is_not_a_weight():
    """tx 740/741: a 5,605.00 baht transfer amount was read as a weight and
    compared against 590 kg because 'จำนวน' matched 'จำนวนเงิน'."""
    r = judge({"totalQuantity": 590},
              sightings(numbers=[("จำนวนเงิน", "5,605.00")]))
    assert not r["issues"], r
    assert "totalQuantity" not in r["matched_fields"]


def test_net_amount_english_is_not_a_weight():
    r = judge({"totalQuantity": 590}, sightings(numbers=[("Net Amount", "5,605.00")]))
    assert not r["issues"]


def test_no_labelled_figure_is_cant_verify():
    """A weight asked of a document that carries none. Unrelated numbers
    differing proves nothing."""
    r = judge({"totalQuantity": 590},
              sightings(numbers=[("Account", "1234567"), ("Ref", "998877")]))
    assert not r["issues"]


@pytest.mark.parametrize("gross,tare,net", [
    ("4,270", "1,780", 2490),
    ("2,200", "2,030", 170),
])
def test_gross_minus_tare_is_the_net_weight(gross, tare, net):
    """tx 713/714: scale tickets print gross and tare; the payload is the net,
    which appears nowhere on the page."""
    r = judge({"totalQuantity": net},
              sightings(numbers=[("น้ำหนัก", gross), ("น้ำหนัก", tare)]))
    assert "totalQuantity" in r["matched_fields"], r
    assert not r["issues"]


def test_net_arithmetic_does_not_apply_to_price():
    """Subtraction is a weighing-slip convention, not a general licence."""
    r = judge({"totalPrice": 2490},
              sightings(numbers=[("Total", "4,270"), ("Total", "1,780")]))
    assert {i["field"] for i in r["issues"]} == {"totalPrice"}


# ── a field examined but unverifiable must not vanish ──────────────────────

def test_a_field_the_image_cannot_confirm_is_reported_not_dropped():
    """_judge_field_numeric could always say "cant_verify" and the caller only
    handled match and mismatch, so the field fell out of both lists — reading
    to anyone downstream exactly like a field that was never checked."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalPrice": "17160", "transactionDate": "2026-06-16"},
        {"numbers_seen": [], "dates_seen": []},      # the image showed nothing
    )
    unverified = {u["field"] for u in r["unverified"]}
    assert "totalPrice" in unverified
    assert "transactionDate" in unverified
    # and it is neither a pass nor a failure
    assert not r["issues"]
    assert "totalPrice" not in r["matched_fields"]


def test_an_unverified_field_explains_why():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings({"totalPrice": "17160"}, {"numbers_seen": [], "dates_seen": []})
    u = next(u for u in r["unverified"] if u["field"] == "totalPrice")
    assert u["payload_value"] == "17160"
    assert u["image_indicates"] == "not shown"
    assert u["explanation"]["en"] and u["explanation"]["th"]


def test_a_field_nobody_submitted_is_not_reported_as_unverified():
    """Empty payload values are not an open question — there is nothing to
    check. Only fields actually submitted belong in the list."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings({"totalPrice": None, "pricePerUnit": ""},
                         {"numbers_seen": [], "dates_seen": []})
    assert r["unverified"] == []


def test_a_match_still_carries_its_confirmation():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalPrice": "17160"},
        {"numbers_seen": [{"label": "total", "value": "17,160.00"}], "dates_seen": []},
    )
    assert "totalPrice" in r["matched_fields"]
    c = next(c for c in r["confirmations"] if c["field"] == "totalPrice")
    assert "17160" in c["explanation"]["en"]
    assert r["unverified"] == []


# ── paperwork precedes the record ──────────────────────────────────────────

def _judge_date(payload_date, image_dates):
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings
    return _judge_sightings(
        {"transactionDate": payload_date},
        {"dates_seen": [{"label": "date", "value": d} for d in image_dates],
         "numbers_seen": []},
    )


def test_documents_dated_days_before_the_record_are_not_a_mismatch():
    """Real case, embeded 553: weighed 30-31 Aug, QC signed 1 Sep, recorded
    3 Sep. A symmetric +/-1 day window flagged all three documents."""
    r = _judge_date("2026-09-03", ["30/08/2026", "31/08/2026", "01/09/2026"])
    assert not r["issues"]
    assert "transactionDate" in r["matched_fields"]


def test_the_confirmation_says_the_distance_and_the_direction():
    r = _judge_date("2026-09-03", ["30/08/2026", "01/09/2026"])
    c = next(c for c in r["confirmations"] if c["field"] == "transactionDate")
    assert "2 day(s) after 2026-09-01" in c["explanation"]["en"]


def test_a_buddhist_era_document_date_still_anchors():
    r = _judge_date("2026-09-03", ["31/8/69", "1/9/69"])
    assert not r["issues"]


def test_a_record_far_after_every_document_is_flagged():
    r = _judge_date("2026-10-15", ["30/08/2026", "01/09/2026"])  # 44 days
    assert {i["field"] for i in r["issues"]} == {"transactionDate"}


def test_a_record_dated_the_day_before_its_documents_passes():
    """The single largest pattern in real data (195 of 538): the paperwork is
    written up the day AFTER the material moves, so the transaction date sits
    one day before every document. Anchoring on the earliest rejected these."""
    r = _judge_date("2026-08-29", ["30/08/2026", "01/09/2026"])
    assert not r["issues"]
    assert "transactionDate" in r["matched_fields"]


def test_a_record_far_before_every_document_is_flagged():
    r = _judge_date("2026-06-01", ["30/08/2026", "01/09/2026"])
    assert {i["field"] for i in r["issues"]} == {"transactionDate"}
    assert "before" in r["issues"][0]["explanation"]["en"]


def test_an_exact_match_still_passes():
    r = _judge_date("2026-09-03", ["03/09/2026"])
    assert not r["issues"] and "transactionDate" in r["matched_fields"]


def test_the_window_is_three_days_either_side():
    """Measured: +/-1 accepts 96.5% of real transactions, +/-3 98.3%, +/-5
    99.4%. Past 3 the curve flattens and starts admitting wrong evidence; at 1
    an OCR slip on a Buddhist year fails an honest transaction."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _DATE_WINDOW_DAYS
    assert _DATE_WINDOW_DAYS == 3


def test_it_measures_to_the_NEAREST_document_date():
    """Not the earliest. A weighing sheet weeks old alongside a current invoice
    should not drag the whole transaction down."""
    r = _judge_date("2026-09-02", ["01/06/2026", "01/09/2026"])
    assert not r["issues"]
    c = next(c for c in r["confirmations"] if c["field"] == "transactionDate")
    assert "2026-09-01" in c["explanation"]["en"]


# ── a confirmation must name what it matched ───────────────────────────────

def test_a_numeric_pass_names_the_figure_it_matched():
    """"matches the image. Seen: None" reads as a bug, not a pass — the judge
    only returned the sighting on a MISMATCH."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalQuantity": "5900.00000"},
        {"numbers_seen": [{"label": "น้ำหนักสุทธิ", "value": "5,900"}],
         "dates_seen": []},
    )
    c = next(c for c in r["confirmations"] if c["field"] == "totalQuantity")
    assert "None" not in c["explanation"]["en"]
    assert "5,900" in c["explanation"]["en"]
    assert c["image_indicates"] == "5,900"


def test_a_sighting_only_pass_also_names_it():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"pricePerUnit": "10"},
        {"numbers_seen": [{"label": "scribble", "value": "10"}], "dates_seen": []},
    )
    c = next(c for c in r["confirmations"] if c["field"] == "pricePerUnit")
    assert "None" not in c["explanation"]["en"]


def test_a_net_weight_match_says_it_was_derived():
    """A weighbridge ticket prints gross and tare; the net is the difference.
    "matches the image. Seen: 17,730, 11,830" for a submitted 5,900 reads as a
    false pass — neither number is the value."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalQuantity": "5900"},
        {"numbers_seen": [{"label": "น้ำหนักรวม", "value": "17,730"},
                          {"label": "น้ำหนักรถเปล่า", "value": "11,830"}],
         "dates_seen": []},
    )
    assert "totalQuantity" in r["matched_fields"]
    c = next(c for c in r["confirmations"] if c["field"] == "totalQuantity")
    assert "difference" in c["explanation"]["en"]
    assert "gross minus tare" in c["explanation"]["en"]


def test_a_direct_sighting_does_not_claim_to_be_derived():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalQuantity": "5900"},
        {"numbers_seen": [{"label": "น้ำหนักสุทธิ", "value": "5,900"}],
         "dates_seen": []},
    )
    c = next(c for c in r["confirmations"] if c["field"] == "totalQuantity")
    assert "difference" not in c["explanation"]["en"]


def test_the_thai_explanation_uses_the_thai_description():
    """The model describes the image in English; dropping that into a Thai
    sentence gave "รูปเป็น printed UBC receiving report ตรงกับ..."."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalQuantity": "1"},
        {"numbers_seen": [], "dates_seen": [],
         "image_content": "printed UBC receiving report",
         "image_content_th": "รายงานรับกล่องเครื่องดื่มแบบพิมพ์",
         "matches_stated_type": True},
        expected_type="production_report",
    )
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "รายงานรับกล่องเครื่องดื่มแบบพิมพ์" in c["explanation"]["th"]
    assert "printed UBC receiving report" not in c["explanation"]["th"]
    assert "printed UBC receiving report" in c["explanation"]["en"]


def test_it_falls_back_when_the_model_omits_the_thai_phrase():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"totalQuantity": "1"},
        {"numbers_seen": [], "dates_seen": [],
         "image_content": "printed tax invoice", "matches_stated_type": True},
        expected_type="tax_invoice",
    )
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "printed tax invoice" in c["explanation"]["th"]


def test_a_serial_number_shaped_like_a_date_is_not_evidence():
    """A tax id or serial matches DD/MM/YYYY. One produced "1983-10-08" on a
    2026 transaction and was flagged as 15,655 days out."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"transactionDate": "2026-08-10"},
        {"dates_seen": [{"label": "เลขที่", "value": "08/10/1983"},
                        {"label": "วันที่", "value": "10/08/2026"}],
         "numbers_seen": []},
    )
    assert not r["issues"]
    assert "transactionDate" in r["matched_fields"]


def test_only_noise_is_unverified_not_a_mismatch():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"transactionDate": "2026-08-10"},
        {"dates_seen": [{"label": "เลขที่", "value": "08/10/1983"}],
         "numbers_seen": []},
    )
    assert not r["issues"]
    assert {u["field"] for u in r["unverified"]} == {"transactionDate"}


def test_the_plausible_window_is_two_years():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _DATE_PLAUSIBLE_DAYS
    assert _DATE_PLAUSIBLE_DAYS == 730


# ── a review is not overwritten by a re-run ────────────────────────────────

def test_human_decided_statuses_are_named():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import (
        _HUMAN_DECIDED_STATUSES, _determine_status,
    )
    assert _HUMAN_DECIDED_STATUSES == {"approved", "rejected"}
    # and the worker itself never produces one, so seeing one means reviewed
    for cands, integ in (([], {"issues": []}), ([], {"issues": [{"field": "x"}]})):
        assert _determine_status(cands, integ) not in _HUMAN_DECIDED_STATUSES


# ── the year is the digit the model gets wrong ─────────────────────────────

def test_a_misread_buddhist_year_does_not_fail_a_matching_day():
    """Measured on project 50: the same document came back as 2026-08-31,
    2069-08-31 and 31/8/67 across calls. Day and month were right every time."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    for printed in ("31/8/67", "31/8/69", "2069-08-31"):
        r = _judge_sightings(
            {"transactionDate": "2026-08-30"},
            {"dates_seen": [{"label": "date", "value": printed}], "numbers_seen": []},
        )
        assert not r["issues"], printed
        assert "transactionDate" in r["matched_fields"], printed


def test_a_genuinely_different_day_still_fails():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"transactionDate": "2026-08-30"},
        {"dates_seen": [{"label": "date", "value": "15/02/69"}], "numbers_seen": []},
    )
    assert {i["field"] for i in r["issues"]} == {"transactionDate"}


def test_a_year_blind_match_says_so():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings

    r = _judge_sightings(
        {"transactionDate": "2026-08-30"},
        {"dates_seen": [{"label": "date", "value": "31/8/67"}], "numbers_seen": []},
    )
    c = next(c for c in r["confirmations"] if c["field"] == "transactionDate")
    assert "year differs" in c["explanation"]["en"]


# ── say WHAT made it that type, and why some types cannot be checked ───────

def _judge_type(stated, content, content_th, elements, elements_th, ok=True):
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings
    return _judge_sightings(
        {}, {"dates_seen": [], "numbers_seen": [],
             "image_content": content, "image_content_th": content_th,
             "identifying_elements": elements,
             "identifying_elements_th": elements_th,
             "matches_stated_type": ok},
        expected_type=stated)


def test_a_type_match_lists_what_identified_it():
    """"the image is a weighing sheet" is an assertion; naming the letterhead
    and the scale display is something a reviewer can check."""
    r = _judge_type("product_weighing_sheet",
                    "printed product weighing sheet", "ใบชั่งน้ำหนักสินค้าแบบพิมพ์",
                    "company letterhead, net weight column, operator signature",
                    "หัวจดหมายบริษัท, ช่องน้ำหนักสุทธิ, ลายเซ็นผู้ปฏิบัติงาน")
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "net weight column" in c["explanation"]["en"]
    assert "ช่องน้ำหนักสุทธิ" in c["explanation"]["th"]


def test_a_type_mismatch_also_says_what_it_saw():
    r = _judge_type("money_transfer_document", "a photo of a bird", "รูปถ่ายนก",
                    "tree branch, feathers", "กิ่งไม้, ขนนก", ok=False)
    i = next(i for i in r["issues"] if i["field"] == "imageType")
    assert "feathers" in i["explanation"]["en"]
    assert "ขนนก" in i["explanation"]["th"]


def _judge_material_slot(stated, content, is_doc, shows_material=None):
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _judge_sightings
    return _judge_sightings(
        {}, {"dates_seen": [], "numbers_seen": [],
             "image_content": content, "image_content_th": content,
             "identifying_elements": "", "identifying_elements_th": "",
             "is_paper_document": is_doc,
             "shows_material": shows_material},
        expected_type=stated)


def test_a_material_slot_holding_the_material_passes():
    """"Is this specifically a product image" has no wrong answer — a photo of
    bottles IS one. "Is this paperwork" does."""
    r = _judge_material_slot("product_image", "a pile of PET bottles", False)
    assert not r["issues"]
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "shows the material" in c["explanation"]["en"]


def test_a_material_slot_holding_a_document_is_flagged():
    r = _judge_material_slot("product_image", "a printed tax invoice", True)
    i = next(i for i in r["issues"] if i["field"] == "imageType")
    assert "should be a photo of the material" in i["explanation"]["en"]


def test_an_undecidable_material_slot_is_unverified():
    r = _judge_material_slot("product_image", "something unclear", None)
    assert not r["issues"]
    u = next(u for u in r["unverified"] if u["field"] == "imageType")
    assert "Could not tell" in u["explanation"]["en"]


def test_every_generic_slot_gets_the_material_check():
    for t in ("product_image", "waste_photo", "material_photo", "other"):
        r = _judge_material_slot(t, "a printed receipt", True)
        assert {i["field"] for i in r["issues"]} == {"imageType"}, t


def test_the_elements_are_optional():
    r = _judge_type("qc_file", "a QC report", "ใบตรวจสอบคุณภาพ", "", "")
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "Identified by" not in c["explanation"]["en"]


def test_paperwork_that_carries_product_photos_is_the_product_image():
    """A delivery sheet with the truck and the bales pasted on it still shows
    the material, which is what the slot is for. Paper wrapping is not a
    wrong file."""
    r = _judge_material_slot(
        "product_image", "a sheet with truck and baled-waste photos", True,
        shows_material=True)
    assert not r["issues"]
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "shows the material" in c["explanation"]["en"]


def test_a_document_with_no_product_photo_is_still_flagged():
    r = _judge_material_slot(
        "product_image", "a printed tax invoice", True, shows_material=False)
    assert {i["field"] for i in r["issues"]} == {"imageType"}


def test_a_page_that_is_essentially_just_a_photo_is_not_paperwork():
    """A printed or scanned photograph with no data on it is the material,
    whatever it is printed on."""
    r = _judge_material_slot(
        "product_image", "a printed photograph of baled PET bottles", False)
    assert not r["issues"]
    c = next(c for c in r["confirmations"] if c["field"] == "imageType")
    assert "shows the material" in c["explanation"]["en"]


# ── the slot type reads in Thai too ────────────────────────────────────────

def test_the_thai_sentence_names_the_type_in_thai():
    """It used to print the raw slug: "ระบุประเภทเป็น 'money_transfer_document'"."""
    r = _judge_type("money_transfer_document", "a photo of a rabbit", "รูปถ่ายกระต่าย",
                    "", "", ok=False)
    i = next(i for i in r["issues"] if i["field"] == "imageType")
    assert "เอกสารการโอนเงิน" in i["explanation"]["th"]
    assert "money_transfer_document" not in i["explanation"]["th"]
    # the English half keeps the key, which is what a developer greps for
    assert "money_transfer_document" in i["explanation"]["en"]


def test_every_slot_type_in_use_has_a_thai_name():
    """The 22 rows of transaction_image_types. A new one renders as its slug,
    which is the old behaviour, not a crash."""
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _IMAGE_TYPE_TH
    for t in ("invoice", "bill_of_lading", "qc_file", "receipt", "cash_bill",
              "payment_voucher", "tax_invoice", "id_card",
              "invoice/receipt/cash_bill/payment_voucher",
              "invoice/tax_invoice/cash_bill/payment_voucher/id_card",
              "money_transfer_document", "production_report",
              "monthly_progress_report", "production_other_report",
              "product_weighing_sheet",
              "product_weighing_sheet/product_weighing_image", "product_image"):
        assert t in _IMAGE_TYPE_TH, t


def test_an_unknown_type_falls_back_to_its_key():
    from GEPPPlatform.services.cores.epr_ai_audit.cron.worker import _type_th
    assert _type_th("brand_new_type") == "brand_new_type"
    assert _type_th(None) is None
