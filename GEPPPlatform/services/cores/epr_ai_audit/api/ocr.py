"""OCR readers: a dump of files -> a filled form.

Two forms are supported, sharing the same guts (load files -> vision LLM ->
fill fields -> route file-slots back to URLs by index):

  read_transaction()  transaction with repeating RECORDS (materials/line items)
  read_audit()        flat fields grouped by SECTION, no repetition

Files are sent in order; the model refers to them by 0-based index, and we
swap indices back to URLs here so the model never has to echo long URLs.

Which file lands in which slot is decided from key-values, not by the model:
doc_keys.SLOT_KEYS lists the identifying values each document type prints
("seller tax id", "tare weight"), the model only reports which of them it can
read off each file, and _classify() does the matching here in Python. A
request may override a slot with its own "keys". Slots with neither (a bare
product photo prints nothing to match on) keep the old model-decides path.
"""

import json
import logging
import re
from typing import Any, Dict, List

from GEPPPlatform.libs.exceptions import BadRequestException
from GEPPPlatform.libs.image_processing import safe_process_image
from GEPPPlatform.libs.openrouter import OCR_MODEL, call_llm

from .doc_keys import keysets

logger = logging.getLogger(__name__)


# ── shared helpers ─────────────────────────────────────────────────────────

# Field types the user picks in the UI — a dropdown, a tag chooser. Nothing on
# a document prints them, so the model is never shown them and never fills
# them. Add a type here if the frontend grows another chooser.
_USER_CHOICE_TYPES = {"select-one", "tags"}

# Computed, not read: a unit price is printed small if at all, and we already
# have both inputs. Renamed on the frontend? Rename it here too.
_PRICE_PER_UNIT, _TOTAL, _WEIGHT = "pricePerUnit", "totalPrice", "weight"


def _split(fields: List[Dict]) -> tuple[list, list]:
    """Return (value_fields, file_fields) from a flat field list.

    Value fields are the ones the model can read off a document, so
    user-choice fields are in NEITHER list — see _user_choice.
    """
    return (
        [f for f in fields
         if f.get("type") != "file" and f.get("type") not in _USER_CHOICE_TYPES],
        [f for f in fields if f.get("type") == "file"],
    )


