"""
Background worker for the EPR dedup queue.

`POST /ai/audit/embed-transaction` returns immediately after inserting the
transaction + image rows (with NULL extracted_data). This module is what
the cron Lambda calls to fill those NULLs and then run dedup. One entry
point: `process_transaction(conn, tx_id)`.

Per-image commits keep partial progress durable — if the LLM succeeds on
images 1-3 but fails on image 4, the first three stay extracted and only
image 4 is retried on the next pass.

Cron handler shape (see entry_points/GEPPEPRAIAudit.py):
    from GEPPPlatform.services.cores.epr_ai_audit.cron.db import get_connection
    from GEPPPlatform.services.cores.epr_ai_audit.cron import jobs, worker

    def handler(event, context):
        conn = get_connection()
        try:
            with conn:
                # Small batch so a few in-progress legacy imports per project
                # don't blow past Lambda's 15-min timeout.
                claimed = jobs.claim_next_jobs(conn, jobs.STAGE_EMBEDDING, batch_size=3)
            for job_id, tx_id in claimed:
                try:
                    report = worker.process_transaction(conn, tx_id)
                    with conn:
                        if report and report.get("retry_later"):
                            # Legacy import still in progress for this project
                            # — release the job so it retries next tick.
                            jobs.release_job(conn, job_id)
                        else:
                            jobs.mark_done(conn, job_id, report or {"missing": True})
                except Exception as exc:
                    with conn:
                        jobs.mark_failed(conn, job_id, repr(exc))
        finally:
            conn.close()
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional

from psycopg2.extras import Json

from GEPPPlatform.libs import image_processing, legacy_db, openrouter

from . import duplicates, legacy_import

logger = logging.getLogger(__name__)


def _to_vec_literal(vec):
    """pgvector accepts a string literal `[v1,v2,...]` cast to ::vector."""
    return "[" + ",".join(f"{float(x)}" for x in vec) + "]"


def _extract_and_embed(image_url: str):
    """Run vision LLM + description embedding for one file URL.

    Returns (extracted_dict_or_None, description_vec_literal_or_None).
    All errors fail-soft so the caller can write NULLs and continue.
    """
    extracted = None
    desc_vec_literal = None

    data_url = image_processing.safe_process_image(image_url)
    if data_url is None:
        return None, None

    try:
        extracted = openrouter.extract_image_data(data_url)
    except Exception as exc:
        logger.warning("LLM extraction failed for %s: %s", image_url, exc)

    description = (extracted or {}).get("visual_description")
    if description:
        try:
            vec = openrouter.embed_text(description)
            desc_vec_literal = _to_vec_literal(vec)
        except Exception as exc:
            logger.warning("description embedding failed for %s: %s", image_url, exc)

    return extracted, desc_vec_literal


def _update_image(conn, table: str, img_id: int, image_url: str) -> bool:
    """Process one image row, write extracted_data + description_embedding,
    commit. Returns True if extraction populated `extracted_data`.

    `table` is a hardcoded literal from the caller, not user input. The
    commit-per-image policy keeps partial progress durable across crashes."""
    extracted, desc_vec_literal = _extract_and_embed(image_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} "
                f"SET extracted_data = %s, description_embedding = %s::vector, "
                f"    updated_date = NOW() "
                f"WHERE id = %s",
                (
                    Json(extracted) if extracted is not None else None,
                    desc_vec_literal,
                    img_id,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return extracted is not None


def _pending_transaction_images(conn, tx_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, image_url FROM epr_transaction_image "
            "WHERE transaction_id = %s "
            "AND is_active = TRUE "
            "AND extracted_data IS NULL",
            (tx_id,),
        )
        return cur.fetchall()


def _pending_record_images(conn, tx_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT i.id, i.image_url "
            "FROM epr_transaction_record_image i "
            "JOIN epr_transaction_records_embeded r ON r.id = i.epr_transaction_record_id "
            "WHERE r.transaction_id = %s "
            "AND i.is_active = TRUE "
            "AND i.extracted_data IS NULL",
            (tx_id,),
        )
        return cur.fetchall()


# Threshold above which a description_similarity counts as an "image" match
# in the flags summary. Mirrors duplicates.DESC_SIM_LOW_FUZZY.
_FLAGS_IMAGE_SIM_THRESHOLD = 0.70

# Only these confidence tiers are surfaced in flags.duplicates[]. Lower tiers
# (medium, low-fuzzy) are too noisy for reviewers on document-heavy projects
# where tax IDs/vendors cluster naturally. The full candidate list — including
# the dropped tiers — is still persisted on epr_dedup_jobs.result for audit.
_SURFACED_CONFIDENCE_TIERS = {"high", "medium-fuzzy"}

# Per-payload parallelism for integrity LLM calls. Each call is pure HTTP I/O
# (fetch image → vision LLM → JSON parse) with no shared mutable state and no
# DB access, so threading is safe. Capped to keep us well under OpenRouter
# rate limits and to avoid memory bloat from many concurrent image downloads.
_INTEGRITY_PARALLELISM = 4


def _fetch_legacy_ids(conn, embeded_ids):
    """Return {embeded_id: legacy_tx_id} for candidates that were imported
    from the legacy MySQL DB. Missing keys = the row was API-inserted and
    has no legacy id."""
    if not embeded_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, (raw_data->>'_legacy_id')::bigint "
            "FROM epr_transactions_embeded "
            "WHERE id = ANY(%s) AND raw_data ? '_legacy_id'",
            (list(embeded_ids),),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def _summarize_candidates_for_flags(candidates, legacy_id_map=None):
    """Reduce raw dedup candidates into a compact summary stored on the
    parent transaction's `flags` JSONB column.

    Only candidates whose confidence is in _SURFACED_CONFIDENCE_TIERS
    (currently `high` and `medium-fuzzy`) are surfaced — lower tiers are too
    noisy on document-heavy projects. The full unfiltered list is still on
    `epr_dedup_jobs.result.candidates` for audit.

    `id` in the output is the legacy MySQL transaction id when the candidate
    was imported from legacy, else the embeded (Postgres) id — the embeded id
    is always also returned as `embeded_id` so consumers can join internally.

    Each candidate gets a `matched_by` list ("text_data", "image", or both)
    so consumers can quickly see WHY it was flagged without parsing the
    underlying fields themselves.
    """
    legacy_id_map = legacy_id_map or {}
    out = []
    for c in candidates:
        if c.get("confidence") not in _SURFACED_CONFIDENCE_TIERS:
            continue
        matched_by = []
        if (c.get("matched_document_numbers")
                or c.get("matched_identifiers")
                or c.get("matched_doc_triples")):
            matched_by.append("text_data")
        sim = c.get("description_similarity")
        if sim is not None and sim >= _FLAGS_IMAGE_SIM_THRESHOLD:
            matched_by.append("image")
        embeded_id = c.get("id")
        legacy_id = legacy_id_map.get(embeded_id)
        out.append({
            "id": legacy_id if legacy_id is not None else embeded_id,
            "embeded_id": embeded_id,
            "legacy_id": legacy_id,
            "confidence": c.get("confidence"),
            "matched_by": matched_by,
            "matched_document_numbers": c.get("matched_document_numbers") or [],
            "matched_identifiers": c.get("matched_identifiers") or [],
            "description_similarity": sim,
        })
    return out


def _determine_status(candidates, integrity=None) -> str:
    """`flagged` if EITHER any candidate is HIGH confidence OR any
    integrity issue exists (parent OR any record); else `passed`.

    HIGH dedup = document_number match or vendor/date/total triple match.
    Integrity issue = payload data disagrees with what LLM extracted from
    the transaction's own images, or from any of its record images.

    Lower-tier dedup candidates (medium, medium-fuzzy, low-fuzzy) stay in
    `flags.duplicates` for review but don't auto-flag — too noisy on
    document-heavy projects where tax IDs/vendors cluster naturally.
    """
    for c in candidates:
        if c.get("confidence") == "high":
            return "flagged"
    if integrity:
        if integrity.get("issues"):
            return "flagged"
        for r in integrity.get("records") or []:
            if r.get("issues"):
                return "flagged"
    return "passed"


# Phrases that, when found in an issue's `explanation`, indicate the LLM
# actually concluded the field MATCHES but filed it under "issues" anyway.
# These get dropped to matched_fields by `_clean_false_positive_issues`.
_MATCH_PHRASES_IN_EXPLANATION = (
    "this is a match",
    "matches the payload",
    "should be considered a match",
    "is a match.",
    "is a match,",
    "within the allowed",
    "within tolerance",
    "within ±1",         # within ±1
    "within +/- 1",
    "this matches",
    "match.",
    # Soft-match phrasing the LLM uses on imageType when it concludes the
    # image fits the type but still files it under issues anyway.
    "is consistent with",
    "consistent with a ",
    "consistent with the",
    "fits the type",
    "fits the category",
    "matches the stated type",
    "matches the type",
    "matches the category",
    "appears to be a",
    "appears to be the",
    # Numeric-formatting non-issues — should never be flagged but if they
    # are, drop them.
    "missing comma",
    "thousands separator",
    "without the comma",
    "without thousand",
    "decimal formatting",
    "formatting difference",
    "cosmetic difference",
)


def _clean_false_positive_issues(raw_issues, matched_set):
    """Drop "issues" the LLM mis-filed. Two cases caught here:

    1. MATCH disguised as an issue — explanation contains a phrase like
       "this is a match" / "consistent with" / "within tolerance". The field
       is moved to `matched_set` so it surfaces as a real match.
    2. CANT VERIFY disguised as an issue — image_indicates is something like
       "Not visible" or the explanation admits the value isn't shown / can't
       be estimated. These get silently dropped (NOT moved to matched_set,
       because nothing was actually verified).

    The LLM occasionally ignores the per-field decision flow even when the
    prompt is explicit. This safety net catches that drift.
    """
    kept = []
    for issue in raw_issues or []:
        explanation = issue.get("explanation")
        # explanation is now {"en": "...", "th": "..."}; tolerate old plain-string
        # rows that may still be in flight from before the schema change.
        if isinstance(explanation, dict):
            en_text = (explanation.get("en") or "").lower()
        else:
            en_text = (explanation or "").lower()
        indicates = str(issue.get("image_indicates") or "").lower().strip()

        # Case 1: LLM concluded MATCH but filed as issue.
        if any(p in en_text for p in _MATCH_PHRASES_IN_EXPLANATION):
            field = issue.get("field")
            if field:
                matched_set.add(str(field))
            continue

        # Case 2: LLM admits it CAN'T VERIFY but filed as issue anyway.
        if any(p in indicates for p in _NOT_VISIBLE_PHRASES_IN_INDICATES):
            continue
        if any(p in en_text for p in _NOT_VISIBLE_PHRASES_IN_EXPLANATION):
            continue

        field = issue.get("field")
        payload_value = issue.get("payload_value")
        image_indicates = issue.get("image_indicates")

        # Case 2.5: Payload didn't claim a value for this field — nothing to
        # verify against, so no mismatch is possible. The LLM occasionally
        # flags these anyway ("the image shows X but the payload didn't
        # specify"). Drop silently. The prompt also tells the model to skip
        # null fields entirely; this is the safety net.
        if _is_empty_payload_value(payload_value):
            continue

        # Case 3: For ANY numeric field, if payload_value and image_indicates
        # represent the same number (within ±1%), the LLM reported both sides
        # as equal but still filed an issue. Drop it regardless of explanation
        # prose. This is the most reliable check — compares the actual values
        # the LLM extracted, not its narrative phrasing.
        if field in _NUMERIC_INTEGRITY_FIELDS:
            if _values_numerically_equal(payload_value, image_indicates):
                matched_set.add(str(field))
                continue

        # Case 4: For the LENIENT field (pricePerUnit), if the LLM's own
        # explanation contains the payload value as a number, the LLM sighted
        # it on the image but flagged anyway (typically because a labeled cell
        # had a 0.00 placeholder while the real value was written elsewhere).
        # Treat it as MATCH and move on.
        if field == "pricePerUnit":
            if _explanation_mentions_numeric_value(en_text, payload_value):
                matched_set.add("pricePerUnit")
                continue

        # Case 5: For transactionDate, parse both sides into real dates,
        # applying Buddhist→Gregorian conversion to years >= 2500. If the
        # dates land within ±1 calendar day of each other, the LLM either
        # forgot to convert (image year 2568 vs payload 2025) or just ignored
        # the tolerance rule. Drop the issue. This catches the most common
        # Thai-date failure mode (LLM compares Buddhist year directly against
        # Gregorian year without subtracting 543).
        if field == "transactionDate":
            if _dates_within_one_day(payload_value, image_indicates):
                matched_set.add("transactionDate")
                continue
            # Refuse to flag on suspicious "dates" — short DD/M fragments
            # with no 4-digit year or recognized label. Almost always the
            # LLM misreading an address ("27/9"), page number ("1/3"), or
            # tax-ID slice. Drop the issue silently rather than trust it.
            if _is_suspicious_date_fragment(image_indicates):
                continue

        # Case 6: imageType claimed against a GENERIC label that's too vague
        # to verify (this is a waste-management platform — "product_image" /
        # "photo" / "waste_photo" etc. cover any visible material). The LLM
        # routinely flags waste photos for these labels; we always drop.
        if field == "imageType":
            stated_type = str(payload_value or "").strip().lower()
            if stated_type in _GENERIC_IMAGE_TYPES:
                continue

        kept.append(issue)
    return kept


# A "date" fragment short enough to almost certainly NOT be a real date:
# no 4-digit year, no Thai/English month name. Almost always an address
# number / phone / tax-ID / page-number misread by the LLM.
_SUSPICIOUS_DATE_FRAGMENT_RE = re.compile(r"^\s*\d{1,2}\s*[/\-.]\s*\d{1,2}\s*$")

# Keywords that strongly suggest a string contains a real date-label
# context. If any of these appear, we trust the LLM's reading.
_DATE_LABEL_HINTS = (
    "date", "issue", "issued", "delivery", "delivered", "received",
    "signed", "inspected", "transaction", "due",
    "วันที่", "ลงวันที่", "ออกเมื่อ", "ออกใบ", "ส่งของ", "ส่งสินค้า",
    "รับสินค้า", "ทำรายการ", "ตรวจ",
    # Recognised month names (English + Thai abbreviated set)
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
)


def _is_suspicious_date_fragment(image_indicates):
    """True if `image_indicates` looks like an LLM misread of a non-date
    number (address, page-number, tax-ID slice) rather than a real date.

    Heuristic: short DD/MM-shaped fragment with no 4-digit year anywhere
    AND no date-label keyword anywhere. The LLM should have refused; we
    drop these to avoid false flags from misread address numbers like
    "27/9 Soi 5"."""
    if not image_indicates:
        return False
    s = str(image_indicates).strip()
    # Bare "27/9" or "12-5" with nothing else
    if _SUSPICIOUS_DATE_FRAGMENT_RE.match(s):
        return True
    # Any 4-digit-year span anywhere = not suspicious
    if re.search(r"\b\d{4}\b", s):
        return False
    # DD/MM/YY Thai shorthand (with the YY component) = a valid date format
    if re.search(r"\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2}\b", s):
        return False
    # If a date-label keyword appears, trust the LLM
    lower = s.lower()
    if any(h in lower for h in _DATE_LABEL_HINTS):
        return False
    # No year, no label, and at least one slash/dash fragment → suspicious
    if re.search(r"\d{1,2}\s*[/\-.]\s*\d{1,2}", s):
        return True
    return False


# Image types that are too generic to verify against image content. Waste
# photos, scrap, materials in bins, vehicles loaded with cargo all
# legitimately fit these labels on a recycling/waste-management platform —
# so the LLM should skip the imageType check entirely. Lowercased, exact.
# payload_value forms that mean "the user didn't claim a value". Anything in
# this set should never produce an integrity issue — there's nothing to
# compare against. Compared lowercased after stripping whitespace.
_EMPTY_PAYLOAD_TOKENS = frozenset({
    "", "-", "--", "none", "null", "n/a", "na", "undefined",
    "ไม่ระบุ", "ไม่มี",
})


def _is_empty_payload_value(v):
    """True when the payload value is missing / empty / a placeholder
    sentinel like '-' or 'null'. Numeric zero is NOT considered empty —
    a zero claim is still a real claim that may need verifying."""
    if v is None:
        return True
    if isinstance(v, (int, float)):
        return False
    s = str(v).strip().lower()
    return s in _EMPTY_PAYLOAD_TOKENS


_GENERIC_IMAGE_TYPES = frozenset({
    "",
    "other",
    "photo",
    "image",
    "product_image",
    "product",
    "product_photo",
    "waste_photo",
    "waste_image",
    "cargo_photo",
    "cargo_image",
    "material_photo",
    "material_image",
    "general",
    "misc",
    "miscellaneous",
})


# Fields whose payload_value and image_indicates are numeric — eligible for
# the same-value short-circuit in _clean_false_positive_issues.
_NUMERIC_INTEGRITY_FIELDS = ("totalQuantity", "totalPrice", "pricePerUnit")


def _values_numerically_equal(a, b, tolerance=0.01):
    """True if a and b parse to equal numbers within `tolerance` (default ±1%).
    Tolerates thousands separators, currency symbols, unit suffixes, and
    trailing-zero formatting on either side."""
    na = _parse_number(a)
    nb = _parse_number(b)
    if na is None or nb is None:
        return False
    if na == 0 and nb == 0:
        return True
    if na == 0 or nb == 0:
        return False
    return abs(na - nb) / max(abs(na), abs(nb)) <= tolerance


# Date regexes used by _parse_date_flexible. Most permissive patterns first.
_DATE_PATTERNS = (
    # YYYY-MM-DD (ISO-style)
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    # DD/MM/YYYY  /  DD-MM-YYYY  /  DD.MM.YYYY
    re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"),
    # DD/MM/YY (2-digit year — only as a last-resort, see _parse_date_flexible)
    re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})\b"),
)


def _parse_date_flexible(s):
    """Best-effort date parse. Returns a `datetime.date` or None.

    Applies Buddhist-Era → Gregorian conversion (year - 543) automatically
    when the parsed year is ≥ 2500. Handles 2-digit Buddhist years like
    "26/11/68" (68 → 2568 → 2025) by adding 2500 first.

    Recognizes ISO, slash, dash, and dot date formats. Picks the first match
    in `s`, so leading prose like "The date is 26/11/2568 in Buddhist" works.
    """
    if not s:
        return None
    s = str(s).strip()

    # ISO first (unambiguous about year position)
    m = _DATE_PATTERNS[0].search(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe_date(y, mo, d)

    # DD/MM/YYYY with 4-digit year
    m = _DATE_PATTERNS[1].search(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe_date(y, mo, d)

    # DD/MM/YY with 2-digit year — assume Buddhist short form (e.g. "68" → 2568)
    m = _DATE_PATTERNS[2].search(s)
    if m:
        d, mo, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # 2-digit years on Thai docs are nearly always Buddhist shorthand.
        # "68" → 2568 → 2025. "61" → 2561 → 2018.
        y = 2500 + y2
        return _safe_date(y, mo, d)

    return None


def _safe_date(year, month, day):
    """Build a `date(y, m, d)`, applying Buddhist-Era conversion to years
    ≥ 2500. Returns None on any invalid combo."""
    if year >= 2500:
        year -= 543
    try:
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _dates_within_one_day(a, b, tolerance_days=1):
    """True if `a` parses to a single date and ANY date found in `b` is within
    `tolerance_days` of it. Either side may be a string with one or more
    date-shaped substrings (ISO / DD-MM-YYYY / DD-MM-YY). Years ≥ 2500 are
    treated as Buddhist Era and converted to Gregorian.

    The asymmetric handling — single date on the left, sweep all dates on
    the right — is for the common case where the LLM lists multiple dates
    in image_indicates ("Issue: 29/03/68, Delivery: 31/03/68"); we want a
    MATCH if any of them is close to the payload.
    """
    da = _parse_date_flexible(a)
    if da is None:
        return False
    for db in _extract_all_dates(b):
        if abs((db - da).days) <= tolerance_days:
            return True
    return False


def _extract_all_dates(s):
    """Yield every date-shaped substring in `s` as a `datetime.date`,
    auto-converting Buddhist years. Tries ISO first, then DD/MM/YYYY,
    then DD/MM/YY-shorthand. Each match-position is consumed only once
    per pattern, but the function returns all distinct dates found."""
    if not s:
        return
    s = str(s)
    seen = set()

    # ISO: YYYY-MM-DD
    for m in _DATE_PATTERNS[0].finditer(s):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        sd = _safe_date(y, mo, d)
        if sd and sd not in seen:
            seen.add(sd)
            yield sd

    # DD/MM/YYYY (or DD-MM-YYYY / DD.MM.YYYY)
    for m in _DATE_PATTERNS[1].finditer(s):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        sd = _safe_date(y, mo, d)
        if sd and sd not in seen:
            seen.add(sd)
            yield sd

    # DD/MM/YY — Thai 2-digit shorthand (assumed Buddhist: "68" → 2568)
    for m in _DATE_PATTERNS[2].finditer(s):
        d, mo, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        sd = _safe_date(2500 + y2, mo, d)
        if sd and sd not in seen:
            seen.add(sd)
            yield sd


def _parse_number(v):
    """Best-effort numeric parse. Returns float or None.
    Strips thousands separators (commas), currency symbols, and unit
    suffixes commonly seen on Thai recycling docs."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    # Strip currency / unit noise
    for noise in ("฿", "$", "บาท", "thb", "kg", "kgs", "กก.", "กก", "/kg", "/กก."):
        s = s.replace(noise, "")
    s = s.replace(",", "").strip()
    # Pick the first plain number out of whatever's left
    m = _NUMERIC_TOKEN_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# Pull every number-shaped substring (with or without thousands separators
