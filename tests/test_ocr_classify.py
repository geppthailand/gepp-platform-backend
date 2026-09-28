"""File-slot classification is decided by extracted keys, not by the model."""

import sys
import types

# ocr.py pulls in the whole GEPPPlatform package (db, boto, openrouter) at
# import time; none of it is needed to exercise _classify.
for name, attrs in [
    ("GEPPPlatform.libs.exceptions", {"BadRequestException": type("BadRequestException", (Exception,), {})}),
    ("GEPPPlatform.libs.image_processing", {"safe_process_image": lambda url: url}),
    ("GEPPPlatform.libs.openrouter", {"OCR_MODEL": "x", "call_llm": lambda *a, **k: None}),
]:
    sys.modules.setdefault(name, types.SimpleNamespace(**attrs))

from GEPPPlatform.services.cores.epr_ai_audit.api.ocr import _classify, _declared_keys

INVOICE = {"name": "invoice", "type": "file", "keys": ["invoice no", "seller tax id", "total amount"]}
WEIGHING = {"name": "weighing_sheet", "type": "file", "keys": ["ticket no", "gross weight", "tare weight"]}
PHOTO = {"name": "product_image", "type": "file"}  # no keys -> model keeps deciding

INVENTORY = [
    {"index": 0, "doc_type": "weighbridge", "keys": {"ticket no": "W-77", "gross weight": "12,340", "tare weight": "3,100"}},
    {"index": 1, "doc_type": "photo", "keys": {}},
    {"index": 2, "doc_type": "tax invoice", "keys": {"invoice no": "INV-1", "seller tax id": "013", "total amount": "8,000"}},
]


def test_keys_decide_the_slot_not_file_order():
    got = _classify(INVENTORY, [INVOICE, WEIGHING, PHOTO], [0, 1, 2], set())
    assert got == {"invoice": 2, "weighing_sheet": 0}, got


def test_keyless_slots_are_left_to_the_model():
    assert _classify(INVENTORY, [PHOTO], [0, 1, 2], set()) == {}


def test_weak_match_leaves_the_slot_empty():
    inv = [{"index": 0, "keys": {"invoice no": "INV-1"}}]  # 1 of 3 = under 0.5
    assert _classify(inv, [INVOICE], [0], set()) == {"invoice": None}


def test_blank_values_do_not_count_as_a_key():
    inv = [{"index": 0, "keys": {"invoice no": "INV-1", "seller tax id": "", "total amount": None}}]
    assert _classify(inv, [INVOICE], [0], set()) == {"invoice": None}


def test_one_file_never_fills_two_slots():
    both = {"name": "any_doc", "type": "file", "keys": ["ticket no", "gross weight"]}
    used = set()
    got = _classify(INVENTORY, [WEIGHING, both], [0, 1, 2], used)
    assert sorted(v for v in got.values() if v is not None) == [0]
    assert used == {0}


def test_used_files_carry_across_records():
    used = {0}
    assert _classify(INVENTORY, [WEIGHING], [0, 1, 2], used) == {"weighing_sheet": None}


def test_candidate_pool_scopes_the_search():
    assert _classify(INVENTORY, [INVOICE], [0, 1], set()) == {"invoice": None}


def test_declared_keys_dedupes_in_order():
    dup = {"name": "b", "type": "file", "keys": ["total amount", "note"]}
    assert _declared_keys([INVOICE, dup, PHOTO]) == [
        "invoice no", "seller tax id", "total amount", "note",
    ]


# ── the SLOT_KEYS table ────────────────────────────────────────────────────

from GEPPPlatform.services.cores.epr_ai_audit.api.doc_keys import SLOT_KEYS, keysets