def _user_choice(fields: List[Dict]) -> List[Dict]:
    """Fields the frontend must set. Returned null so the shape stays stable."""
    return [f for f in fields if f.get("type") in _USER_CHOICE_TYPES]


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(v) -> Any:
    """First number in a value, thousands separators and units stripped."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = _NUM.search(str(v if v is not None else "").replace(",", ""))
    return float(m.group()) if m else None


def _derive_price_per_unit(obj: Dict, read_from_document: set = None) -> None:
    """pricePerUnit = totalPrice / weight, as a FALLBACK, in place.

    An itemising invoice prints the unit price on the line, and a printed
    number beats a derived one: it is the figure the two parties agreed, and
    recomputing it only re-introduces whatever rounding the document already
    resolved. `read_from_document` is the set of fields _fill_from_keys took
    off a classified file, and those are left alone.

    Anything NOT read off a document is still computed, overwriting whatever
    the model put there in STEP 2 — arithmetic beats a guess.

    If either input is missing or the weight is zero, nothing changes — a
    divide that cannot be done is not a reason to blank a real reading.
    """
    if _PRICE_PER_UNIT not in obj or _PRICE_PER_UNIT in (read_from_document or ()):
        return
    total, weight = _num(obj.get(_TOTAL)), _num(obj.get(_WEIGHT))
    if total is None or not weight:
        return
    obj[_PRICE_PER_UNIT] = round(total / weight, 2)


def _keysets(field: Dict) -> List[List[str]]:
    """Key sets this slot can be claimed by — request override, else the table."""
    return keysets(field.get("name", ""), field.get("keys"))


def _describe(fields: List[Dict]) -> str:
    """One line per field for the prompt, noting allowed options if present."""
    lines = []
    for f in fields:
        line = f"  - {f['name']}"
        if f.get("options"):
            line += f" (one of: {', '.join(f['options'])})"
        if f.get("from"):
            line += f" [read this off the file in slot: {f['from']}]"
        if f.get("description"):
            line += f" — {f['description']}"
        lines.append(line)
    return "\n".join(lines) if lines else "  (none)"


def _slots(file_fields: List[Dict]) -> str:
    """One block per file-slot, spelling out which document types it accepts.

    Slot names are authored as slash-separated alternatives
    ("invoice/tax_invoice/cash_bill"), which the model reads as one opaque
    string unless we expand it. Expanding it is most of what stops a
    weighbridge ticket landing in the invoice slot.
    """
    lines = []
    for f in file_fields:
        lines.append(f"  - {f['name']}")
        accepts = [p.strip().replace("_", " ") for p in f["name"].split("/") if p.strip()]
        if len(accepts) > 1:
            lines.append(f"      accepts any ONE of: {', '.join(accepts)}")
        sets = _keysets(f)
        if len(sets) > 1:
            lines.append("      identified by ANY ONE of these key sets:")
        for ks in sets:
            lines.append(f"      · {', '.join(ks)}" if len(sets) > 1
                         else f"      identified by: {', '.join(ks)}")
        if f.get("description"):
            lines.append(f"      {f['description']}")
    return "\n".join(lines) if lines else "  (none)"


def _declared_keys(file_fields: List[Dict]) -> List[str]:
    """Every key name declared across the given file-slots, de-duped, in order."""
    out = []
    for f in file_fields:
        for ks in _keysets(f):
            for k in ks:
                if k not in out:
                    out.append(k)
    return out


def _inventory_block(n_files: int, keys: List[str]) -> str:
    """STEP 1 of both prompts: force the model to look at every file once.

    When slots declare keys, this is also where classification happens — the
    model only reports which keys it can actually read off each file, and
    _classify() picks the slot from that. So the instruction has to be about
    reading, not about guessing what the document is for.
    """
    if not keys:
        keys_block = '''      "summary": "<the identifiers actually printed on it: doc number, date,
                   weight, party names — so a later step can tell files apart>"'''
    else:
        keys_block = (
            '      "keys": {<of the keys listed below, ONLY those this file\n'
            "                actually prints, mapped to the value printed.\n"
            "                Omit a key entirely if it is not on this file —\n"
            "                do not invent it, do not carry it from another file>}"
        )

    block = f"""STEP 1 — INVENTORY EVERY FILE. Before filling anything, look at each
file once and say what it is. Output EXACTLY {n_files} entries, one per file, in
index order — including any that end up filling no slot.

A multi-page document is ONE file, not one entry per page. Read all of its
pages and describe it once, merging what you found. Splitting a file into two
entries shifts the index of every file after it, and those indices are how the
slots are resolved — so a split silently puts the wrong document in the wrong
slot. Never output more or fewer than {n_files} entries.

  "files": [
    {{"index": 0,
      "doc_type": "<what this document is: tax invoice, receipt, payment voucher,
                    weighbridge/weighing sheet, scale reading photo, material photo,
                    vehicle photo, id card, production report, other>",
{keys_block}}}
  ]"""
    if keys:
        block += "\n\n  Keys to look for across all files: " + ", ".join(keys)
        block += """
  Which slot each file belongs to is decided from these keys, not from your
  own judgement — so reading them accurately is the whole job of STEP 1."""
    return block


_GROUNDING_RULES = """- Do STEP 1 before STEP 2. Every slot you fill and every value you
  read must trace back to a file you inventoried.
- A file fills AT MOST ONE slot. Never put the same index in two slots.
- Put a file in a slot only if its doc_type is one the slot accepts. If no
  file matches, the slot is null — a wrong file is worse than an empty one.
- Where a slot lists "identified by" keys, a file belongs there only if it
  prints those keys. Report the keys honestly in STEP 1 and read that slot's
  values off that same file.
- Read each value off the file that actually shows it, and prefer the
  document that is the authoritative source for that field: document numbers
  and amounts from the invoice/receipt/voucher, weights from the weighing
  sheet or scale reading, plate numbers from the vehicle photo. Do not carry
  a value over from a file that merely mentions it in passing.
- If two files disagree on a value, take the authoritative one; if neither
  is clearly authoritative, return null.
- On an itemised document, a per-line key describes THAT LINE, not the whole
  document. "weight" and "pricePerUnit" are the line's quantity and unit
  price, and "totalPrice" is the line's own amount BEFORE VAT — not the
  invoice's grand total, and not the total including VAT. Report the grand
  total only under a key that says so.