# / decimals) out of a chunk of free text.
_NUMERIC_TOKEN_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _explanation_mentions_numeric_value(text, payload_value, tolerance=0.01):
    """True if `text` contains a number equal to `payload_value` within
    `tolerance` (default ±1%). Used to detect LLM "I saw it but flagged it
    anyway" explanations for lenient sighting-only fields like pricePerUnit.
    """
    if payload_value is None or payload_value == "":
        return False
    try:
        target = float(str(payload_value).replace(",", ""))
    except (TypeError, ValueError):
        return False
    if target == 0:
        # Exact match for zero; tolerance math would divide by zero.
        return "0" in text
    abs_target = abs(target)
    for m in _NUMERIC_TOKEN_RE.findall(text or ""):
        try:
            n = float(m.replace(",", ""))
        except ValueError:
            continue
        if abs(n - target) / abs_target <= tolerance:
            return True
    return False


# image_indicates values that mean "the value isn't visible/legible/present
# in this image" — when the LLM writes any of these, the field is CANT
# VERIFY, not a mismatch. Lowercased substring match.
_NOT_VISIBLE_PHRASES_IN_INDICATES = (
    "not visible",
    "not shown",
    "not displayed",
    "not present",
    "not legible",
    "not specified",
    "not stated",
    "cannot determine",
    "cannot be determined",
    "cannot estimate",
    "cannot be estimated",
    "no clear",
    "no indication",
    "no specific",
    "no value",
    "unknown",
    "n/a",
    "none visible",
)