# Every slot name the platform uses. product_image is deliberately keyless.
PLATFORM_SLOTS = [
    "invoice", "bill_of_lading", "qc_file", "receipt", "cash_bill",
    "payment_voucher", "tax_invoice", "id_card",
    "invoice/receipt/cash_bill/payment_voucher",
    "invoice/tax_invoice/cash_bill/payment_voucher/id_card",
    "money_transfer_document", "production_report", "monthly_progress_report",
    "production_other_report", "product_weighing_sheet",
    "product_weighing_sheet/product_weighing_image", "product_image",
]


def test_every_platform_slot_resolves_except_photos():
    unresolved = [s for s in PLATFORM_SLOTS if not keysets(s)]
    assert unresolved == ["product_image"], unresolved


def test_composite_slot_offers_one_keyset_per_alternative():
    assert keysets("invoice/tax_invoice/cash_bill/payment_voucher/id_card") == [
        SLOT_KEYS["invoice"], SLOT_KEYS["tax_invoice"], SLOT_KEYS["cash_bill"],
        SLOT_KEYS["payment_voucher"], SLOT_KEYS["id_card"],
    ]


def test_request_keys_override_the_table():
    assert keysets("invoice", ["only this"]) == [["only this"]]


def test_composite_matches_on_its_best_alternative_alone():
    # An id card shares nothing with an invoice; the slot must still take it
    # via the id_card alternative rather than failing on a unioned key list.
    slot = {"name": "invoice/tax_invoice/cash_bill/payment_voucher/id_card", "type": "file"}
    inv = [{"index": 0, "keys": {k: "x" for k in SLOT_KEYS["id_card"]}}]
    assert _classify(inv, [slot], [0], set()) == {slot["name"]: 0}


def test_tax_invoice_beats_plain_invoice_on_a_taxed_document():
    inv = [{"index": 0, "keys": {k: "x" for k in SLOT_KEYS["tax_invoice"]}}]
    got = _classify(inv, [{"name": "tax_invoice", "type": "file"},
                          {"name": "invoice", "type": "file"}], [0], set())
    assert got == {"tax_invoice": 0, "invoice": None}


def test_keyless_slot_loses_a_file_a_keyed_slot_claimed():
    from GEPPPlatform.services.cores.epr_ai_audit.api.ocr import _dedupe_slots
    fields = [{"name": "product_weighing_sheet", "type": "file"},
              {"name": "product_image", "type": "file"}]
    obj = {"product_weighing_sheet": "u0", "product_image": "u0"}
    _dedupe_slots(obj, fields)
    assert obj == {"product_weighing_sheet": "u0", "product_image": None}


def test_dedupe_leaves_distinct_files_alone():
    from GEPPPlatform.services.cores.epr_ai_audit.api.ocr import _dedupe_slots
    fields = [{"name": "product_weighing_sheet", "type": "file"},
              {"name": "product_image", "type": "file"}]
    obj = {"product_weighing_sheet": "u0", "product_image": "u1"}
    _dedupe_slots(obj, fields)
    assert obj == {"product_weighing_sheet": "u0", "product_image": "u1"}


# ── end to end: the real frontend payload, a stubbed model ─────────────────

import json

import GEPPPlatform.services.cores.epr_ai_audit.api.ocr as ocr

FIELDS = [
    {"name": "invoiceNo", "type": "text"},
    {"name": "transactionDate", "type": "text"},
    {"name": "sorter", "type": "select-one"},
    {"name": "weight", "type": "text"},
    {"name": "invoice/tax_invoice/cash_bill/payment_voucher/id_card", "type": "file", "required": True},
    {"name": "money_transfer_document", "type": "file", "required": True},
    {"name": "production_report", "type": "file", "required": False},
    {"record_field": [
        {"name": "weight", "type": "text"},
        {"name": "pricePerUnit", "type": "text"},
        {"name": "totalPrice", "type": "text"},
        {"name": "transactionDate", "type": "text"},
        {"name": "Baling", "type": "tags", "options": ["Non-Baled", "Baled"]},
        {"name": "qc_file", "type": "file", "required": True},
        {"name": "product_weighing_sheet", "type": "file", "required": True},
        {"name": "product_image", "type": "file", "required": True},
    ]},
]

