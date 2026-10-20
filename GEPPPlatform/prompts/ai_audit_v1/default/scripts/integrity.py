"""Deterministic integrity checks for audit evidence.

Numbers and dates do not need a language model. `925 == 925` is arithmetic, and
asking an LLM to do it buys a hallucination risk, a token bill and a different
answer on the next run. This module settles those columns in Python; the LLM is
left with what it is actually good at — fuzzy name matching ("ขวด PET" ≈
"Plastic PET Bottles") and writing the Thai explanation of a mismatch.

The second job here matters more than the speed. A column used to have two
states, `found` and `match`, so "the photo was too blurry to read" and "the
numbers disagree" both came out as a failed audit. They are not the same thing:

    MATCH         the evidence carries the value and it agrees
    MISMATCH      the evidence carries the value and it disagrees  -> real finding
    NOT_EXPECTED  no document here is supposed to carry this value -> not a fault
    UNREADABLE    a document that SHOULD carry it yielded nothing  -> human review

Telling the last two apart is what `extract_list` is for: it already declares
what each document type is meant to print, so we know whether a blank means
"wrong place to look" or "we failed to read it".
"""

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

MATCH = "match"
MISMATCH = "mismatch"
NOT_EXPECTED = "not_expected"
UNREADABLE = "unreadable"

# Record column -> the evidence field names that carry it, from the seeded
# extract_list of ai_audit_document_types. Add a name here when a new document
# type spells a field differently; an unmapped column simply falls through to
# the LLM, which is the old behaviour.
# Two vocabularies describe the same quantity. ai_audit_document_types uses
# weight_kg / price_per_unit / total / date; the OCR's doc_keys.SLOT_KEYS uses
# the frontend's field names, weight / pricePerUnit / totalPrice /
# transactionDate. Evidence can arrive in either, so both are listed — a
# document is not less readable for being described in the other dialect.
_COLUMN_EVIDENCE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "origin_weight_kg": ("weight_kg", "weight"),
    "weight_kg": ("weight_kg", "weight"),
    "origin_quantity": ("quantity",),
    "origin_price_per_unit": ("price_per_unit", "pricePerUnit"),
    "total_amount": ("total", "grand_total", "totalPrice"),
    "transaction_date": ("date", "transactionDate"),
}

# Columns a machine can settle. Everything else (material_id, origin_id,
# destination_id — all name matching) stays with the LLM.
DETERMINISTIC_COLUMNS = frozenset(_COLUMN_EVIDENCE_FIELDS)

# ponytail: 0% on numbers and an exact date, because that is what
# prompts/templates/transaction_evidence_matching.yaml already tells the LLM.
# Matching it means switching a column to the deterministic path cannot quietly
# change an audit outcome. NOTE: ai_audit_column_details.check_rules says "allow
# 5% tolerance" for these same columns and is never sent to that prompt — the
# two disagree today. Settle which one is policy, then change this constant.
NUMERIC_TOLERANCE = 0.0
_ROUND_DP = 2