# Explanation phrases that also indicate CANT VERIFY.
_NOT_VISIBLE_PHRASES_IN_EXPLANATION = (
    "not visible in",
    "not shown in",
    "not displayed in",
    "is not visible",
    "is not shown",
    "is not displayed",
    "is not specified",
    "is not stated",
    "is not present",
    "is not legible",
    "is not clearly",
    "cannot estimate",
    "cannot be estimated",
    "cannot determine",
    "cannot be determined",
    "unable to determine",
    "unable to verify",
    "unable to estimate",
    "no clear indication",
    "no specific quantity",
    "no specific total",
    "no specific price",
    "no specific weight",
    "no precise",
    "without a printed",
    "without any printed",
)


def _load_integrity_inputs(conn, tx_id):
    """Pull the parent's raw_data and all its image rows (id, name, type,
    type_id, url) for the LLM-based integrity check. Every image is checked
    — documents verify invoiceNo / date / total, scale readings verify
    weight, waste/cargo photos can verify quantity if a number is visible.
    The LLM decides what's checkable per-image."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT raw_data FROM epr_transactions_embeded WHERE id = %s",
            (tx_id,),
        )
        row = cur.fetchone()
        raw_data = row[0] if row else None
        cur.execute(
            "SELECT id, name, type, type_id, image_url "
            "FROM epr_transaction_image "
            "WHERE transaction_id = %s AND image_url IS NOT NULL",
            (tx_id,),
        )
        images = [
            {"id": r[0], "name": r[1], "type": r[2], "type_id": r[3], "image_url": r[4]}
            for r in cur.fetchall()
        ]
    return raw_data, images


def _load_record_integrity_inputs(conn, tx_id):
    """Return [(record_id, record_raw_data, [image_dict, ...]), ...] for one tx.

    Skips soft-deleted records and image rows. Records with zero images are
    included with an empty list so the caller can decide whether to skip
    them (we do — no images means nothing to verify against)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, raw_data FROM epr_transaction_records_embeded "
            "WHERE transaction_id = %s AND deleted_date IS NULL",
            (tx_id,),
        )
        records = cur.fetchall()
        out = []
        for record_id, record_raw in records:
            cur.execute(
                "SELECT id, name, type, type_id, image_url "
                "FROM epr_transaction_record_image "
                "WHERE epr_transaction_record_id = %s "
                "AND image_url IS NOT NULL "
                "AND deleted_date IS NULL",
                (record_id,),
            )
            imgs = [
                {"id": r[0], "name": r[1], "type": r[2],
                 "type_id": r[3], "image_url": r[4]}
                for r in cur.fetchall()
            ]
            out.append((record_id, record_raw, imgs))
    return out


