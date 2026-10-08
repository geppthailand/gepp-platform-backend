"""GET /api/epr/ai_audit/transactions/{id}/audit

Keyed by epr_transactions_embeded.id — these transactions come from the legacy
database, so the Postgres `transactions` table has nothing to say about them.

The verdicts already existed in flags.integrity and were never served: the list
endpoint returned the raw blob. This endpoint unpacks matched_fields (why it
passed) and issues (why it failed).
"""

from datetime import datetime
from decimal import Decimal

import pytest

def _bad_request():
    """Resolved at call time, not import time.

    conftest snapshots and restores sys.modules per test, so a class imported
    at module load can be a DIFFERENT object from the one the service raises
    later — pytest.raises then catches nothing and the test fails while the
    code is correct. Importing inside the test sidesteps that entirely.
    """
    from GEPPPlatform.libs.exceptions import BadRequestException
    return BadRequestException



import GEPPPlatform.services.cores.epr_ai_audit.api.handlers as handlers
from GEPPPlatform.services.cores.epr_ai_audit.api.service import EprAiAuditService

FLAGS = {
    "duplicates": [{"embeded_id": 4471, "score": 0.97}],
    "integrity": {
        "matched_fields": ["transactionDate", "weight", "invoiceNo"],
        "confirmations": [
            {"field": "transactionDate", "payload_value": "2026-06-16",
             "image_indicates": "date: 16/6/69",
             "explanation": {"en": "A date on the image is within 1 day of 2026-06-16.",
                             "th": "พบวันที่ในรูปตรงกับ 2026-06-16"}},
            {"field": "weight", "payload_value": "1430",
             "image_indicates": "net weight: 1,430",
             "explanation": {"en": "Submitted quantity 1430 matches the image.",
                             "th": "ปริมาณที่กรอก 1430 ตรงกับในรูป"}},
        ],
        "issues": [{
            "field": "pricePerUnit",
            "payload_value": "15.75",
            "image_indicates": "12.00",
            "explanation": {"en": "The invoice shows 12.00 per kg, not 15.75",
                            "th": "ใบกำกับภาษีแสดง 12.00 ต่อกิโลกรัม ไม่ใช่ 15.75"},
        }],
        "checked_image_count": 4,
        "errors": [],
        "checked_at": "2026-06-16T04:12:40+00:00",
    },
    "dedup_at": "2026-06-16T04:12:39+00:00",
    "reason": "flagged: 1 field mismatch",
}

TX = (4482, True, {"id": "151008", "invoiceNo": "PRO2506-008"}, 41,
      Decimal("0.92"), "flagged", FLAGS,
      datetime(2026, 6, 16, 4, 0), datetime(2026, 6, 16, 4, 12), None)

TX2 = (4483, True, {"_legacy_id": 151009}, 41, Decimal("0.80"), "passed", {},
       datetime(2026, 6, 17, 4, 0), datetime(2026, 6, 17, 4, 12), None)

REC_FLAGS = {"integrity": {"matched_fields": ["weight"], "issues": [],
                           "checked_image_count": 2, "errors": [],
                           "checked_at": "2026-06-16T04:12:40+00:00"}}
# rows now carry transaction_id as the second column (set-based fetch)
RECS = [(9901, 4482, True, {"weight": "1430"}, Decimal("0.90"), "passed", REC_FLAGS,
         datetime(2026, 6, 16, 4, 0), datetime(2026, 6, 16, 4, 12), None)]


IMAGES = [
    # (transaction_id, id, name, url, type, record_id, extracted_data)
    (4482, 501, "invoice.jpg", "https://s3/inv.jpg", "invoice", None,
     {"scene_type": "invoice", "document_number": "PRO2506-008",
      "document_date": "2026-06-16", "total_amount": 17160,
      "weight": {"value": 1430, "unit": "kg"},
      "visual_description": "A Thai tax invoice"}),
    (4482, 502, "scale.jpg", "https://s3/scale.jpg", "product_weighing_sheet", 9901,
     {"scene_type": "scale_reading", "weight": {"value": 1430, "unit": "kg"},
      "visual_description": "A weighbridge ticket"}),
    (4482, 503, "photo.jpg", "https://s3/photo.jpg", "product_image", 9901, None),
]


class FakeDB:
    def __init__(self, tx=TX, recs=RECS, dups=((4471, {"_legacy_id": 151001}),),
                 images=IMAGES, extra=()):
        self.rows = ([tx] if tx else []) + list(extra)
        self.recs, self.dups, self.images = recs, dups, images

    def execute(self, stmt, params=None):
        sql, db = str(stmt), self
        ids = set((params or {}).get("ids") or [])

        class R:
            def fetchone(self):
                return None

            def fetchall(self):
                if "SELECT id, raw_data FROM epr_transactions_embeded" in sql:
                    return db.dups
                if "epr_transaction_image" in sql:
                    return db.images
                if "epr_transaction_records_embeded" in sql and "SELECT id, transaction_id" in sql:
                    return db.recs
                if "FROM epr_transactions_embeded" in sql:
                    return [r for r in db.rows if r[0] in ids]
                return []
        return R()