- Where a document shows both a weighed amount and a billed amount (a scale
  ticket says 9,230 kg but the invoice bills 8,583 kg after a quality
  deduction), "weight" is the BILLED quantity — the one the line's price is
  multiplied by.
- An invoice may cover SEVERAL deliveries while this transaction is only one
  of them. Pick the ONE line that belongs here — the line whose quantity is
  closest to the weighing sheet's net weight, allowing for a few percent of
  quality deduction — and read weight, pricePerUnit and totalPrice off that
  single line. Never add the lines together, and never return several values
  joined into one string: one line, one number each."""


def _check_required(files: List[str], file_fields: List[Dict]) -> None:
    """Reject if fewer files than the number of required file-slots."""
    required = sum(1 for f in file_fields if f.get("required"))
    if len(files) < required:
        raise BadRequestException(
            f"Not enough files: {len(files)} provided, {required} required."
        )


def _load_data_urls(files: List[str]) -> tuple[list, list]:
    """Fetch + prep each file. Returns (data_urls, kept_urls) in parallel order.

    The two lists MUST stay index-parallel — the prompt numbers files by
    position and _resolve_indices maps the model's index back through
    kept_urls. Anything that makes one input file produce several entries
    (rasterizing a PDF into page images, say) has to append the source URL
    once per entry, or file-slots resolve to the wrong document silently.
    """
    data_urls, kept_urls = [], []
    for url in files:
        d = safe_process_image(url)
        if d is None:
            logger.warning("OCR: could not process file, skipping: %s", url)
            continue
        data_urls.append(d)
        kept_urls.append(url)
    if not data_urls:
        raise ValueError("No files could be fetched/processed.")
    return data_urls, kept_urls


# The library default (4096) is not enough here. A reasoning model spends most
# of that budget thinking — measured ~3,700 reasoning tokens against ~400 of
# actual content — and the JSON then cuts off mid-value. The inventory also
# grows with the file count. We are billed for what is produced, not for the
# ceiling, so the ceiling is set well clear of it.
# ponytail: a flat ceiling, not a reasoning cap. Measured worst case was 16,380
# output tokens for 1,887 chars of answer — ~14,500 of it reasoning. Billing is
# per token produced, so this ceiling costs nothing until a call needs it, but
# it does not stop the model burning tokens to think. If truncation comes back,
# cap the thinking instead: OpenRouter takes reasoning={"max_tokens": N}, which
# means threading extra_body through call_llm.
_MAX_OUTPUT_TOKENS = 32768


# ponytail: reasoning is left at full. effort="low" halves the latency (21.6s ->
# 11.2s measured) but costs real accuracy — on 20 real transactions it took
# slotting from 98.8% to 85.4% and values from 94% to 89%. The 30s gateway limit
# is solved by going async, not by making the model think less.
def _call_and_parse(prompt: str, data_urls: List[str]) -> Dict:
    result = call_llm(prompt, image_urls=data_urls, model=OCR_MODEL,
                      max_tokens=_MAX_OUTPUT_TOKENS)
    text = result["content"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Truncation looks exactly like malformed JSON from here, and the
        # difference matters: one is a token budget, the other is a prompt bug.
        usage = result.get("usage") or {}
        truncated = not text.endswith("}")
        logger.error(
            "OCR: model response did not parse (%s). truncated=%s usage=%s "
            "chars=%d tail=%r",
            exc, truncated, usage, len(text), text[-200:],
        )
        raise ValueError(
            f"OCR response {'was truncated' if truncated else 'was not valid JSON'} "
            f"({len(text)} chars, usage={usage})"
        ) from exc


# ponytail: a file must show at least half a slot's declared keys to land in
# it. One stray key match is not evidence, and an empty slot beats a wrong
# one. Lower it if slots start coming back empty on real documents.
_MIN_KEY_COVERAGE = 0.5


def _blank(v) -> bool:
    return v in (None, "", [], {}) or (isinstance(v, str) and not v.strip())


def _extracted(inventory: List[Dict]) -> Dict[int, Dict[str, Any]]:
    """{file index: {key (lowercased): value}} from STEP 1, blanks dropped.

    Keys are lowercased because the model echoes back the names we gave it and
    case drifts ("invoiceNo" -> "invoiceno"); callers match lowercased too.
    """
    out = {}
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        i = entry.get("index")
        if isinstance(i, bool) or not isinstance(i, int):
            continue
        out[i] = {
            str(k).strip().lower(): v
            for k, v in (entry.get("keys") or {}).items()
            if not _blank(v)
        }
    return out


def _classify(
    inventory: List[Dict],
    file_fields: List[Dict],
    candidates: List[int],
    used: set,
) -> Dict[str, Any]:
    """Decide file-slots from the keys STEP 1 read off each file.

    Returns {slot name: file index or None} covering only slots that declare
    "keys" — the rest are left to whatever the model picked. Greedy: the
    highest-coverage (slot, file) pair wins, then that slot and that file are
    both out of the running, so one file never fills two slots. `used` is
    mutated, which is how record-level slots stay exclusive across records.
    """
    keyed = [f for f in file_fields if _keysets(f)]
    if not keyed:
        return {}

    extracted = _extracted(inventory)
    seen = {i: set(ks) for i, ks in extracted.items()}

    scored = []
    for f in keyed:
        # A composite slot ("invoice/tax_invoice") matches on its BEST
        # alternative — a file need only look like one of them, so unioning
        # the key lists would just inflate the denominator and match nothing.
        alts = [[str(k).strip().lower() for k in ks] for ks in _keysets(f)]
        for i in candidates:
            if i in used:
                continue
            best = max(
                (sum(1 for k in want if k in seen.get(i, ())) / len(want), 0)
                for want in alts if want
            )[0] if any(alts) else 0
            if best >= _MIN_KEY_COVERAGE:
                scored.append((best, f["name"], i))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))

    out = {f["name"]: None for f in keyed}
    taken_slots = set()
    for _coverage, name, i in scored:
        if name in taken_slots or i in used:
            continue
        out[name] = i
        taken_slots.add(name)
        used.add(i)
    return out


def _apply_slots(obj: Dict, assigned: Dict[str, Any], urls: List[str]) -> None:
    """Overwrite the model's slot picks with the key-matched ones, in place."""
    for name, idx in assigned.items():
        obj[name] = urls[idx] if isinstance(idx, int) and 0 <= idx < len(urls) else None