# Field names a record's raw_data may use for the per-material weight/quantity.
# Coalesced left-to-right; first non-None wins.
_RECORD_QUANTITY_FIELDS = (
    "totalQuantity", "quantity", "weight", "materialWeight", "kgQuantity",
)

# Field names a record's raw_data may use for the per-unit price.
# The legacy MySQL column is `price` (per-unit). Coalesce in case the API
# payload uses a different alias.
_RECORD_PRICE_FIELDS = (
    "price", "pricePerUnit", "unitPrice",
)


def _payload_for_integrity(raw_data, is_record=False):
    """Build the {transactionDate, totalQuantity, totalPrice, pricePerUnit}
    payload the integrity prompt expects.

    `invoiceNo` is intentionally NOT checked — it's freeform user-controlled
    text on the parent and rarely matches the document numbers printed on
    record-level files (scale tickets, QC certs, etc. carry their own refs).
    Verifying it generates more noise than signal.

    Parent (is_record=False):
      - `totalQuantity` and `totalPrice` from raw_data
      - `pricePerUnit` is None (parents track totals, not unit rates)
    Record (is_record=True):
      - Uses ONLY the record's own raw_data — does not inherit parent fields
      - Quantity coalesced via _RECORD_QUANTITY_FIELDS
      - `pricePerUnit` coalesced via _RECORD_PRICE_FIELDS (legacy MySQL stores
        per-unit price as `price`)
      - `totalPrice` is None (records track per-unit, not totals)

    Fields that resolve to None are sent to the LLM as `null` and the prompt
    instructs it to skip null fields entirely. So a record with only a
    quantity (no price) won't generate any price-related output.

    Returns None when EVERY field is None — caller should skip the image set.
    """
    raw = raw_data or {}
    tx_date = raw.get("transactionDate")

    if is_record:
        qty = _coalesce(raw, _RECORD_QUANTITY_FIELDS)
        ppu = _coalesce(raw, _RECORD_PRICE_FIELDS)
        total_price = None
    else:
        qty = raw.get("totalQuantity")
        total_price = raw.get("totalPrice")
        ppu = None

    payload = {
        "transactionDate": tx_date,
        "totalQuantity": qty,
        "totalPrice": total_price,
        "pricePerUnit": ppu,
    }
    if not any(v is not None and v != "" for v in payload.values()):
        return None
    return payload