# Documents for one delivery carry DIFFERENT dates by design, and the spread is
# not symmetric: paperwork FOLLOWS the goods. The material is weighed, then the
# invoice is cut, then it is paid. Given 11, 13, 14 and 16 December, the
# transaction happened on the 11th and the rest is settlement.
#
# So the earliest date anchors the transaction, and later dates are expected
# rather than tolerated — a payment three weeks after delivery is normal, not a
# discrepancy. What IS suspicious is a document dated BEFORE the transaction it
# belongs to: that is usually evidence from a different delivery.
#
# There is no upper bound, and a small allowance on the early side: the record
# is typed up AFTER the goods arrive, so QC and weighing routinely predate it.
# Measured over 112 real transactions, the earliest document sits this far
# before the record date:
#
#     1-4 days    45 transactions   <- normal lead time
#     5 days       1
#     11-30 days   6                <- suspicious
#     89/172/177   3                <- certainly the wrong file
#
# The gap between 5 and 11 is where the line goes. At 0 this rule flagged 49%
# of legitimate transactions; at 5 it passes all 46 normal cases and still
# catches the 9 outliers, including a weighing sheet 172 days off its record.
#
# ai_audit_column_details.check_rules says "within 3 days", which is never sent
# to the matching prompt and was never the live rule anyway.
BACKDATE_GRACE_DAYS = 5

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def to_number(value: Any) -> Optional[float]:
    """First number in a value, thousands separators and units stripped."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM_RE.search(str(value if value is not None else "").replace(",", ""))
    return float(m.group()) if m else None


# Month names, because documents write them as often as numbers — in English
# ("08-May-25") and in Thai ("5 มีนาคม 2568").
_MONTH_WORDS = {}
for _i, (_en, _th) in enumerate([
    ("january jan", "มกราคม ม.ค."), ("february feb", "กุมภาพันธ์ ก.พ."),
    ("march mar", "มีนาคม มี.ค."), ("april apr", "เมษายน เม.ย."),
    ("may", "พฤษภาคม พ.ค."), ("june jun", "มิถุนายน มิ.ย."),
    ("july jul", "กรกฎาคม ก.ค."), ("august aug", "สิงหาคม ส.ค."),
    ("september sep sept", "กันยายน ก.ย."), ("october oct", "ตุลาคม ต.ค."),
    ("november nov", "พฤศจิกายน พ.ย."), ("december dec", "ธันวาคม ธ.ค."),
], 1):
    for _w in (_en + " " + _th).split():
        _MONTH_WORDS[_w] = _i


def _year(y: int) -> int:
    """2568 and 68 are Buddhist, 2025 and 25 Gregorian. Pick whichever lands
    nearest today — a two-digit 69 is 2026, not 2069."""
    if y >= 2400:
        return y - 543
    if y >= 1900:
        return y
    now = datetime.now().year
    greg, bud = 2000 + y, 2500 + y - 543
    return greg if abs(greg - now) <= abs(bud - now) else bud


def to_date(value: Any) -> Optional[date]:
    """A date out of whatever a document actually printed.

    This used to accept only YYYY-MM-DD, on the assumption that the classifier
    normalises. It does not: real evidence comes back as "24/1/2026",
    "07/03/69", "5 มีนาคม 2568". Nothing parsed, so every date comparison fell
    through to mismatch and flagged paperwork that was in fact identical.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value or "").lower()
    named = [n for w, n in _MONTH_WORDS.items()
             if re.search(rf"(?<![a-z]){re.escape(w)}", text)]
    nums = [int(x) for x in re.findall(r"\d+", text)]

    if named and len(nums) >= 2:
        d, m, y = nums[0], named[0], nums[-1]
    elif len(nums) >= 3:
        d, m, y = nums[0], nums[1], nums[2]
        if d >= 1000:                     # yyyy-mm-dd
            d, m, y = nums[2], nums[1], nums[0]
        elif m > 12 and d <= 12:          # mm/dd/yyyy
            d, m = m, d
    else:
        return None
    try:
        return date(_year(y), m, d)
    except ValueError:
        return None


def collect_field(data: Any, names: Iterable[str]) -> List[Any]:
    """Every value stored under any of `names`, at any depth.

    extract_list nests — a receipt puts weight_kg inside a "materials" list —
    so the value we want is rarely at the top level. Blank entries are dropped
    so an explicit null reads the same as an absent key.
    """
    wanted = {n.strip().lower() for n in names}
    found: List[Any] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).strip().lower() in wanted and not _blank(v):
                    found.append(v)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v in ([], {})


def expects_column(column: str, extract_list: Any) -> bool:
    """Is this document type supposed to carry this column?

    Asked of the type's extract_list, which is the declaration of what the
    document prints. This is what separates "a waste photo has no invoice
    total" from "the receipt's total was unreadable".
    """
    fields = _COLUMN_EVIDENCE_FIELDS.get(column)
    if not fields:
        return False
    return bool(collect_field_names(extract_list) & {f.lower() for f in fields})