def _dedupe_slots(obj: Dict, file_fields: List[Dict]) -> None:
    """One file, one slot. Key-matched slots win; a keyless slot the model
    filled with the same file is cleared.

    Without this, a file the model dropped into a keyless slot (product_image)
    could also be key-matched into a real one, and the same URL would come
    back under two slots.
    """
    ordered = ([f["name"] for f in file_fields if _keysets(f)]
               + [f["name"] for f in file_fields if not _keysets(f)])
    seen = set()
    for name in ordered:
        url = obj.get(name)
        if not url:
            continue
        if url in seen:
            obj[name] = None
        else:
            seen.add(url)


def _fill_from_keys(
    obj: Dict,
    value_fields: List[Dict],
    file_fields: List[Dict],
    assigned: Dict[str, Any],
    inventory: List[Dict],
) -> set:
    """Fill value fields from the file that claimed the slot declaring them.

    Returns the field names it filled, so a later step can tell a value read
    off a document from one the model guessed.

    A key named like a value field IS that field's value, already read in
    STEP 1 off the document we then classified. Taking it here is what makes
    "correct data from the correct file" a guarantee rather than a prompt
    instruction — it overrides whatever the model put there in STEP 2.

    Where several slots declare the same key (transactionDate is printed on an
    invoice AND on a weighing sheet), the first slot in field order wins, so
    the order of file-slots in the request is the tie-break.
    """
    wanted = {f["name"].strip().lower(): f["name"] for f in value_fields}
    if not wanted:
        return set()
    extracted = _extracted(inventory)
    filled = set()
    for f in file_fields:
        idx = assigned.get(f["name"])
        if not isinstance(idx, int):
            continue
        from_file = extracted.get(idx) or {}
        for ks in _keysets(f):
            for k in ks:
                lk = str(k).strip().lower()
                if lk in wanted and lk not in filled and lk in from_file:
                    obj[wanted[lk]] = from_file[lk]
                    filled.add(lk)
    return {wanted[lk] for lk in filled}