def _coalesce(raw, field_names):
    """First non-empty value from `raw` looking up `field_names` in order."""
    for f in field_names:
        v = raw.get(f)
        if v is not None and v != "":
            return v
    return None


def _process_one_integrity_image(payload, img, extra_ctx):
    """Fetch + LLM-verify one image. Pure; no DB access, no shared state.
    Returns ('ok', img_ctx, llm_result) | ('error', err_dict) | ('skip',).
    Lives at module scope (not nested) so it pickles trivially if we ever
    swap to a process pool."""
    image_url = img.get("image_url")
    if not image_url:
        return ("skip",)

    img_ctx = {
        "image_id": img.get("id"),
        "image_type_id": img.get("type_id"),
        "image_type": img.get("type"),
        "image_name": img.get("name"),
        "source_image_url": image_url,
        **extra_ctx,
    }

    data_url = image_processing.safe_process_image(image_url)
    if data_url is None:
        return ("error", {**img_ctx, "error": "fetch_or_decode_failed"})

    try:
        result = openrouter.verify_integrity_against_image(
            data_url, payload, expected_type=img.get("type"),
        )
    except Exception as exc:
        logger.warning("integrity LLM call failed for image_id=%s url=%s: %s",
                       img.get("id"), image_url, exc)
        return ("error", {**img_ctx, "error": f"{type(exc).__name__}: {exc}"})

    return ("ok", img_ctx, result)