URLS = ["u0", "u1", "u2", "u3", "u4"]

# u0 tax invoice, u1 transfer slip, u2 weighbridge ticket, u3 qc, u4 photo.
# The model is made to get STEP 2 WRONG on purpose — wrong slots, and an
# invoiceNo copied off the transfer slip — so the test shows the key matching
# overriding it rather than merely agreeing with it.
MODEL_REPLY = {
    "files": [
        {"index": 0, "doc_type": "tax invoice", "keys": {
            "invoiceNo": "INV-2024-001", "transactionDate": "2024-03-01",
            "totalPrice": "85,600", "seller tax id": "0105536000021",
            "buyer tax id": "0107537000123", "vat amount": "5,600"}},
        {"index": 1, "doc_type": "transfer slip", "keys": {
            "transactionDate": "2024-03-02", "totalPrice": "85,600",
            "sender account or name": "SCB 1234", "receiver account or name": "KBANK 9876",
            "bank name": "SCB", "transaction reference number": "TRF889900"}},
        {"index": 2, "doc_type": "weighbridge ticket", "keys": {
            "weight": "9,240", "transactionDate": "2024-03-01",
            "weighing ticket or slip number": "WB-5521",
            "gross weight": "12,340", "tare weight": "3,100",
            "vehicle plate number": "70-1234"}},
        {"index": 3, "doc_type": "qc report", "keys": {
            "transactionDate": "2024-03-01", "qc or inspection report number": "QC-88",
            "material or lot number": "LOT-12", "test or measurement result": "99.1%",
            "pass or fail result": "PASS", "inspector name or signature": "S. Boon"}},
        {"index": 4, "doc_type": "material photo", "keys": {}},
    ],
    "transaction": {
        "invoiceNo": "TRF889900",          # wrong: read off the transfer slip
        "transactionDate": "2024-03-02",   # wrong: the transfer date
        "sorter": "Line A",
        "weight": None,
        "invoice/tax_invoice/cash_bill/payment_voucher/id_card": 1,  # wrong file
        "money_transfer_document": 0,                                # wrong file
        "production_report": 3,                                      # no such doc
    },
    "records": [{
        "file_indices": [2, 3, 4],
        "weight": "12,340",              # wrong: gross, not net
        "pricePerUnit": "9.26",
        "totalPrice": "85,600",
        "transactionDate": "2024-03-01",
        "Baling": "Baled",
        "qc_file": 4,                    # wrong file
        "product_weighing_sheet": 4,     # wrong file
        "product_image": 2,              # wrong file
    }],
}


def _read(monkeypatch, reply):
    monkeypatch.setattr(ocr, "safe_process_image", lambda url: url)
    monkeypatch.setattr(ocr, "call_llm",
                        lambda *a, **k: {"content": json.dumps(reply)})
    return ocr.read_transaction(URLS, FIELDS)


def test_slots_are_corrected_from_the_keys(monkeypatch):
    out = _read(monkeypatch, MODEL_REPLY)
    txn, rec = out["transaction"], out["records"][0]
    assert txn["invoice/tax_invoice/cash_bill/payment_voucher/id_card"] == "u0"
    assert txn["money_transfer_document"] == "u1"
    assert txn["production_report"] is None      # no production report was sent
    assert rec["product_weighing_sheet"] == "u2"
    assert rec["qc_file"] == "u3"


def test_values_come_from_the_file_that_won_the_slot(monkeypatch):
    out = _read(monkeypatch, MODEL_REPLY)
    txn, rec = out["transaction"], out["records"][0]
    assert txn["invoiceNo"] == "INV-2024-001"     # the tax invoice, not the slip
    assert txn["transactionDate"] == "2024-03-01"
    assert rec["weight"] == "9,240"               # net off the ticket, not gross