def collect_field_names(extract_list: Any) -> set:
    """Every field name declared in an extract_list, at any depth."""
    names = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                names.add(str(k).strip().lower())
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(extract_list)
    return names


def compare(column: str, evidence_values: List[Any], record_value: Any) -> Optional[Any]:
    """The evidence value that matches the record value, or None.

    Returns the matching VALUE rather than a bool so the caller can say what a
    pass was based on — "matched 8,583.00 on the tax invoice" is auditable,
    "true" is not.

    ANY, not all: one document legitimately lists several materials, so the
    right line only has to be present. Pinning the value to the RIGHT line is
    row-level integrity, which the LLM still does — see the note in check().
    """

    want = to_number(record_value)
    if want is None:
        return None
    for v in evidence_values:
        got = to_number(v)
        if got is None:
            continue
        if round(got, _ROUND_DP) == round(want, _ROUND_DP):
            return v
        if NUMERIC_TOLERANCE and abs(got - want) <= abs(want) * NUMERIC_TOLERANCE:
            return v
    return None


def check(
    column: str,
    record_value: Any,
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Settle one column against every evidence file. One of the four outcomes.

    `evidence` items are {'extracted_data': {...}, 'extract_list': {...}} —
    what the file actually yielded, and what its document type promised.

    Deliberately NOT done here: row-level integrity (does this weight sit on the
    same line as this material). That needs the material name matched first,
    which is fuzzy, so a match here means "the number is on the document"
    and the LLM still has to confirm it is on the right row.
    """
    fields = _COLUMN_EVIDENCE_FIELDS.get(column)
    if not fields:
        return {"outcome": None, "reason": "column is not machine-checkable",
                "evidence": None}

    if column.endswith("transaction_date"):
        return _check_date(column, record_value, evidence, fields)

    any_expected = False
    hits = []                 # (gap, evidence, value) — best one wins
    seen_values = []          # (file_id, doc type name, value) for the reason text
    for ev in evidence:
        expected = expects_column(column, ev.get("extract_list"))
        values = collect_field(ev.get("extracted_data"), fields)
        any_expected = any_expected or expected
        for v in values:
            seen_values.append((ev.get("file_id"), ev.get("document_type_name"), v))
        if values:
            hit = compare(column, values, record_value)
            if hit is not None:
                hits.append((_date_gap(column, hit, record_value), ev, hit))

    if hits:
        _gap, ev, hit = min(hits, key=lambda h: h[0])
        return {
            "outcome": MATCH,
            "evidence": {"file_id": ev.get("file_id"),
                         "document_type_name": ev.get("document_type_name"),
                         "value": hit},
            "reason": _passed_because(column, hit, record_value, ev),
        }

    if seen_values:
        shown = ", ".join(f"{d or 'file %s' % f}: {v}" for f, d, v in seen_values[:3])
        return {"outcome": MISMATCH, "evidence": None,
                "reason": f"{column}: record has {record_value!r}, evidence shows {shown}"}
    if any_expected:
        return {"outcome": UNREADABLE, "evidence": None,
                "reason": f"{column}: a document that should show this yielded nothing"}
    return {"outcome": NOT_EXPECTED, "evidence": None,
            "reason": f"{column}: no attached document type declares this field"}


def _check_date(column: str, record_value: Any, evidence: List[Dict],
                fields: Tuple[str, ...]) -> Dict[str, Any]:
    """The earliest document dates the transaction; later ones are settlement.

    Paperwork follows the goods, so the spread is one-sided. The earliest date
    across all the evidence is when the transaction happened, and the record
    must agree with it. Anything after is expected — an invoice cut two days
    later, a voucher paid three weeks later. Anything BEFORE the record's date
    is the real signal: a document that predates the transaction it is filed
    under usually belongs to a different delivery.
    """
    want = to_date(record_value)
    dated = []                # (date, raw value, evidence)
    any_expected = False
    for ev in evidence:
        any_expected = any_expected or expects_column(column, ev.get("extract_list"))
        for v in collect_field(ev.get("extracted_data"), fields):
            d = to_date(v)
            if d is not None:
                dated.append((d, v, ev))

    if not dated:
        if any_expected:
            return {"outcome": UNREADABLE, "evidence": None,
                    "reason": f"{column}: a document that should show this yielded nothing"}
        return {"outcome": NOT_EXPECTED, "evidence": None,
                "reason": f"{column}: no attached document type declares this field"}

    if want is None:
        return {"outcome": MISMATCH, "evidence": None,
                "reason": f"{column}: the record has no readable date"}

    earliest_d, earliest_v, earliest_ev = min(dated, key=lambda t: t[0])
    where = (earliest_ev.get("document_type_name")
             or f"file {earliest_ev.get('file_id')}")

    # One comparison decides it. "A document predates the record" and "the
    # record disagrees with its earliest document" are the same condition —
    # only the wording that helps a reviewer differs.
    gap = (want - earliest_d).days
    if gap > BACKDATE_GRACE_DAYS:
        return {
            "outcome": MISMATCH, "evidence": None,
            "reason": (f"{column}: the {where} is dated {earliest_v}, {gap} day(s) "
                       f"before the record's {record_value} — a document cannot "
                       f"predate the transaction it belongs to, so either the "
                       f"record is dated too late or this file belongs elsewhere"),
        }
    if gap < 0:
        # The record predates every document. Nothing was weighed, invoiced or
        # paid on the day it claims.
        return {
            "outcome": MISMATCH, "evidence": None,
            "reason": (f"{column}: the record says {record_value} but the earliest "
                       f"document is the {where} at {earliest_v}, {-gap} day(s) later "
                       f"— nothing supports the record's date"),
        }

    later = sorted({d for d, _, _ in dated if d > earliest_d})
    trail = (f", then {', '.join(str(d) for d in later)}" if later else "")
    lead = ("matching the record" if gap == 0 else
            f"{gap} day(s) before the record's {record_value}, within the normal "
            f"{BACKDATE_GRACE_DAYS}-day lead time")
    return {
        "outcome": MATCH,
        "evidence": {"file_id": earliest_ev.get("file_id"),
                     "document_type_name": earliest_ev.get("document_type_name"),
                     "value": earliest_v},
        "reason": (f"{column}: the {where} is the earliest document at {earliest_v}, "
                   f"{lead}{trail} — later paperwork is settlement"),
    }


def _date_gap(column: str, hit: Any, record_value: Any) -> int:
    """Days between a date hit and the record. 0 for non-date columns, so the
    first numeric match wins as before."""
    if not column.endswith("transaction_date"):
        return 0
    a, b = to_date(hit), to_date(record_value)
    return abs((a - b).days) if a and b else 0


def _passed_because(column: str, hit: Any, record_value: Any, ev: Dict) -> str:
    """Why this passed, in the same words a person would use to re-check it.

    A pass used to carry no explanation at all, so an approved audit could not
    be re-traced without re-running it. This names the document and the value.
    """
    where = ev.get("document_type_name") or f"file {ev.get('file_id')}"
    if column.endswith("transaction_date"):
        a, b = to_date(hit), to_date(record_value)
        if a and b and a != b:
            off = abs((a - b).days)
            return (f"{column}: {hit} on the {where}, {off} day(s) from the record's "
                    f"{record_value} — within the {DATE_TOLERANCE_DAYS}-day allowance "
                    f"documents are issued apart")
        return f"{column}: {hit} on the {where} matches the record"
    return f"{column}: {hit} on the {where} matches the record's {record_value}"