def _blank_user_choice(obj: Dict, fields: List[Dict]) -> None:
    """Null every user-choice field, in place.

    They are never put in the prompt, but the model can still echo a field
    name it saw in an example, so this is a hard reset rather than a default —
    a guessed dropdown value looks exactly like a confirmed one downstream.
    """
    for f in _user_choice(fields):
        obj[f["name"]] = None


def _warn_if_names_drifted(value_fields: List[Dict], file_fields: List[Dict]) -> None:
    """Loud when no value field name appears in any slot's keys.

    That means doc_keys.SLOT_KEYS and the frontend's field names no longer
    agree, so classification still works but nothing is filled from it — a
    silent downgrade to the old model-decides behaviour otherwise.
    """
    if not value_fields or not file_fields:
        return
    names = {f["name"].strip().lower() for f in value_fields}
    keys = {str(k).strip().lower() for f in file_fields for ks in _keysets(f) for k in ks}
    if keys and not (names & keys):
        logger.warning(
            "OCR: no value field name matches any slot key — doc_keys.SLOT_KEYS "
            "and the request's field names may have drifted apart. fields=%s",
            sorted(names),
        )


def _check_inventory(inventory: List[Dict], n_files: int) -> List[Dict]:
    """The inventory must have exactly one entry per file, or indices lie.

    A multi-page PDF tempts the model into one entry per page. That shifts the
    index of every file after it, so a slot resolves to a neighbouring document
    — silently, because an index in range still looks valid. Entries pointing
    past the end are dropped (they can only be wrong), and any mismatch is
    logged loudly because the surviving indices may also be shifted.
    """
    kept, seen = [], set()
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        i = entry.get("index")
        if isinstance(i, bool) or not isinstance(i, int) or not (0 <= i < n_files):
            logger.warning("OCR: inventory entry has an out-of-range index %r "
                           "(%d files) — dropping it", i, n_files)
            continue
        if i in seen:
            logger.warning("OCR: file %d appears twice in the inventory — the "
                           "model split one file across entries, so slot indices "
                           "after it may be shifted", i)
            continue
        seen.add(i)
        kept.append(entry)
    if len(kept) != n_files:
        logger.warning("OCR: inventory has %d usable entries for %d files — "
                       "file-slot indices may not line up", len(kept), n_files)
    return kept


def _resolve_indices(obj: Dict, file_fields: List[Dict], urls: List[str]) -> None:
    """Replace file-slot index values with the actual URL, in place.

    Only touches keys already present in `obj`, so passing the full file-field
    list against a partial section dict won't inject stray null keys.
    """
    for f in file_fields:
        name = f["name"]
        if name in obj:
            idx = obj[name]
            obj[name] = urls[idx] if isinstance(idx, int) and 0 <= idx < len(urls) else None


# ── transaction form (with records) ────────────────────────────────────────

def _build_txn_prompt(txn_fields, record_fields, n_files) -> str:
    txn_values, txn_files = _split(txn_fields)
    rec_values, rec_files = _split(record_fields)
    keys = _declared_keys(txn_files + rec_files)

    return f"""You are given {n_files} file(s), numbered 0 to {n_files - 1}, in the
order provided. They ALL belong to ONE transaction. A transaction has one or
more RECORDS (e.g. each material / line item is a record); a single record may
span several files.

{_inventory_block(n_files, keys)}

STEP 2 — FILL THE FORM using that inventory. Return ONE JSON object with this
shape (the "files" inventory from STEP 1 stays in the output):

{{
  "files": [ ...from STEP 1... ],
  "transaction": {{
    <one key per transaction value field below, value read from the files or null>,
    <one key per transaction file-slot below, set to the 0-based index of the
     file that belongs in that slot, or null>
  }},
  "records": [
    {{ "file_indices": [<every file index belonging to THIS record>],
       <one key per record value field>, <one key per record file-slot as index> }}
  ]
}}

TRANSACTION value fields:
{_describe(txn_values)}

TRANSACTION file-slots (return a file index, not a value):
{_slots(txn_files)}

RECORD value fields (repeat per record found):
{_describe(rec_values)}

RECORD file-slots (return a file index, not a value):
{_slots(rec_files)}

Rules:
{_GROUNDING_RULES}
- A record's file-slots take files belonging to THAT record (same material /
  line item), matched using what STEP 1 recorded — not whichever file of that
  type you saw first. "file_indices" must list every file of that record,
  including ones that fill no slot; a file appears under one record only.
- Only fill what is clearly readable. Use null when not visible — never guess.
- Figure out the number of records yourself from the files.
- Return ONLY the JSON object. No markdown, no commentary."""


