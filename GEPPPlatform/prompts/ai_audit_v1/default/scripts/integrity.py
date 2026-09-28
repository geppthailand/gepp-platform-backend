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
_COLUMN_EVIDENCE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "origin_weight_kg": ("weight_kg",),
    "weight_kg": ("weight_kg",),
    "origin_quantity": ("quantity",),
    "origin_price_per_unit": ("price_per_unit",),
    "total_amount": ("total", "grand_total"),
    "transaction_date": ("date",),
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

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def to_number(value: Any) -> Optional[float]:
    """First number in a value, thousands separators and units stripped."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM_RE.search(str(value if value is not None else "").replace(",", ""))
    return float(m.group()) if m else None


def to_date(value: Any) -> Optional[date]:
    """An ISO-ish date out of a value. Evidence dates are extracted as
    YYYY-MM-DD by the classifier prompt, and record dates are already formatted
    that way, so this stays deliberately strict — anything looser belongs in the
    OCR layer, not in a comparison."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(value or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
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


def compare(column: str, evidence_values: List[Any], record_value: Any) -> bool:
    """Do any of the evidence values equal the record value?

    ANY, not all: one document legitimately lists several materials, so the
    right line only has to be present. Pinning the value to the RIGHT line is
    row-level integrity, which the LLM still does — see the note in check().
    """
    if column == "transaction_date":
        want = to_date(record_value)
        return want is not None and any(to_date(v) == want for v in evidence_values)

    want = to_number(record_value)
    if want is None:
        return False
    for v in evidence_values:
        got = to_number(v)
        if got is None:
            continue
        if round(got, _ROUND_DP) == round(want, _ROUND_DP):
            return True
        if NUMERIC_TOLERANCE and abs(got - want) <= abs(want) * NUMERIC_TOLERANCE:
            return True
    return False


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
        return {"outcome": None, "reason": "column is not machine-checkable"}

    any_expected = False
    any_value = False
    for ev in evidence:
        expected = expects_column(column, ev.get("extract_list"))
        values = collect_field(ev.get("extracted_data"), fields)
        any_expected = any_expected or expected
        any_value = any_value or bool(values)
        if values and compare(column, values, record_value):
            return {"outcome": MATCH, "reason": None}

    if any_value:
        return {"outcome": MISMATCH,
                "reason": f"{column}: evidence carries a value that differs from the record"}
    if any_expected:
        return {"outcome": UNREADABLE,
                "reason": f"{column}: a document that should show this yielded nothing"}
    return {"outcome": NOT_EXPECTED,
            "reason": f"{column}: no attached document type declares this field"}
