"""OCR readers: a dump of files -> a filled form.

Two forms are supported, sharing the same guts (load files -> vision LLM ->
fill fields -> route file-slots back to URLs by index):

  read_transaction()  transaction with repeating RECORDS (materials/line items)
  read_audit()        flat fields grouped by SECTION, no repetition

Files are sent in order; the model refers to them by 0-based index, and we
swap indices back to URLs here so the model never has to echo long URLs.
"""

import json
import logging
from typing import Any, Dict, List

from GEPPPlatform.libs.exceptions import BadRequestException
from GEPPPlatform.libs.image_processing import safe_process_image
from GEPPPlatform.libs.openrouter import INTEGRITY_MODEL, call_llm

logger = logging.getLogger(__name__)


# ── shared helpers ─────────────────────────────────────────────────────────

def _split(fields: List[Dict]) -> tuple[list, list]:
    """Return (value_fields, file_fields) from a flat field list."""
    return (
        [f for f in fields if f.get("type") != "file"],
        [f for f in fields if f.get("type") == "file"],
    )


def _describe(fields: List[Dict]) -> str:
    """One line per field for the prompt, noting allowed options if present."""
    lines = []
    for f in fields:
        line = f"  - {f['name']}"
        if f.get("options"):
            line += f" (one of: {', '.join(f['options'])})"
        lines.append(line)
    return "\n".join(lines) if lines else "  (none)"


def _check_required(files: List[str], file_fields: List[Dict]) -> None:
    """Reject if fewer files than the number of required file-slots."""
    required = sum(1 for f in file_fields if f.get("required"))
    if len(files) < required:
        raise BadRequestException(
            f"Not enough files: {len(files)} provided, {required} required."
        )


def _load_data_urls(files: List[str]) -> tuple[list, list]:
    """Fetch + prep each file. Returns (data_urls, kept_urls) in parallel order."""
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


def _call_and_parse(prompt: str, data_urls: List[str]) -> Dict:
    result = call_llm(prompt, image_urls=data_urls, model=INTEGRITY_MODEL)
    text = result["content"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


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

    def slots(ff):
        return "\n".join(f"  - {f['name']}" for f in ff) or "  (none)"

    return f"""You are given {n_files} file(s), numbered 0 to {n_files - 1}, in the
order provided. They ALL belong to ONE transaction. A transaction has one or
more RECORDS (e.g. each material / line item is a record); a single record may
span several files.

Read across all files and return ONE JSON object with this shape:

{{
  "transaction": {{
    <one key per transaction value field below, value read from the files or null>,
    <one key per transaction file-slot below, set to the 0-based index of the
     file that belongs in that slot, or null>
  }},
  "records": [
    {{ <one key per record value field>, <one key per record file-slot as index> }}
  ]
}}

TRANSACTION value fields:
{_describe(txn_values)}

TRANSACTION file-slots (return a file index, not a value):
{slots(txn_files)}

RECORD value fields (repeat per record found):
{_describe(rec_values)}

RECORD file-slots (return a file index, not a value):
{slots(rec_files)}

Rules:
- Only fill what is clearly readable. Use null when not visible — never guess.
- For option fields, pick exactly one of the listed options or null.
- Figure out the number of records yourself from the files.
- Return ONLY the JSON object. No markdown, no commentary."""


def read_transaction(files: List[str], fields: List[Dict]) -> Dict[str, Any]:
    """fields: txn fields (flat, with "name") + one item carrying "record_field".
    Returns {"transaction": {...}, "records": [{...}]} with file-slots as URLs.
    """
    txn_fields = [f for f in fields if "name" in f]
    record_fields = next((f["record_field"] for f in fields if "record_field" in f), [])

    _, txn_files = _split(txn_fields)
    _, rec_files = _split(record_fields)
    _check_required(files, txn_files + rec_files)

    data_urls, kept_urls = _load_data_urls(files)
    parsed = _call_and_parse(_build_txn_prompt(txn_fields, record_fields, len(data_urls)), data_urls)

    _resolve_indices(parsed.get("transaction", {}), txn_files, kept_urls)
    for rec in parsed.get("records", []):
        _resolve_indices(rec, rec_files, kept_urls)
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
    blocks = []
    for section in _sections_in_order(fields):
        in_section = [f for f in fields if (f.get("section") or "") == section]
        values, files_ = _split(in_section)
        block = [f'Section "{section}":', "  value fields:", _describe(values)]
        block.append("  file-slots (return a file index, not a value):")
        block.append("\n".join(f"    - {f['name']}" for f in files_) or "    (none)")
        blocks.append("\n".join(block))

    return f"""You are given {n_files} file(s), numbered 0 to {n_files - 1}, in the
order provided. They describe ONE recycler audit. Fields are grouped into
sections. There are NO repeating records — fill each section exactly once.

Read across all files and return ONE JSON object, one key per section, each
mapping to an object with one key per field in that section. For value fields
put the value read from the files (or null). For file-slots put the 0-based
index of the file that belongs there (or null).

{chr(10).join(blocks)}

Rules:
- Only fill what is clearly readable. Use null when not visible — never guess.
- For option fields, pick exactly one of the listed options or null.
- Return ONLY the JSON object. No markdown, no commentary."""


def read_audit(files: List[str], fields: List[Dict]) -> Dict[str, Any]:
    """fields: flat list, each {section, name, type, options?}. Sections and
    fields are user-defined, not fixed. Returns {"<section>": {field: value}}
    with file-slots resolved to URLs.
    """
    _, file_fields = _split(fields)
    _check_required(files, file_fields)

    data_urls, kept_urls = _load_data_urls(files)
    parsed = _call_and_parse(_build_audit_prompt(fields, len(data_urls)), data_urls)

    # resolve file indices -> URLs across every section (only present keys touched)
    for section in parsed.values():
        if isinstance(section, dict):
            _resolve_indices(section, file_fields, kept_urls)
    return parsed