def test_user_choice_fields_come_back_null_for_the_frontend(monkeypatch):
    out = _read(monkeypatch, MODEL_REPLY)
    # the model echoed values for both; they are the user's to pick, so the
    # echo is discarded rather than passed off as read from a document
    assert out["transaction"]["sorter"] is None
    assert out["records"][0]["Baling"] is None


def test_user_choice_fields_are_never_shown_to_the_model():
    prompt = ocr._build_txn_prompt([f for f in FIELDS if "name" in f],
                                   FIELDS[-1]["record_field"], 5)
    assert "sorter" not in prompt
    assert "Baling" not in prompt
    assert "Non-Baled" not in prompt
    assert "invoiceNo" in prompt      # ordinary value fields still are


def test_price_per_unit_is_computed_not_read(monkeypatch):
    rec = _read(monkeypatch, MODEL_REPLY)["records"][0]
    # 85,600 / 9,240 net — not the model's "9.26" string, and not derived from
    # the gross weight the model originally put in the weight field
    assert rec["pricePerUnit"] == 9.26
    assert rec["weight"] == "9,240"


def test_price_per_unit_keeps_the_read_value_when_it_cannot_divide(monkeypatch):
    reply = json.loads(json.dumps(MODEL_REPLY))
    reply["files"][2]["keys"].pop("weight")          # no net weight anywhere
    reply["records"][0]["weight"] = None
    reply["records"][0]["pricePerUnit"] = "9.26"
    rec = _read(monkeypatch, reply)["records"][0]
    assert rec["pricePerUnit"] == "9.26"


def test_num_parses_separators_and_units():
    assert ocr._num("85,600") == 85600.0
    assert ocr._num("9,240 kg") == 9240.0
    assert ocr._num(1234) == 1234.0
    assert ocr._num("") is None
    assert ocr._num(None) is None
    assert ocr._num("n/a") is None


def test_the_photo_keeps_the_only_file_left(monkeypatch):
    rec = _read(monkeypatch, MODEL_REPLY)["records"][0]
    # u2 went to the weighing sheet, so the model's product_image=u2 is cleared
    # rather than handing the same file back under two slots.
    assert rec["product_image"] is None
    assert len({rec["qc_file"], rec["product_weighing_sheet"]}) == 2


# ── the inventory must line up with the files ──────────────────────────────

def test_a_multipage_pdf_split_into_two_entries_is_caught():
    """A multi-page PDF tempts the model into one entry per page. That shifts
    every index after it, so a slot silently resolves to a neighbouring
    document — the failure that put a payment voucher out of range and left the
    invoice slot empty on a real 5-file upload."""
    inv = [
        {"index": 0, "doc_type": "qc"},
        {"index": 1, "doc_type": "weighbridge"},
        {"index": 2, "doc_type": "photo"},
        {"index": 3, "doc_type": "report", "keys": {"a": "rows 1 to 18"}},
        {"index": 4, "doc_type": "report", "keys": {"a": "rows 19 to 27"}},
        {"index": 5, "doc_type": "payment voucher"},      # past the end
    ]
    kept = ocr._check_inventory(inv, 5)
    assert [e["index"] for e in kept] == [0, 1, 2, 3, 4]
    assert all(e["index"] < 5 for e in kept)


def test_duplicate_indices_are_dropped():
    inv = [{"index": 0}, {"index": 0}, {"index": 1}]
    assert [e["index"] for e in ocr._check_inventory(inv, 2)] == [0, 1]


def test_a_clean_inventory_passes_through():
    inv = [{"index": i, "doc_type": "x"} for i in range(4)]
    assert ocr._check_inventory(inv, 4) == inv


def test_junk_entries_do_not_crash_it():
    inv = [{"index": 0}, "nonsense", {"index": None}, {"index": True},
           {"no_index": 1}, {"index": -1}, {"index": 9}]
    assert [e["index"] for e in ocr._check_inventory(inv, 2)] == [0]