def read_transaction(files: List[str], fields: List[Dict]) -> Dict[str, Any]:
    """fields: txn fields (flat, with "name") + one item carrying "record_field".

    Slot keys come from doc_keys.SLOT_KEYS by slot name; a field may override
    with its own "keys": [...]. A value field may add "from": "<slot name>".
    Returns {"files": [...], "transaction": {...}, "records": [{...}]} with
    file-slots as URLs.
    """
    txn_fields = [f for f in fields if "name" in f]
    record_fields = next((f["record_field"] for f in fields if "record_field" in f), [])

    txn_values, txn_files = _split(txn_fields)
    rec_values, rec_files = _split(record_fields)
    _check_required(files, txn_files + rec_files)
    _warn_if_names_drifted(txn_values + rec_values, txn_files + rec_files)

    data_urls, kept_urls = _load_data_urls(files)
    parsed = _call_and_parse(_build_txn_prompt(txn_fields, record_fields, len(data_urls)), data_urls)

    inventory = _check_inventory(parsed.get("files") or [], len(kept_urls))
    all_idx = list(range(len(kept_urls)))
    used: set = set()

    # Records first: their slots are scoped to that record's own files, so a
    # record can only claim a file the model put under it. Transaction-level
    # slots then pick from whatever is left.
    txn = parsed.get("transaction", {})
    _resolve_indices(txn, txn_files, kept_urls)

    # Slots first, values after. A record's value can legitimately come off a
    # transaction-level document — an invoice line carries the billed quantity
    # and unit price — so every slot has to be assigned before anything is
    # read out of them.
    per_record = []
    for rec in parsed.get("records", []):
        _resolve_indices(rec, rec_files, kept_urls)
        pool = [i for i in rec.pop("file_indices", None) or all_idx if i in all_idx]
        rec_assigned = _classify(inventory, rec_files, pool, used)
        _apply_slots(rec, rec_assigned, kept_urls)
        _dedupe_slots(rec, rec_files)
        per_record.append((rec, rec_assigned))

    txn_assigned = _classify(inventory, txn_files, all_idx, used)
    _apply_slots(txn, txn_assigned, kept_urls)
    _dedupe_slots(txn, txn_files)

    # Transaction slots are offered FIRST, so the invoice's billed quantity
    # beats the weighing sheet's net weight where they differ — a quality
    # deduction between weighing and invoicing made that a 7% error on real
    # data. _fill_from_keys keeps the first source it finds, so the weighing
    # sheet stays the fallback for an invoice that does not itemise.
    for rec, rec_assigned in per_record:
        read = _fill_from_keys(rec, rec_values, txn_files + rec_files,
                               {**rec_assigned, **txn_assigned}, inventory)
        _blank_user_choice(rec, record_fields)
        _derive_price_per_unit(rec, read)

    read = _fill_from_keys(txn, txn_values, txn_files, txn_assigned, inventory)
    _blank_user_choice(txn, txn_fields)
    _derive_price_per_unit(txn, read)
    return parsed


# ── audit form (grouped by section, no records) ─────────────────────────────

def _sections_in_order(fields: List[Dict]) -> List[str]:
    seen = []
    for f in fields:
        s = f.get("section") or ""
        if s not in seen:
            seen.append(s)
    return seen


