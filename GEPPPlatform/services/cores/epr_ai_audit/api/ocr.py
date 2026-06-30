"""OCR reader: a dump of files for ONE transaction -> filled form.

Hands every file to the vision LLM at once and asks it to (a) read the
transaction-level values, (b) find the records and read each one's values,
and (c) route each uploaded file into the right file-slot by index.

Files are sent in order; the model refers to them by 0-based index, and we
swap indices back to URLs here so the model never has to echo long URLs.
"""

import json
import logging
from typing import Any, Dict, List

from GEPPPlatform.libs.image_processing import safe_process_image
from GEPPPlatform.libs.openrouter import call_llm

logger = logging.getLogger(__name__)


def _split(fields: List[Dict]) -> tuple[list, list]:
    """Return (value_fields, file_fields) from a flat field list."""
    value_fields = [f for f in fields if f.get("type") != "file"]
    file_fields = [f for f in fields if f.get("type") == "file"]
    return value_fields, file_fields


def _describe(fields: List[Dict]) -> str:
    """One line per field for the prompt, noting allowed options if present."""
    lines = []
    for f in fields:
        line = f"  - {f['name']}"
        if f.get("options"):
            line += f" (one of: {', '.join(f['options'])})"
        lines.append(line)
    return "\n".join(lines) if lines else "  (none)"


def _build_prompt(txn_fields: List[Dict], record_fields: List[Dict], n_files: int) -> str:
    txn_values, txn_files = _split(txn_fields)
    rec_values, rec_files = _split(record_fields)

    def file_slots(file_fields):
        return "\n".join(f"  - {f['name']}" for f in file_fields) or "  (none)"

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
    {{
      <one key per record value field>,
      <one key per record file-slot, set to the matching file index or null>
    }}
  ]
}}

TRANSACTION value fields:
{_describe(txn_values)}

TRANSACTION file-slots (return a file index, not a value):
{file_slots(txn_files)}

RECORD value fields (repeat per record found):
{_describe(rec_values)}

RECORD file-slots (return a file index, not a value):
{file_slots(rec_files)}

Rules:
- Only fill what is clearly readable. Use null when not visible — never guess.
- For option fields, pick exactly one of the listed options or null.
- Figure out the number of records yourself from the files.
- Return ONLY the JSON object. No markdown, no commentary."""


def _resolve_indices(obj: Dict, file_fields: List[Dict], urls: List[str]) -> None:
    """Replace file-slot index values with the actual URL, in place."""
    for f in file_fields:
        name = f["name"]
        idx = obj.get(name)
        obj[name] = urls[idx] if isinstance(idx, int) and 0 <= idx < len(urls) else None


def read_transaction(files: List[str], fields: List[Dict]) -> Dict[str, Any]:
    """files: list of S3 URLs. fields: the form (txn fields + one record_field item).

    Returns {"transaction": {...}, "records": [{...}]} with file-slots resolved
    to URLs. Raises on LLM/parse error (caller decides whether to swallow).
    """
    txn_fields = [f for f in fields if "name" in f]
    record_fields = next((f["record_field"] for f in fields if "record_field" in f), [])

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

    prompt = _build_prompt(txn_fields, record_fields, len(data_urls))
    result = call_llm(prompt, image_urls=data_urls)

    text = result["content"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)

    _, txn_files = _split(txn_fields)
    _, rec_files = _split(record_fields)
    _resolve_indices(parsed.get("transaction", {}), txn_files, kept_urls)
    for rec in parsed.get("records", []):
        _resolve_indices(rec, rec_files, kept_urls)

    return parsed