def _check_integrity_for_images(payload, images, extra_ctx=None):
    """Run the integrity LLM for ONE payload across a set of images. Aggregate
    issues / matched_fields / errors. Pure (no DB access).

    Images are processed in parallel up to _INTEGRITY_PARALLELISM workers —
    each call is pure HTTP I/O (image fetch + vision-LLM round-trip) and
    independent, so threading is safe. Aggregation happens single-threaded
    after futures complete, preserving input ordering for stable output.

    `extra_ctx` is merged into every issue and error emitted by this call —
    used to attach `record_id` for record-level runs so consumers can trace
    which record's image surfaced an issue.

    Fail-soft per-image: fetch/LLM/JSON errors land in `errors`, not raised.
    """
    extra_ctx = extra_ctx or {}
    image_list = list(images or [])
    if not image_list:
        return {"issues": [], "matched_fields": set(),
                "checked_image_count": 0, "errors": []}

    workers = min(_INTEGRITY_PARALLELISM, len(image_list))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        # ex.map preserves input order — needed so output is deterministic.
        results = list(ex.map(
            lambda img: _process_one_integrity_image(payload, img, extra_ctx),
            image_list,
        ))

    issues = []
    matched_set: set[str] = set()
    errors = []
    checked = 0
    for r in results:
        kind = r[0]
        if kind == "skip":
            continue
        if kind == "error":
            errors.append(r[1])
            continue
        # ok
        _, img_ctx, llm_result = r
        checked += 1
        cleaned_issues = _clean_false_positive_issues(llm_result.get("issues"), matched_set)
        for issue in cleaned_issues:
            issue.update(img_ctx)
            issues.append(issue)
        for f in (llm_result.get("matched_fields") or []):
            matched_set.add(str(f))

    return {
        "issues": issues,
        "matched_fields": matched_set,
        "checked_image_count": checked,
        "errors": errors,
    }


