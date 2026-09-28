"""The key-values that identify each document type, one entry per slot name.

This is the single place to edit when a slot mis-classifies. Keys do two jobs
at once, and the double duty is the point:

  1. IDENTITY — a file must print half of a slot's keys to claim that slot.
  2. DATA — a key named exactly like a value field in the request ("invoiceNo",
     "transactionDate", "weight") fills that field straight from the file that
     claimed the slot. One read, in STEP 1, off the authoritative document.

So keys are written in the frontend's own field names wherever the two
correspond, and in plain description where they do not. The plain ones are not
dead weight: "seller tax id" and "tare weight" are what actually separate a
tax invoice from an invoice and a weighbridge ticket from a scale photo. The
form-named keys are mostly shared across document types, so a set carried only
by them cannot discriminate.

  Keep at least two keys that ONLY this document type prints.

Only ATOMIC doc types live here. A slash-separated slot
("invoice/tax_invoice/cash_bill") resolves to its parts and matches if a file
looks like ANY ONE of them — so composites need no entry of their own.

A slot with no entry here (and no explicit "keys" in the request) keeps the
old behaviour: the model picks the file for it. That is the right answer for
photos, which print nothing to match on.

If the frontend renames a value field, the matching key here quietly stops
filling it (it still identifies). ocr.py logs a warning when a request's value
fields overlap none of these — that is the signal the names have drifted.
"""

from typing import Dict, List

# Value-field names the frontend sends, and which of them a key here can fill.
# Renaming one on the frontend means renaming it here.
#   transaction: invoiceNo, transactionDate, weight
#   record:      weight, totalPrice, transactionDate
# NOT fillable, so no key is ever named after them:
#   sorter, Labelling, Baling, colour — "select-one"/"tags" types. The user
#     picks these in the UI; ocr.py keeps them out of the prompt and returns
#     them null (see _USER_CHOICE_TYPES).
#   pricePerUnit — computed as totalPrice / weight (see _derive_price_per_unit).

SLOT_KEYS: Dict[str, List[str]] = {
    # ── commercial documents ────────────────────────────────────────────────
    # These five share invoiceNo/transactionDate/totalPrice, so each one's
    # last keys are doing all the discriminating.
    #
    # The three that ITEMISE also carry "weight" and "pricePerUnit": the line
    # shows the BILLED quantity and unit price, which is what the form means.
    # On a project with a quality deduction those differ from the weighing
    # sheet — measured on project 48, the scale said 9,230 kg and the invoice
    # billed 8,583 kg at 15.75. Reading the scale gave a 7% error on a
    # compliance figure, so the invoice takes precedence (see ocr.py, where
    # transaction-level slots are offered to record fields first).
    "invoice": [
        "invoiceNo", "transactionDate", "weight", "pricePerUnit",
        "grand total for the whole invoice",
        "seller or supplier name", "buyer or customer name",
    ],
    "tax_invoice": [
        "invoiceNo", "transactionDate", "weight", "pricePerUnit",
        "grand total for the whole invoice",
        "seller tax id", "buyer tax id", "vat amount",
    ],
    "cash_bill": [
        "invoiceNo", "transactionDate", "weight", "pricePerUnit",
        "grand total for the whole invoice",
        "seller or shop name", "cash payment marking",
    ],
    "receipt": [
        "invoiceNo", "transactionDate", "totalPrice",
        "received from", "receiver signature",
    ],
    "payment_voucher": [
        "invoiceNo", "transactionDate", "totalPrice",
        "payee name", "approver signature", "account or expense code",
    ],
    "money_transfer_document": [
        "transactionDate", "totalPrice",
        "sender account or name", "receiver account or name",
        "bank name", "transaction reference number",
    ],

    # ── logistics / quality ─────────────────────────────────────────────────
    "bill_of_lading": [
        "transactionDate", "weight",
        "bill of lading or consignment number", "consignor or shipper",
        "consignee or receiver", "vehicle or vessel identifier",
    ],
    # Measured on 42 real QC files (projects 41 + 43): "qc or inspection report
    # number" appeared on 1 and "pass or fail result" on 0. Both only inflated
    # the denominator, pushing genuine QC files under the coverage threshold —
    # dropping them took this slot from 27/42 to 35/42 on replay.
    "qc_file": [
        "transactionDate", "material or lot number",
        "test or measurement result", "inspector name or signature",
    ],

    # ── weighing ────────────────────────────────────────────────────────────
    # "weight" here is the NET weight — the number the form wants. Tare is the
    # discriminator: only a real weighbridge ticket prints one.
    "product_weighing_sheet": [
        "weight", "transactionDate",
        "weighing ticket or slip number", "gross weight", "tare weight",
        "vehicle plate number",
    ],
    # A photo of a scale display: almost nothing is printed, so the set is
    # small on purpose — one clear reading is enough to claim the slot.
    "product_weighing_image": [
        "weight", "weight unit shown on the scale display",
    ],

    # ── production reporting ────────────────────────────────────────────────
    # Measured on a real upload: what arrives here is a MONTHLY RECEIVING
    # report — "รายงานรับกล่องเครื่องดื่มที่ใช้แล้ว ประจำเดือน สิงหาคม 2569",
    # a table of dated delivery rows — not a factory production report. The
    # original keys (input/output quantity, production line) described the
    # latter, so a real report scored 1/6 and the slot came back empty while
    # the file went nowhere. The many-rows key is the discriminator: an
    # invoice prints one transaction, a report prints a month of them.
    # NOTE the key names: "total weight for the whole period", NOT "weight".
    # A key named like a form field FILLS that field, and this report's weight
    # is a month's total (300,786 kg) while the form's `weight` is one
    # transaction (5,900 kg). Naming it "weight" put the month into the
    # transaction. When a document carries the same quantity at a different
    # granularity, give the key a different name so it stays identity-only.
    "production_report": [
        "reporting month and year",
        "a table listing many dated rows, one per delivery or batch",
        "product or material name",
        "total weight for the whole period",
        "grand total amount for the whole period",
    ],
    # Same trap as production_report: a monthly figure must not be named after
    # a per-transaction form field.
    "monthly_progress_report": [
        "reporting month and year",
        "planned quantity for the period", "actual quantity for the period",
        "cumulative total to date",
        "a table listing many dated rows",
    ],
    "production_other_report": [
        "transactionDate", "weight",
        "report title", "product or material name",
    ],

    # ── identity ────────────────────────────────────────────────────────────
    # Nothing on an id card fills a form field; it is identity-only.
    "id_card": [
        "identification number", "full name", "date of birth",
        "address", "issue or expiry date",
    ],

    # ponytail: no entry for product_image on purpose — a bare product photo
    # prints no key-values, so key matching cannot help. The model keeps
    # picking it, as it did before.
}


def keysets(slot_name: str, explicit: List[str] = None) -> List[List[str]]:
    """Key sets a file may match to claim this slot — one list per alternative.

    An explicit "keys" on the field wins outright (one alternative). Otherwise
    the slot name is split on "/" and each part looked up, so
    "invoice/tax_invoice" matches a file that looks like either one.
    """
    if explicit:
        return [list(explicit)]
    out = []
    for part in slot_name.split("/"):
        found = SLOT_KEYS.get(part.strip())
        if found:
            out.append(found)
    return out