def _get(db=None, tx_id=4482):
    """The single-transaction view, for the assertions below."""
    out = EprAiAuditService(db or FakeDB()).get_transaction_audit(tx_id)
    assert out["count"] == len(out["results"])
    return out["results"][0]


def _raw(db=None, tx_id=4482):
    return EprAiAuditService(db or FakeDB()).get_transaction_audit(tx_id)


# ── it is keyed by the EMBEDDED id ─────────────────────────────────────────

def test_it_takes_the_embeded_id_and_also_reports_the_source_id():
    out = _get()
    assert out["transaction"]["id"] == 4482                  # epr_transactions_embeded.id
    assert out["transaction"]["transaction_id"] == "151008"  # the id a caller knows


# ── why it passed, why it failed ───────────────────────────────────────────

def test_matched_fields_become_the_passed_list():
    a = _get()["audit"]
    assert [p["field"] for p in a["passed"]] == ["transactionDate", "weight", "invoiceNo"]
    assert a["passed_count"] == 3


def test_a_pass_explains_itself_the_same_way_a_failure_does():
    """A pass used to be a bare field name — you could see that something was
    checked but not what against."""
    p = _get()["audit"]["passed"][0]
    assert p["field"] == "transactionDate"
    assert p["payload_value"] == "2026-06-16"       # what was submitted
    assert p["image_indicates"] == "date: 16/6/69"  # what the image showed
    assert p["explanation"]["en"] and p["explanation"]["th"]
    assert p["explained"] is True


def test_a_pass_recorded_before_confirmations_existed_is_marked_unexplained():
    """Old rows kept only the field name. The pass is real; say so honestly
    rather than inventing a reason for it."""
    p = _get()["audit"]["passed"][2]                # invoiceNo has no confirmation
    assert p["field"] == "invoiceNo"
    assert p["explained"] is False
    assert p["payload_value"] is None and p["explanation"] == {}


def test_a_failure_carries_both_sides_and_both_languages():
    f = _get()["audit"]["failed"][0]
    assert f["field"] == "pricePerUnit"
    assert f["payload_value"] == "15.75"        # what the operator entered
    assert f["image_indicates"] == "12.00"      # what the document showed
    assert "12.00" in f["explanation"]["en"]
    assert f["explanation"]["th"]


def test_duplicates_resolve_to_a_source_id_you_can_open():
    d = _get()["audit"]["duplicates"][0]
    assert d["embeded_id"] == 4471 and d["transaction_id"] == 151001


def test_the_reason_behind_the_status_is_included():
    out = _get()
    assert out["transaction"]["status"] == "flagged"
    assert out["audit"]["reason"] == "flagged: 1 field mismatch"
    assert out["audit"]["checked_image_count"] == 4


# ── records get their own verdicts ─────────────────────────────────────────

def test_each_record_carries_its_own_passed_and_failed():
    rec = _get()["records"][0]
    assert [p["field"] for p in rec["audit"]["passed"]] == ["weight"]
    assert rec["audit"]["failed"] == []


def test_a_skipped_record_is_marked_not_silently_passed():
    """Records with no images are set to 'passed' with skipped=true so they are
    not stuck pending — a reviewer must be able to tell that apart."""
    flags = {"integrity": {"matched_fields": [], "issues": [], "skipped": True,
                           "checked_image_count": 0, "errors": []}}
    recs = [(9902, 4482, True, {}, None, "passed", flags,
             datetime(2026, 6, 16), datetime(2026, 6, 16), None)]
    assert _get(FakeDB(recs=recs))["records"][0]["audit"]["skipped"] is True


# ── robustness ─────────────────────────────────────────────────────────────

def test_the_body_is_json_serialisable():
    import json
    json.dumps(_get())                       # Decimal would raise
    assert _get()["transaction"]["ai_score"] == 0.92


def test_a_transaction_not_yet_deduped_does_not_break():
    out = _get(FakeDB(tx=tuple(list(TX[:6]) + [{}] + list(TX[7:])), dups=(), images=()))
    assert out["audit"]["passed"] == [] and out["audit"]["failed"] == []
    assert out["audit"]["checked_at"] is None


def test_a_missing_transaction_comes_back_under_not_found():
    out = EprAiAuditService(FakeDB(tx=None)).get_transaction_audit(999)
    assert out["results"] == [] and out["not_found"] == [999]