def _check_integrity(raw_data, parent_images, record_inputs=None):
    """LLM-based integrity check across the parent and all of its records.

    Verified fields: `transactionDate` and `totalQuantity`. `invoiceNo` is
    intentionally NOT checked (freeform user-controlled, noisy).

    For each parent image: verify against the parent's payload.
    For each record image: verify against that record's OWN payload — no
    parent inheritance. Records get checked on the data they actually carry
    (typically quantity from a scale ticket).

    Issues from record images are tagged with `record_id` so reviewers can
    identify the source. Records with no images or no verifiable fields
    are silently skipped.

    Returns:
      {
        "issues":              [...parent...],
        "matched_fields":      [...parent...],
        "checked_image_count": <parent count only>,
        "errors":              [...parent...],
        "records": [
          {"record_id": int, "issues": [...], "matched_fields": [...],
           "checked_image_count": int, "errors": [...]},
          ...
        ],
      }
    """
    # Parent
    parent_payload = _payload_for_integrity(raw_data)
    if parent_payload is None:
        parent_result = {"issues": [], "matched_fields": set(),
                         "checked_image_count": 0, "errors": []}
    else:
        parent_result = _check_integrity_for_images(parent_payload, parent_images)

    # Records
    records_out = []
    for record_id, record_raw, imgs in (record_inputs or []):
        if not imgs:
            continue
        rpayload = _payload_for_integrity(record_raw, is_record=True)
        if rpayload is None:
            continue
        r = _check_integrity_for_images(
            rpayload, imgs, extra_ctx={"record_id": record_id},
        )
        records_out.append({
            "record_id": record_id,
            "issues": r["issues"],
            "matched_fields": sorted(r["matched_fields"]),
            "checked_image_count": r["checked_image_count"],
            "errors": r["errors"],
        })

    return {
        "issues": parent_result["issues"],
        "matched_fields": sorted(parent_result["matched_fields"]),
        "checked_image_count": parent_result["checked_image_count"],
        "errors": parent_result["errors"],
        "records": records_out,
    }


def _write_dedup_outcome(conn, tx_id: int, candidates, integrity=None, reason=None):
    """Write dedup + integrity outcome to the parent transaction's
    `status` and `flags` columns AND each record's own `status` / `flags`.
    Records that were checked get their per-record integrity summary; records
    skipped (no images / no verifiable payload) get `passed` with
    `flags.integrity.skipped = true` so they're not stuck on `pending`.
    All updates committed in one small transaction."""
    integrity = integrity or {"issues": [], "matched_fields": [], "records": []}
    legacy_id_map = _fetch_legacy_ids(conn, [c.get("id") for c in candidates])
    flags_obj = {
        "duplicates": _summarize_candidates_for_flags(candidates, legacy_id_map),
        "integrity": {
            "issues": integrity.get("issues") or [],
            "matched_fields": integrity.get("matched_fields") or [],
            "checked_image_count": integrity.get("checked_image_count", 0),
            "errors": integrity.get("errors") or [],
            "records": integrity.get("records") or [],
            "checked_at": _now_iso(),
        },
        "dedup_at": _now_iso(),
    }
    if reason:
        flags_obj["reason"] = reason
    new_status = _determine_status(candidates, integrity)
    integrity_checked_at = flags_obj["integrity"]["checked_at"]
    record_summaries = {
        r["record_id"]: r for r in (integrity.get("records") or [])
    }

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_transactions_embeded "
            "SET flags = %s, status = %s, updated_date = NOW() "
            "WHERE id = %s",
            (Json(flags_obj), new_status, tx_id),
        )

        # Per-record outcomes. Pull every non-deleted record for this tx so we
        # cover records that were skipped by the integrity check (no images /
        # no verifiable payload) — those move from `pending` to `passed` with
        # a `skipped: true` marker so reviewers can tell they weren't verified.
        cur.execute(
            "SELECT id FROM epr_transaction_records_embeded "
            "WHERE transaction_id = %s AND deleted_date IS NULL",
            (tx_id,),
        )
        record_ids = [r[0] for r in cur.fetchall()]
        for record_id in record_ids:
            summary = record_summaries.get(record_id)
            if summary:
                record_flags = {
                    "integrity": {
                        "issues": summary["issues"],
                        "matched_fields": summary["matched_fields"],
                        "checked_image_count": summary["checked_image_count"],
                        "errors": summary["errors"],
                        "checked_at": integrity_checked_at,
                    },
                }
                record_status = "flagged" if summary.get("issues") else "passed"
            else:
                record_flags = {
                    "integrity": {
                        "issues": [],
                        "matched_fields": [],
                        "checked_image_count": 0,
                        "errors": [],
                        "checked_at": integrity_checked_at,
                        "skipped": True,
                    },
                }
                record_status = "passed"
            cur.execute(
                "UPDATE epr_transaction_records_embeded "
                "SET status = %s, flags = %s, updated_date = NOW() "
                "WHERE id = %s",
                (record_status, Json(record_flags), record_id),
            )
    conn.commit()
    return new_status, flags_obj


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _project_has_ai_audit(legacy_conn, project_id: int) -> bool:
    """Look up `epr_project.ai_audit` in the legacy MySQL DB. Returns True
    only when the column is explicitly truthy. Missing project / NULL flag
    default to False (safer — opt-in)."""
    with legacy_conn.cursor() as cur:
        cur.execute(
            "SELECT ai_audit FROM epr_project WHERE id = %s",
            (project_id,),
        )
        row = cur.fetchone()
    return bool(row[0]) if row and row[0] is not None else False


def _mark_skipped(conn, tx_id: int, reason: str) -> dict:
    """Stamp the parent tx + all its non-deleted records with status='skipped'
    and a small flags block explaining why. Used when the worker bails out
    before doing any LLM work (e.g. project's ai_audit flag is off)."""
    flags_obj = {"reason": reason, "skipped_at": _now_iso()}
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE epr_transactions_embeded "
            "SET status = %s, flags = %s, updated_date = NOW() "
            "WHERE id = %s",
            ("skipped", Json(flags_obj), tx_id),
        )
        cur.execute(
            "UPDATE epr_transaction_records_embeded "
            "SET status = %s, flags = %s, updated_date = NOW() "
            "WHERE transaction_id = %s AND deleted_date IS NULL",
            ("skipped", Json(flags_obj), tx_id),
        )
    conn.commit()
    return flags_obj