def _build_audit_prompt(fields: List[Dict], n_files: int) -> str:
    keys = _declared_keys(_split(fields)[1])
    blocks = []
    for section in _sections_in_order(fields):
        in_section = [f for f in fields if (f.get("section") or "") == section]
        values, files_ = _split(in_section)
        block = [f'Section "{section}":', "  value fields:", _describe(values)]
        block.append("  file-slots (return a file index, not a value):")
        block.append(_slots(files_))
        blocks.append("\n".join(block))

    return f"""You are given {n_files} file(s), numbered 0 to {n_files - 1}, in the
order provided. They describe ONE recycler audit. Fields are grouped into
sections. There are NO repeating records — fill each section exactly once.

{_inventory_block(n_files, keys)}

STEP 2 — FILL THE FORM using that inventory. Return ONE JSON object with a
"files" key holding the STEP 1 inventory, plus one key per section, each
mapping to an object with one key per field in that section. For value fields
put the value read from the files (or null). For file-slots put the 0-based
index of the file that belongs there (or null).

{chr(10).join(blocks)}

Rules:
{_GROUNDING_RULES}
- Only fill what is clearly readable. Use null when not visible — never guess.
- Return ONLY the JSON object. No markdown, no commentary."""


def read_audit(files: List[str], fields: List[Dict]) -> Dict[str, Any]:
    """fields: flat list, each {section, name, type, options?}. Sections and
    fields are user-defined, not fixed. File-slots are matched by
    doc_keys.SLOT_KEYS, or an overriding "keys": [...]. Returns {"<section>": {field: value}}
    with file-slots resolved to URLs.
    """
    value_fields, file_fields = _split(fields)
    _check_required(files, file_fields)
    _warn_if_names_drifted(value_fields, file_fields)

    data_urls, kept_urls = _load_data_urls(files)
    parsed = _call_and_parse(_build_audit_prompt(fields, len(data_urls)), data_urls)

    # One assignment across all sections — a file fills at most one slot
    # overall, same rule the model is given.
    assigned = _classify(_check_inventory(parsed.get("files") or [], len(kept_urls)),
                         file_fields, list(range(len(kept_urls))), set())

    # resolve file indices -> URLs across every section (only present keys touched)
    for section in parsed.values():
        if isinstance(section, dict):
            _resolve_indices(section, file_fields, kept_urls)
            here = [f for f in file_fields if f["name"] in section]
            _apply_slots(section, {k: v for k, v in assigned.items() if k in section},
                         kept_urls)
            _dedupe_slots(section, here)
            read = _fill_from_keys(section, [f for f in value_fields if f["name"] in section],
                                   here, assigned, parsed.get("files") or [])
            _blank_user_choice(section, fields)
            _derive_price_per_unit(section, read)
    return parsed


# ── local runner ───────────────────────────────────────────────────────────

def _explain(parsed: Dict, fields: List[Dict]) -> str:
    """Why each file landed where it did — the thing you actually need when a
    slot comes back wrong: what the model read off each file, and what the
    final slotting was. Read the two together."""
    out = ["", "── what the model read off each file ──"]
    for e in parsed.get("files") or []:
        keys = e.get("keys") or {}
        out.append(f"  [{e.get('index')}] {e.get('doc_type') or '?'}"
                   f"  ({len(keys)} keys)")
        for k, v in keys.items():
            out.append(f"        {k} = {v}")
        if not keys:
            out.append("        (nothing matched — this file can only be "
                       "model-picked, or its keys are named wrong)")

    file_names = {f["name"] for f in _split([f for f in fields if "name" in f])[1]}
    rec_fields = next((f["record_field"] for f in fields if "record_field" in f), [])
    file_names |= {f["name"] for f in _split(rec_fields)[1]}

    out.append("")
    out.append("── where each slot ended up ──")
    for scope, obj in ([("transaction", parsed.get("transaction") or {})]
                       + [(f"record {i}", r) for i, r in enumerate(parsed.get("records") or [])]):
        out.append(f"  {scope}:")
        for k, v in obj.items():
            mark = "FILE " if k in file_names else "     "
            out.append(f"    {mark}{k} = {v}")
    return "\n".join(out)


if __name__ == "__main__":
    # python -m GEPPPlatform.services.cores.epr_ai_audit.api.ocr request.json
    # where request.json is the POST body: {"files": [...], "fields": [...]}
    # Needs OPENROUTER_API_KEY. No database, no AWS — files are plain HTTP GETs.
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with open(sys.argv[1]) as fh:
        body = json.load(fh)
    result = read_transaction(body["files"], body["fields"])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(_explain(result, body["fields"]), file=sys.stderr)