def test_the_prompt_demands_one_entry_per_file():
    prompt = ocr._build_txn_prompt([{"name": "invoice", "type": "file"}], [], 5)
    assert "EXACTLY 5 entries" in prompt
    assert "multi-page document is ONE file" in prompt


# ── billed quantity beats the weighing sheet ───────────────────────────────

INVOICE_SPEC = {"name": "invoice/tax_invoice", "type": "file"}
SHEET_SPEC = {"name": "product_weighing_sheet", "type": "file"}

# Real numbers from project 48 txn 139244: the scale weighed 9,230 kg, the
# invoice billed 8,583 kg at 15.75 after a 7% quality deduction.
DEDUCTION_REPLY = {
    "files": [
        {"index": 0, "doc_type": "tax invoice", "keys": {
            "invoiceNo": "P202511038", "transactionDate": "2025-11-18",
            "totalPrice": "135,182.25", "weight": "8,583.00", "pricePerUnit": "15.75",
            "seller tax id": "0205564020764", "buyer tax id": "0745560007017",
            "vat amount": "9,462.76"}},
        {"index": 1, "doc_type": "weighbridge", "keys": {
            "weighing ticket or slip number": "0000059624",
            "transactionDate": "2025-11-18", "gross weight": "14,850",
            "tare weight": "5,620", "weight": "9,230",
            "vehicle plate number": "71-8163"}},
    ],
    "transaction": {"invoiceNo": None, "invoice/tax_invoice": None},
    "records": [{"file_indices": [0, 1], "weight": "9,230", "pricePerUnit": "99",
                 "totalPrice": "135,182.25", "product_weighing_sheet": None}],
}

DEDUCTION_FIELDS = [
    {"name": "invoiceNo", "type": "text"},
    INVOICE_SPEC,
    {"record_field": [
        {"name": "weight", "type": "text"},
        {"name": "pricePerUnit", "type": "text"},
        {"name": "totalPrice", "type": "text"},
        SHEET_SPEC,
    ]},
]


def _read_deduction(monkeypatch, reply=None):
    monkeypatch.setattr(ocr, "safe_process_image", lambda url: url)
    monkeypatch.setattr(ocr, "call_llm",
                        lambda *a, **k: {"content": json.dumps(reply or DEDUCTION_REPLY)})
    return ocr.read_transaction(["u0", "u1"], DEDUCTION_FIELDS)


def test_the_invoices_billed_quantity_wins_over_the_scale(monkeypatch):
    """Both numbers are on documents and both are correct readings. The form
    means the billed weight; taking the scale's was a 7% error."""
    rec = _read_deduction(monkeypatch)["records"][0]
    assert ocr._num(rec["weight"]) == 8583.0        # invoice, not 9230 from the scale


def test_a_printed_unit_price_is_not_recomputed(monkeypatch):
    rec = _read_deduction(monkeypatch)["records"][0]
    assert ocr._num(rec["pricePerUnit"]) == 15.75   # as printed, not 135182.25/8583


def test_the_weighing_sheet_still_fills_weight_when_the_invoice_does_not(monkeypatch):
    reply = json.loads(json.dumps(DEDUCTION_REPLY))
    reply["files"][0]["keys"].pop("weight")          # invoice without a line quantity
    reply["files"][0]["keys"].pop("pricePerUnit")
    rec = _read_deduction(monkeypatch, reply)["records"][0]
    assert ocr._num(rec["weight"]) == 9230.0         # falls back to the scale


def test_an_unprinted_unit_price_is_still_computed(monkeypatch):
    """Arithmetic still beats the model's STEP 2 guess when no document says."""
    reply = json.loads(json.dumps(DEDUCTION_REPLY))
    reply["files"][0]["keys"].pop("pricePerUnit")
    rec = _read_deduction(monkeypatch, reply)["records"][0]
    assert rec["pricePerUnit"] == round(135182.25 / 8583, 2)   # not the model's "99"