def _other_active_tx_exists(conn, project_id: int, tx_id: int) -> bool:
    """True if at least one OTHER transaction exists in this project (any
    is_active value, but not soft-deleted). Used to decide whether dedup
    has anything to compare against."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM epr_transactions_embeded "
            "WHERE epr_project_id = %s AND id != %s "
            "AND deleted_date IS NULL "
            "LIMIT 1",
            (project_id, tx_id),
        )
        return cur.fetchone() is not None


def process_transaction(conn, tx_id: int) -> Optional[dict]:
    """Background-process one transaction end-to-end:
       1. Ensure legacy data for this project has been imported (chunked,
          resumable). If still in progress, return early — the cron releases
          this job back to pending so it retries next tick.
       2. LLM-extract + description-embed every image with NULL extracted_data.
          Runs whether or not there's comparison data — extractions are
          needed for the per-transaction integrity check.
       3. Integrity check: payload (raw_data) vs image extractions.
       4. Dedup detection — only if other transactions exist in the project.
       5. Write combined outcome (status + flags) to the parent row.

    Per-image commits keep partial progress durable.
    """
    # Sanity check: does the transaction exist?
    with conn.cursor() as cur:
        cur.execute(
            "SELECT epr_project_id FROM epr_transactions_embeded "
            "WHERE id = %s AND deleted_date IS NULL",
            (tx_id,),
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("process_transaction: tx_id=%s not found / soft-deleted", tx_id)
            return None
        project_id = row[0]

    # Step 0/1: project gate + legacy import. One legacy connection serves both.
    #   0. Check `epr_project.ai_audit` in legacy DB — if disabled, mark the
    #      tx + records as 'skipped' and return early. No LLM work runs.
    #   1. Drive one chunk of legacy import for the project (may return
    #      'in_progress' if more chunks remain).
    if project_id is not None:
        legacy_conn = legacy_db.get_legacy_connection()
        try:
            if not _project_has_ai_audit(legacy_conn, project_id):
                _mark_skipped(conn, tx_id, "ai_audit_disabled")
                logger.info(
                    "process_transaction tx_id=%s: project %s has ai_audit=OFF, skipping",
                    tx_id, project_id,
                )
                return {
                    "skipped": True,
                    "reason": "ai_audit_disabled",
                    "project_id": project_id,
                }
            import_status, chunk_count = legacy_import.ensure_imported(
                legacy_conn, conn, project_id,
            )
        finally:
            legacy_conn.close()

        if import_status == "in_progress":
            logger.info(
                "process_transaction tx_id=%s: project %s import in progress "
                "(this tick imported %d), releasing job for retry",
                tx_id, project_id, chunk_count,
            )
            return {
                "retry_later": True,
                "reason": "import_in_progress",
                "project_id": project_id,
                "imported_this_tick": chunk_count,
            }

    # Step 2: extract any pending images for this transaction. Runs even when
    # there's no comparison data — the integrity check needs these.
    tx_imgs = _pending_transaction_images(conn, tx_id)
    rec_imgs = _pending_record_images(conn, tx_id)
    total_pending = len(tx_imgs) + len(rec_imgs)
    logger.info(
        "process_transaction tx_id=%s: %d transaction images, %d record images pending",
        tx_id, len(tx_imgs), len(rec_imgs),
    )
    extracted_count = 0
    for img_id, image_url in tx_imgs:
        if _update_image(conn, "epr_transaction_image", img_id, image_url):
            extracted_count += 1
    for img_id, image_url in rec_imgs:
        if _update_image(conn, "epr_transaction_record_image", img_id, image_url):
            extracted_count += 1

    # Step 3: integrity check — vision LLM looks at each image (documents,
    # scale readings, waste/cargo photos, anything) and judges whether the
    # content matches the user-submitted payload. The LLM decides per-image
    # which fields are verifiable. Image metadata (id, type, type_id, name)
    # gets attached to each issue so reviewers can identify the source.
    #
    # Both parent images and per-record images are checked. Record images
    # verify against the record's per-material payload (with invoiceNo /
    # transactionDate inherited from the parent), and issues from those
    # images carry `record_id` so reviewers can trace the source.
    raw_data, images = _load_integrity_inputs(conn, tx_id)
    record_inputs = _load_record_integrity_inputs(conn, tx_id)
    integrity = _check_integrity(raw_data, images, record_inputs)

    # Step 4: dedup — only when there's something to compare against.
    has_comparison = (
        project_id is not None
        and _other_active_tx_exists(conn, project_id, tx_id)
    )
    if has_comparison:
        report = duplicates.find_duplicates(conn, tx_id) or {}
        candidates = report.get("candidates") or []
        reason = None
    else:
        report = {"transaction_id": tx_id, "candidates": []}
        candidates = []
        reason = "no_comparison_data"
        logger.info(
            "process_transaction tx_id=%s: no comparison data in project %s",
            tx_id, project_id,
        )

    # Step 5: write combined outcome (dedup + integrity) to the parent row.
    new_status, flags_obj = _write_dedup_outcome(
        conn, tx_id, candidates, integrity=integrity, reason=reason,
    )

    report["images_processed"] = total_pending
    report["images_extracted"] = extracted_count
    report["integrity"] = integrity
    report["parent_status"] = new_status
    report["parent_flags"] = flags_obj
    if reason:
        report["reason"] = reason
    return report