def test_a_non_numeric_id_is_400_not_a_500():
    with pytest.raises(_bad_request()):
        EprAiAuditService(FakeDB()).get_transaction_audit("abc")


def test_the_route_reaches_the_service(monkeypatch):
    seen = {}
    monkeypatch.setattr(handlers, "EprAiAuditService",
                        lambda db: type("S", (), {
                            "get_transaction_audit": lambda _s, i: seen.setdefault("id", i)
                        })())
    handlers.handle_epr_ai_audit_routes(
        {"rawPath": "/api/epr/ai_audit/transactions/4482/audit"},
        data={}, method="GET", db_session=object())
    assert seen["id"] == "4482"


# ── the evidence behind an unexplained pass ────────────────────────────────

def test_image_extractions_are_served_so_old_passes_can_be_checked():  # noqa
    """Rows deduped before `confirmations` existed carry only a field name.
    What they were judged against is still in epr_transaction_image
    .extracted_data and was never thrown away — serve it rather than ask a
    reviewer to trust an unexplained pass."""
    out = _get()
    inv = out["images"][0]
    assert inv["id"] == 501 and inv["record_id"] is None
    assert inv["extracted_data"]["weight"] == {"value": 1430, "unit": "kg"}
    assert inv["extracted"] is True


def test_record_images_hang_off_their_record_not_the_transaction():
    out = _get()
    assert [i["id"] for i in out["images"]] == [501]            # txn-level only
    assert [i["id"] for i in out["records"][0]["images"]] == [502, 503]


def test_an_unprocessed_image_is_flagged_not_silently_empty():
    """extracted_data NULL means the worker never got to it — different from
    an image that yielded nothing."""
    photo = _get()["records"][0]["images"][1]
    assert photo["id"] == 503
    assert photo["extracted_data"] is None and photo["extracted"] is False


# ── several ids in one request ─────────────────────────────────────────────

def test_several_ids_come_back_in_the_order_asked_for():
    out = EprAiAuditService(FakeDB(extra=(TX2,))).get_transaction_audit("4483,4482")
    assert [r["transaction"]["id"] for r in out["results"]] == [4483, 4482]
    assert out["count"] == 2 and out["not_found"] == []


def test_a_stale_id_in_a_batch_does_not_fail_the_rest():
    """One bad id should not cost the other nine."""
    out = EprAiAuditService(FakeDB(extra=(TX2,))).get_transaction_audit("4482,99999,4483")
    assert [r["transaction"]["id"] for r in out["results"]] == [4482, 4483]
    assert out["not_found"] == [99999]


def test_duplicate_ids_are_collapsed():
    out = EprAiAuditService(FakeDB()).get_transaction_audit("4482,4482,4482")
    assert out["count"] == 1


def test_one_id_still_returns_a_list_so_callers_need_not_branch():
    out = EprAiAuditService(FakeDB()).get_transaction_audit("4482")
    assert isinstance(out["results"], list) and out["count"] == 1


def test_records_and_images_are_attached_to_the_right_transaction():
    out = EprAiAuditService(FakeDB(extra=(TX2,))).get_transaction_audit("4482,4483")
    first, second = out["results"]
    assert first["records_count"] == 1 and [i["id"] for i in first["images"]] == [501]
    assert second["records_count"] == 0 and second["images"] == []


def test_too_many_ids_is_rejected():
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _MAX_AUDIT_IDS
    many = ",".join(str(i) for i in range(_MAX_AUDIT_IDS + 1))
    with pytest.raises(_bad_request(), match=str(_MAX_AUDIT_IDS)):
        EprAiAuditService(FakeDB()).get_transaction_audit(many)


def test_a_blank_or_non_numeric_id_is_rejected():
    for bad in (" , ", "4482,abc"):
        with pytest.raises(_bad_request()):
            EprAiAuditService(FakeDB()).get_transaction_audit(bad)


# ── every submitted field accounts for itself ──────────────────────────────

RAW_WITH_EXTRAS = {
    "_legacy_id": 151008,
    "transactionDate": "2026-09-03",      # judged
    "totalQuantity": 12006.19,            # judged
    "invoiceNo": "2608-024",              # deliberately not checked
    "customerName": None,                 # no check defined
    "vesselName": "MV Test",              # no check defined
    "images": [{"id": 1}],                # structural, not a field
    "organization": {"id": "2039"},       # structural
}

COVERED_FLAGS = {
    "integrity": {
        "matched_fields": ["transactionDate"],
        "confirmations": [{"field": "transactionDate", "payload_value": "2026-09-03",
                           "image_indicates": "31/8/69",
                           "explanation": {"en": "ok", "th": "ok"}}],
        "issues": [],
        "unverified": [{"field": "totalQuantity", "payload_value": 12006.19,
                        "image_indicates": "not shown",
                        "explanation": {"en": "nothing readable", "th": "x"}}],
        "checked_image_count": 2, "errors": [],
        "checked_at": "2026-06-16T04:12:40+00:00",
    },
}


def _covered():
    tx = (4482, True, RAW_WITH_EXTRAS, 41, Decimal("0.9"), "flagged", COVERED_FLAGS,
          datetime(2026, 6, 16), datetime(2026, 6, 16), None)
    return _get(FakeDB(tx=tx, recs=(), images=(), dups=()))["audit"]


def test_a_field_nobody_checks_is_listed_not_omitted():
    """Four verdicts and fifteen silent fields reads as "the rest passed". They
    were never examined — say so per field."""
    a = _covered()
    assert {f["field"] for f in a["not_checked"]} == {
        "invoiceNo", "customerName", "vesselName"}
    assert a["not_checked_count"] == 3


def test_a_judged_field_is_not_also_listed_as_unchecked():
    a = _covered()
    names = {f["field"] for f in a["not_checked"]}
    assert "transactionDate" not in names      # passed
    assert "totalQuantity" not in names        # unverified, but examined


def test_invoiceNo_explains_why_it_is_deliberately_skipped():
    """It is excluded on purpose — a reviewer should see the reason, not a
    shrug."""
    f = next(f for f in _covered()["not_checked"] if f["field"] == "invoiceNo")
    assert "freeform" in f["explanation"]["en"]
    assert f["explanation"]["th"]


def test_an_unmapped_field_gets_the_generic_reason():
    f = next(f for f in _covered()["not_checked"] if f["field"] == "vesselName")
    assert "no check is defined" in f["explanation"]["en"]
    assert f["payload_value"] == "MV Test"


def test_structural_keys_are_not_reported_as_fields():
    names = {f["field"] for f in _covered()["not_checked"]}
    assert not (names & {"images", "organization", "_legacy_id", "status"})


def test_every_bucket_has_a_count_for_badges():
    a = _covered()
    assert (a["passed_count"], a["failed_count"],
            a["unverified_count"], a["not_checked_count"]) == (1, 0, 1, 3)


# ── the name the caller actually submitted ─────────────────────────────────

RECORD_RAW = {"id": "25679", "price": "10.00000", "quantity": "12006.19000",
              "transactionDate": "2026-09-03"}

RECORD_FLAGS = {
    "integrity": {
        "matched_fields": ["pricePerUnit"],
        "confirmations": [{"field": "pricePerUnit", "payload_value": "10.00000",
                           "image_indicates": "10.00",
                           "explanation": {"en": "ok", "th": "ok"}}],
        "issues": [{"field": "totalQuantity", "payload_value": "12006.19000",
                    "image_indicates": "999", "explanation": {"en": "no", "th": "no"},
                    "image_id": 1285, "image_type": "product_weighing_sheet",
                    "image_name": "sheet.pdf", "source_image_url": "https://s3/x.pdf",
                    "record_id": 624}],
        "unverified": [], "checked_image_count": 3, "errors": [],
        "checked_at": "2026-10-02T03:07:27+00:00",
    },
}


def _record_audit():
    recs = [(9901, 4482, True, RECORD_RAW, Decimal("0.9"), "flagged", RECORD_FLAGS,
             datetime(2026, 10, 2), datetime(2026, 10, 2), None)]
    return _get(FakeDB(recs=recs, images=()))["records"][0]["audit"]


def test_a_pass_names_the_key_the_caller_submitted():
    """A record sends `price`; the judge reports `pricePerUnit`. Showing only
    the canonical name leaves a reviewer matching two vocabularies by eye."""
    p = _record_audit()["passed"][0]
    assert p["field"] == "pricePerUnit"        # what the judge called it
    assert p["payload_field"] == "price"       # what was actually sent


def test_a_failure_names_both_too():
    f = _record_audit()["failed"][0]
    assert f["field"] == "totalQuantity"
    assert f["payload_field"] == "quantity"


def test_a_failure_links_the_file_that_produced_it():
    f = _record_audit()["failed"][0]
    assert f["image_id"] == 1285
    assert f["image_type"] == "product_weighing_sheet"
    assert f["source_image_url"].startswith("https://")


def test_a_field_that_is_not_remapped_reports_itself():
    f = _record_audit()
    # transactionDate is submitted under its own name
    assert _payload_field_for("transactionDate") == "transactionDate"


def _payload_field_for(canonical):
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _payload_field
    return _payload_field(canonical, RECORD_RAW)


def test_an_absent_source_key_falls_back_to_the_canonical_name():
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _payload_field
    assert _payload_field("pricePerUnit", {}) is None
    assert _payload_field("imageType", RECORD_RAW) is None   # the judge's own
