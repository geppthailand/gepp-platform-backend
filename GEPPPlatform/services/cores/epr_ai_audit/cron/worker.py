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
                # Small batch so a few slow multi-image transactions don't
                # blow past Lambda's 15-min timeout.
                claimed = jobs.claim_next_jobs(conn, jobs.STAGE_EMBEDDING, batch_size=3)
            for job_id, tx_id in claimed:
                try:
                    report = worker.process_transaction(conn, tx_id)
                    with conn:
                        jobs.mark_done(conn, job_id, report or {"missing": True})
                except Exception as exc:
                    with conn:
                        jobs.mark_failed(conn, job_id, repr(exc))
        finally:
            conn.close()
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional

from psycopg2.extras import Json

from GEPPPlatform.libs import image_processing, openrouter

from . import duplicates

logger = logging.getLogger(__name__)


def _to_vec_literal(vec):
    """pgvector accepts a string literal `[v1,v2,...]` cast to ::vector."""
    return "[" + ",".join(f"{float(x)}" for x in vec) + "]"


def _extract_and_embed(image_url: str, embed: bool = True):
    """Run vision LLM + (optionally) description embedding for one file URL.

    Returns (extracted_dict_or_None, description_vec_literal_or_None).
    All errors fail-soft so the caller can write NULLs and continue.

    `embed=False` skips the embedding call entirely — used for record-level
    images, whose embeddings nothing reads (dedup only searches parent-level
    images). Saves one embed_text call per record image.
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
    if embed and description:
        try:
            vec = openrouter.embed_text(description)
            desc_vec_literal = _to_vec_literal(vec)
        except Exception as exc:
            logger.warning("description embedding failed for %s: %s", image_url, exc)

    return extracted, desc_vec_literal


# Only parent-level images are searched by dedup (see duplicates.py), so only
# they need a description_embedding.
# ponytail: if record images ever join dedup, add the table here and to both
# candidate queries in duplicates.py.
_EMBEDDED_IMAGE_TABLES = {"epr_transaction_image"}


def _update_image(conn, table: str, img_id: int, image_url: str) -> bool:
    """Process one image row, write extracted_data + description_embedding,
    commit. Returns True if extraction populated `extracted_data`.

    `table` is a hardcoded literal from the caller, not user input. The
    commit-per-image policy keeps partial progress durable across crashes."""
    extracted, desc_vec_literal = _extract_and_embed(
        image_url, embed=table in _EMBEDDED_IMAGE_TABLES,
    )
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

# Only these confidence tiers are surfaced in flags.duplicates[]. `low-fuzzy`
# is too noisy for reviewers on document-heavy projects where tax IDs/vendors
# cluster naturally. The full candidate list — including the dropped tier — is
# still persisted on epr_dedup_jobs.result for audit.
# `medium` is included because it now carries vendor/date/total triple matches
# (demoted from high in duplicates._confidence) — worth a look, not worth an
# auto-flag.
_SURFACED_CONFIDENCE_TIERS = {"high", "medium", "medium-fuzzy"}

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


# Thai names for the document slot types, for the Thai half of an
# explanation. transaction_image_types carries only an English `desctiption`
# and nothing in either database translates these — I scanned 1,426 text
# columns across both. ai_audit_document_types has name_th but for a
# different, five-entry vocabulary ("Weight Ticket", not
# product_weighing_sheet), so it cannot be joined to.
#
# If the frontend already renders these names in Thai, that map is the real
# source and this should be replaced by it rather than competing with it.
# Until then an untranslated key renders as the raw slug, which is what the
# Thai sentence used to show for every one of them.
_IMAGE_TYPE_TH = {
    "uncategorized": "ไม่ระบุประเภท",
    "invoice": "ใบแจ้งหนี้",
    "bill_of_lading": "ใบตราส่งสินค้า",
    "qc_file": "เอกสารตรวจสอบคุณภาพ",
    "receipt": "ใบเสร็จรับเงิน",
    "cash_bill": "บิลเงินสด",
    "payment_voucher": "ใบสำคัญจ่าย",
    "tax_invoice": "ใบกำกับภาษี",
    "id_card": "บัตรประชาชน",
    "invoice/receipt/cash_bill/payment_voucher":
        "ใบแจ้งหนี้ / ใบเสร็จรับเงิน / บิลเงินสด / ใบสำคัญจ่าย",
    "invoice/tax_invoice/cash_bill/payment_voucher/id_card":
        "ใบแจ้งหนี้ / ใบกำกับภาษี / บิลเงินสด / ใบสำคัญจ่าย / บัตรประชาชน",
    "money_transfer_document": "เอกสารการโอนเงิน",
    "production_report": "รายงานการผลิต",
    "monthly_progress_report": "รายงานความคืบหน้ารายเดือน",
    "production_other_report": "รายงานการผลิตอื่น ๆ",
    "product_weighing_sheet": "ใบชั่งน้ำหนักสินค้า",
    "product_weighing_sheet/product_weighing_image":
        "ใบชั่งน้ำหนักสินค้า / รูปถ่ายการชั่งน้ำหนัก",
    "product_image": "รูปถ่ายสินค้า",
    "epr_payment_attachment": "เอกสารแนบการชำระเงิน EPR",
    "epr_payment_confirm_file": "เอกสารยืนยันการชำระเงิน EPR",
    "gepp_business_ocr_input": "ไฟล์นำเข้า OCR",
    "gepp_business_ocr_output": "ไฟล์ผลลัพธ์ OCR",
}


def _type_th(name):
    """The Thai name for a slot type, or the raw key when none is known."""
    return _IMAGE_TYPE_TH.get(str(name or "").strip().lower(), name)


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


# How far the recorded transaction date may sit from the NEAREST date on a
# document. Measured over 538 real transactions on dev, comparing candidate
# rules against their stored document_date extractions:
#
#     window      nearest-date rule     anchored on earliest
#     +/-1              96.5%                  48.3%
#     +/-3              98.3%                  52.2%
#     +/-5              99.4%                  55.2%
#
# Anchoring on the earliest document rejected nearly half of real traffic: the
# single largest bucket is the transaction dated ONE DAY BEFORE any document
# (195 of 538), because the paperwork is written up the day after the material
# moves. Nearest-date has no such directional assumption and needs no choice of
# a "main" date.
#
# +/-3 rather than +/-1 because document dates come from the vision model and
# it does misread Buddhist years (67 for 69 has been seen), so a tight window
# fails honest transactions on an OCR slip. Past +/-3 the curve flattens — +/-5
# buys 1.1% and starts admitting genuinely mismatched evidence.
_DATE_WINDOW_DAYS = 3


# A date-shaped substring is not necessarily a date. Tax ids, serial numbers
# and phone numbers match DD/MM/YYYY, and one produced "1983-10-08" on a 2026
# transaction — flagged as 15,655 days out. Anything this far from the
# submitted date is extraction noise, not evidence of a discrepancy, so it is
# dropped before the comparison rather than counted against the transaction.
_DATE_PLAUSIBLE_DAYS = 730          # ~2 years either side


def _plausible_dates(seen, want):
    """Drop date-shaped noise. Returns (kept, dropped)."""
    kept, dropped = [], []
    for d in seen:
        (kept if abs((d - want).days) <= _DATE_PLAUSIBLE_DAYS else dropped).append(d)
    return kept, dropped


def _same_day_and_month(a, b, window):
    """Is `a` within `window` days of `b`, ignoring the YEAR?

    The year is the unreliable digit. A Thai two-digit Buddhist year (69 for
    2026) comes back from the vision model as 67, 2069 or 2019 on different
    calls over the SAME document, while the day and month are read correctly
    almost every time. Measured on project 50: every date "mismatch" had a
    correct day and month and a mangled year.

    So the comparison projects both dates onto one year. A document genuinely
    a year old with the same day and month would pass, which is far rarer than
    the misread it prevents.
    """
    for year_shift in (0, -1, 1):
        try:
            projected = a.replace(year=b.year + year_shift)
        except ValueError:          # 29 Feb onto a non-leap year
            continue
        if abs((projected - b).days) <= window:
            return True
    return False


def _date_supported_by_documents(payload_date, date_blob):
    """Is the recorded transaction date close to ANY date on this document?

    Returns (ok, nearest, reason_fragment).

    Documents for one delivery carry different dates by design — weighed one
    day, QC-signed the next, invoiced after that — and the recorded date can
    fall either side of them. So the test is distance to the CLOSEST date on
    the document, in either direction, rather than a rule about which one
    comes first.
    """
    want = _parse_date_flexible(payload_date)
    seen = sorted(_extract_all_dates(date_blob))
    if want is None or not seen:
        return (None, None, None)
    # Year-blind FIRST, against every parsed candidate — before the noise
    # filter. A misread year can land a real date decades away (2069 for
    # 2026), and dropping it as implausible would discard the very reading
    # that matches. A matching day and month is itself evidence the string is
    # a date rather than a serial number.
    for d in seen:
        if _same_day_and_month(d, want, _DATE_WINDOW_DAYS):
            exact = abs((want - d).days)
            if exact <= _DATE_WINDOW_DAYS:
                if exact == 0:
                    return (True, d, f"the same day as {d} on the document")
                side = "after" if (want - d).days > 0 else "before"
                return (True, d,
                        f"{exact} day(s) {side} {d} on the document, within the "
                        f"{_DATE_WINDOW_DAYS}-day allowance")
            return (True, d,
                    f"the same day and month as {d} on the document — the year "
                    f"differs, which is the digit the model misreads on Thai "
                    f"two-digit Buddhist dates")

    # No day/month match anywhere. Now drop date-shaped noise before deciding
    # whether what is left actually contradicts the submitted date.
    seen, _noise = _plausible_dates(seen, want)
    if not seen:
        return (None, None, None)
    nearest = min(seen, key=lambda x: abs((want - x).days))
    gap = (want - nearest).days
    if abs(gap) <= _DATE_WINDOW_DAYS:
        if gap == 0:
            return (True, nearest, f"the same day as {nearest} on the document")
        side = "after" if gap > 0 else "before"
        return (True, nearest,
                f"{abs(gap)} day(s) {side} {nearest} on the document, within the "
                f"{_DATE_WINDOW_DAYS}-day allowance")
    side = "after" if gap > 0 else "before"
    return (False, nearest,
            f"{abs(gap)} days {side} the closest document date {nearest}, "
            f"beyond the {_DATE_WINDOW_DAYS}-day allowance")


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


                                                        # noqa: E501
# Month names, Thai and English, full and abbreviated. Thai documents very
# often write "21 มกราคม 2568" rather than 21/01/2568, and the numeric
# patterns above cannot see those at all.
_MONTH_NAMES = {
    "มกราคม": 1, "ม.ค.": 1, "ก.พ.": 2, "กุมภาพันธ์": 2, "มีนาคม": 3, "มี.ค.": 3,
    "เมษายน": 4, "เม.ย.": 4, "พฤษภาคม": 5, "พ.ค.": 5, "มิถุนายน": 6, "มิ.ย.": 6,
    "กรกฎาคม": 7, "ก.ค.": 7, "สิงหาคม": 8, "ส.ค.": 8, "กันยายน": 9, "ก.ย.": 9,
    "ตุลาคม": 10, "ต.ค.": 10, "พฤศจิกายน": 11, "พ.ย.": 11, "ธันวาคม": 12, "ธ.ค.": 12,
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
# Longest names first so "มี.ค." wins over a shorter prefix, and "march"
# is not shadowed by "mar".
_MONTH_ALT = "|".join(
    re.escape(k) for k in sorted(_MONTH_NAMES, key=len, reverse=True)
)
# "21 มกราคม 2568" / "21 Jan 2025"
_DMY_NAME_RE = re.compile(rf"(\d{{1,2}})\s*({_MONTH_ALT})\s*(\d{{4}})", re.IGNORECASE)
# "March 31, 2025" / "Jan 5 2025"
_MDY_NAME_RE = re.compile(rf"({_MONTH_ALT})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)


def _extract_named_dates(s):
    """Yield dates written with a Thai or English month name."""
    for rx, order in ((_DMY_NAME_RE, "dmy"), (_MDY_NAME_RE, "mdy")):
        for m in rx.finditer(s):
            if order == "dmy":
                d, name, y = m.group(1), m.group(2), m.group(3)
            else:
                name, d, y = m.group(1), m.group(2), m.group(3)
            mo = _MONTH_NAMES.get(name.lower()) or _MONTH_NAMES.get(name)
            if not mo:
                continue
            sd = _safe_date(int(y), mo, int(d))
            if sd:
                yield sd


def _extract_all_dates(s):
    """Yield every date-shaped substring in `s` as a `datetime.date`,
    auto-converting Buddhist years. Tries ISO first, then DD/MM/YYYY,
    then DD/MM/YY-shorthand, then Thai/English month names. Each
    match-position is consumed only once per pattern, but the function
    returns all distinct dates found."""
    if not s:
        return
    s = str(s)
    seen = set()

    for sd in _extract_named_dates(s):
        if sd not in seen:
            seen.add(sd)
            yield sd

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


def _use_python_judge() -> bool:
    """True when the integrity verdict is decided in Python from LLM sightings
    instead of asking the LLM to compare.

    This is the default everywhere. EPR_INTEGRITY_JUDGE=llm falls back to the
    old path, where the LLM is handed the payload and asked to compare, and
    Python string-matches its prose.

    ponytail: env flag, not a settings table — it is only a rollback lever, so
    delete it (and the LLM-compare path with it) once nothing has needed to
    pull it. Read per-call so it can be flipped on a warm Lambda.
    """
    return os.environ.get("EPR_INTEGRITY_JUDGE", "").lower() != "llm"


# Label keywords that mark a number as the document's grand total / the weight,
# used to prefer the authoritative figure over an incidental sighting.
_TOTAL_LABEL_HINTS = (
    "total", "grand total", "net amount", "amount", "sum",
    "รวม", "รวมเงิน", "รวมทั้งสิ้น", "ยอดรวม", "จำนวนเงิน",
)
_QUANTITY_LABEL_HINTS = (
    "weight", "qty", "quantity", "gross", "tare",
    "น้ำหนัก", "ปริมาณ", "กก", "kg",
)
# Deliberately NOT in the quantity hints:
#   "จำนวน"  — prefix of "จำนวนเงิน" (amount of MONEY), so it matched baht
#              figures on money-transfer slips and flagged them as weights.
#   "net"    — appears in "Net Amount", also money.
# Both were observed misfiring on live project-41 data.

# A label carrying any of these is about money, never a weight.
_MONEY_LABEL_MARKERS = (
    "เงิน", "บาท", "ราคา", "amount", "price", "total", "฿", "thb", "baht", "cost",
)


def _label_matches(label, hints):
    lowered = str(label or "").lower()
    return any(h in lowered for h in hints)


def _is_money_label(label):
    return _label_matches(label, _MONEY_LABEL_MARKERS)


def _all_numbers_in(value):
    """Every number-shaped token in `value`, as floats.

    _parse_number returns only the FIRST token, which is wrong for a sighting
    like "270 x 12 = 2,040" — the per-unit rate is the second multiplicand.
    The sighting prompt asks for A, B and C as separate entries, but the model
    will sometimes return the whole expression, so sweep it.
    """
    if value is None or value == "":
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    s = str(value)
    for noise in ("฿", "$", "บาท", "thb", "kg", "kgs", "กก.", "กก"):
        s = s.replace(noise, " ")
    out = []
    for tok in _NUMERIC_TOKEN_RE.findall(s):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _value_sighted(payload_value, seen_values, tolerance=0.01):
    """True if `payload_value` matches ANY number appearing in `seen_values`."""
    target = _parse_number(payload_value)
    if target is None:
        return False
    for v in seen_values:
        for n in _all_numbers_in(v):
            if target == 0 and n == 0:
                return True
            if target == 0 or n == 0:
                continue
            if abs(target - n) / max(abs(target), abs(n)) <= tolerance:
                return True
    return False


def _net_of_two(payload_value, values, tolerance=0.01):
    """True if `payload_value` is the difference of two numbers in `values`.

    Scale tickets print GROSS and TARE and expect the reader to take the net:
    4,270 - 1,780 = 2,490, where only 2,490 is submitted. Without this a
    perfectly good weighing slip reads as a mismatch.

    Deliberately narrow — subtraction of two sighted values only. Not general
    arithmetic: summing line items would let almost any payload find a
    combination that fits, which is how a sighting check stops meaning anything.
    """
    target = _parse_number(payload_value)
    if target is None or target <= 0:
        return False
    nums = sorted({n for v in values for n in _all_numbers_in(v) if n > 0},
                  reverse=True)
    for i, big in enumerate(nums):
        for small in nums[i + 1:]:
            diff = big - small
            if diff <= 0:
                continue
            if abs(target - diff) / max(abs(target), abs(diff)) <= tolerance:
                return True
    return False


def _judge_field_numeric(payload_value, numbers_seen, label_hints=None,
                         allow_net=False):
    """Decide MATCH / MISMATCH / CANT_VERIFY for one numeric field.

    Returns (outcome, what_the_image_showed). The second element is populated
    on a MATCH as well as a mismatch — a confirmation that cannot name the
    figure it matched reads as "matches the image. Seen: None", which looks
    like a bug rather than a pass.

    Labelled numbers are authoritative: when the image has a number whose
    label looks like this field, only those decide the outcome. Otherwise fall
    back to a sighting check — the payload value appearing ANYWHERE on the
    image counts as a match, matching the deliberately lenient rule the old
    prompt used for pricePerUnit.
    """
    if _is_empty_payload_value(payload_value):
        return ("cant_verify", None)

    entries = [e for e in (numbers_seen or []) if isinstance(e, dict)]
    values = [e.get("value") for e in entries]
    values = [v for v in values if not _is_empty_payload_value(v)]
    if not values:
        return ("cant_verify", None)

    if label_hints is None:
        # Sighting-only field (pricePerUnit). Unit rates get scribbled in
        # margins, so an appearance anywhere counts. Absence proves nothing —
        # never a mismatch, only unverifiable.
        if _value_sighted(payload_value, values):
            return ("match", ", ".join(str(v) for v in values))
        return ("cant_verify", None)

    labelled = [e.get("value") for e in entries
                if _label_matches(e.get("label"), label_hints)
                and not (label_hints is _QUANTITY_LABEL_HINTS
                         and _is_money_label(e.get("label")))
                and not _is_empty_payload_value(e.get("value"))]
    # A 0.00 in a labelled field is an unfilled template placeholder, not
    # evidence.
    labelled = [v for v in labelled if any(n != 0.0 for n in _all_numbers_in(v))]

    if not labelled:
        # This image carries no authoritative figure for this field — e.g. a
        # weight asked of a money-transfer slip. Whether some unrelated number
        # happens to differ says nothing, so CANT VERIFY rather than mismatch.
        return ("cant_verify", None)

    seen_repr = ", ".join(str(v) for v in labelled)
    if _value_sighted(payload_value, labelled):
        return ("match", seen_repr)
    if allow_net and _net_of_two(payload_value, labelled):
        # Derived, not printed: a weighbridge ticket shows gross and tare and
        # the net is the difference. Saying "matches the image. Seen: 17,730,
        # 11,830" for a submitted 5,900 reads as a false pass — neither number
        # is the value. A separate outcome so the caller can say what it did.
        return ("match_net", seen_repr)
    return ("mismatch", ", ".join(str(v) for v in labelled))


def _judge_sightings(payload, sightings, expected_type=None):
    """Compare a payload against what the LLM reported seeing, in Python.

    Same return shape as openrouter.verify_integrity_against_image() so this
    drops straight into _check_integrity_for_images:
      {"verdict": "passed"|"flagged", "issues": [...], "matched_fields": [...]}

    Every comparison here is arithmetic and deterministic — the same sightings
    always yield the same verdict. Nothing needs
    _clean_false_positive_issues(), because no prose is produced to misfile.
    """
    sightings = sightings or {}
    dates_seen = [e for e in (sightings.get("dates_seen") or []) if isinstance(e, dict)]
    numbers_seen = sightings.get("numbers_seen") or []

    issues = []
    matched = []
    confirmed = []
    unverified = []

    def flag(field, payload_value, seen, en, th):
        issues.append({
            "field": field,
            "payload_value": payload_value,
            "image_indicates": seen or "not shown",
            "explanation": {"en": en, "th": th},
        })

    def cant_verify(field, payload_value, en, th):
        """Examined, but the image gave nothing to compare against.

        _judge_field_numeric has always been able to say "cant_verify" and the
        caller only handled match and mismatch, so the field fell out of both
        lists — indistinguishable from one that was never checked at all. That
        is not a pass and it is not a failure; it is an unanswered question,
        and a reviewer has to be able to see which fields are in it.
        """
        unverified.append({
            "field": field,
            "payload_value": payload_value,
            "image_indicates": "not shown",
            "explanation": {"en": en, "th": th},
        })

    def confirm(field, payload_value, seen, en, th):
        """A match, recorded with the same detail as a mismatch.

        `matched_fields` has only ever held field NAMES, so a reviewer could
        see that something passed but not what it was checked against — while
        the mismatch beside it carried both values and an explanation. The
        data was in hand at this point either way; only the failure path kept
        it. Names still go to `matched` so existing consumers are untouched.
        """
        matched.append(field)
        confirmed.append({
            "field": field,
            "payload_value": payload_value,
            "image_indicates": seen or "not shown",
            "explanation": {"en": en, "th": th},
        })

    # ── transactionDate ────────────────────────────────────────────────────
    tx_date = payload.get("transactionDate")
    if not _is_empty_payload_value(tx_date):
        normalized = _normalize_payload_date_local(tx_date)
        date_blob = " ".join(str(e.get("value") or "") for e in dates_seen)
        # Compare against BOTH the raw calendar date and the T17-shifted one,
        # each ±1 day. The legacy "T17:00:00 = next day in Bangkok" convention
        # does not hold for every historical row, so a date that matches
        # either reading is a match — this is what the old prompt's two-layer
        # normalize-then-tolerate approach was reaching for.
        candidates = {normalized, str(tx_date)[:10]}
        # A date string we cannot PARSE is CANT VERIFY, never a mismatch. The
        # model reports dates verbatim, so an unrecognised format (or a script
        # we have no pattern for) must not manufacture a false flag — that is
        # the whole failure mode this design exists to remove.
        # Three outcomes, not two: an unreadable or noise-only date is CANT
        # VERIFY, never a mismatch. Collapsing it into the else branch flagged
        # transactions whose only date-shaped text was a serial number.
        results = [_date_supported_by_documents(c, date_blob)
                   for c in candidates if c]
        supported = next((r for r in results if r[0] is True), None)
        contradicted = next((r for r in results if r[0] is False), None)
        seen = ", ".join(
            f"{e.get('label') or 'date'}: {e.get('value')}" for e in dates_seen
        )

        if supported:
            _ok, nearest, why = supported
            confirm("transactionDate", tx_date, seen,
                    f"{normalized} is {why}. Seen: {seen}.",
                    f"{normalized} ห่างจากวันที่ใกล้ที่สุดในเอกสาร ({nearest}) "
                    f"ไม่เกิน {_DATE_WINDOW_DAYS} วัน พบ: {seen}")
        elif contradicted:
            flag("transactionDate", tx_date, seen,
                 f"{normalized} is not supported by the document dates: "
                 f"{contradicted[2]}. Seen: {seen}.",
                 f"{normalized} ไม่สอดคล้องกับวันที่ในเอกสาร พบ: {seen}")
        else:
            cant_verify("transactionDate", tx_date,
                        "No readable date on the image to compare against.",
                        "ไม่พบวันที่ที่อ่านได้ในรูปเพื่อเปรียบเทียบ")

    # ── numeric fields ─────────────────────────────────────────────────────
    for field, hints, en_label, th_label, allow_net in (
        ("totalQuantity", _QUANTITY_LABEL_HINTS, "quantity", "ปริมาณ", True),
        ("totalPrice", _TOTAL_LABEL_HINTS, "total price", "ยอดรวม", False),
        # pricePerUnit stays sighting-only (no label hints) — unit rates are
        # scribbled in margins on real Thai recycling documents.
        ("pricePerUnit", None, "unit price", "ราคาต่อหน่วย", False),
    ):
        value = payload.get(field)
        outcome, seen = _judge_field_numeric(value, numbers_seen, hints,
                                            allow_net=allow_net)
        if outcome == "match":
            confirm(field, value, seen,
                    f"Submitted {en_label} {value} matches the image. Seen: {seen}.",
                    f"{th_label}ที่กรอก {value} ตรงกับในรูป พบ: {seen}")
        elif outcome == "match_net":
            confirm(field, value, seen,
                    f"Submitted {en_label} {value} is the difference between the "
                    f"figures on the image ({seen}) — gross minus tare.",
                    f"{th_label}ที่กรอก {value} เท่ากับผลต่างของตัวเลขในรูป "
                    f"({seen}) คือ น้ำหนักรวมลบน้ำหนักภาชนะ")
        elif outcome == "mismatch":
            flag(field, value, seen,
                 f"Submitted {en_label} {value} does not match the image. Seen: {seen}.",
                 f"{th_label}ที่กรอก {value} ไม่ตรงกับในรูป พบ: {seen}")
        elif not _is_empty_payload_value(value):
            # Submitted, examined, and the image had nothing to check it
            # against. Silence here would read as a pass.
            cant_verify(field, value,
                        f"No readable {en_label} on the image to compare against.",
                        f"ไม่พบ{th_label}ที่อ่านได้ในรูปเพื่อเปรียบเทียบ")

    # ── imageType ──────────────────────────────────────────────────────────
    # The one genuinely semantic judgement, so it stays with the LLM — but as
    # a tri-state boolean, not prose that has to be string-matched afterwards.
    stated = expected_type
    content = sightings.get("image_content") or "unclear"
    # The model's own description, in Thai, so the Thai sentence is not half
    # English. Falls back to the English phrase on an older row.
    content_th = sightings.get("image_content_th") or content
    elements = sightings.get("identifying_elements") or ""
    elements_th = sightings.get("identifying_elements_th") or elements
    because = f" Identified by: {elements}." if elements else ""
    because_th = f" สังเกตจาก: {elements_th}" if elements_th else ""

    if stated and str(stated).lower() in _GENERIC_IMAGE_TYPES:
        # "Is this specifically a product image" has no wrong answer — a photo
        # of bottles IS one. But these slots are for the MATERIAL, so a sheet
        # of paperwork filed here is wrong and that IS answerable. A photo of
        # goods with a label or a stray document in frame stays fine; only a
        # page read for its text counts as a document.
        #
        # A document that CARRIES product photos (a delivery sheet with the
        # truck and the bales pasted on it) still shows the material, which is
        # what the slot is for. Paper wrapping does not make it the wrong file.
        is_doc = sightings.get("is_paper_document")
        if sightings.get("shows_material") is True:
            is_doc = False
        if is_doc is True:
            flag("imageType", stated, content,
                 f"'{stated}' should be a photo of the material, but the image "
                 f"is a paper document: {content}.{because}",
                 f"'{_type_th(stated)}' ควรเป็นรูปถ่ายของวัสดุ แต่รูปนี้เป็นเอกสาร: "
                 f"{content_th}{because_th}")
        elif is_doc is False:
            confirm("imageType", stated, content,
                    f"The image shows the material: {content}.{because}",
                    f"รูปแสดงตัววัสดุ: {content_th}{because_th}")
        else:
            cant_verify(
                "imageType", stated,
                f"Could not tell whether '{stated}' holds a photo of the "
                f"material or paperwork. The image appears to be {content}.{because}",
                f"ไม่สามารถระบุได้ว่า '{_type_th(stated)}' เป็นรูปวัสดุหรือเอกสาร "
                f"รูปเป็น {content_th}{because_th}",
            )
    elif stated:
        verdict = sightings.get("matches_stated_type")
        if verdict is True:
            confirm("imageType", stated, content,
                    f"The image appears to be {content}, matching the stated "
                    f"type '{stated}'.{because}",
                    f"รูปเป็น {content_th} ตรงกับประเภทที่ระบุ '{_type_th(stated)}'{because_th}")
        elif verdict is False:
            flag("imageType", stated, content,
                 f"Stated type '{stated}' but the image appears to be "
                 f"{content}.{because}",
                 f"ระบุประเภทเป็น '{_type_th(stated)}' แต่ในรูปเป็น {content_th}{because_th}")

    return {
        "verdict": "flagged" if issues else "passed",
        "issues": issues,
        "matched_fields": matched,
        # Same shape as `issues`, for the fields that passed.
        "confirmations": confirmed,
        # And for the ones that could be neither confirmed nor contradicted.
        "unverified": unverified,
    }


def _normalize_payload_date_local(date_str):
    """Apply the legacy T17:00:00-is-next-day-in-Bangkok convention.

    Delegates to openrouter._normalize_payload_date so the LLM path and the
    Python judge cannot drift apart on this rule.
    """
    return openrouter._normalize_payload_date(date_str)


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
        if _use_python_judge():
            sightings = openrouter.read_image_sightings(
                data_url, expected_type=img.get("type"),
            )
            result = _judge_sightings(payload, sightings, expected_type=img.get("type"))
            # Issues came from arithmetic, not prose — nothing to un-misfile.
            result["_prejudged"] = True
        else:
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
        return {"issues": [], "matched_fields": set(), "confirmations": [],
                "unverified": [], "checked_image_count": 0, "errors": []}

    workers = min(_INTEGRITY_PARALLELISM, len(image_list))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        # ex.map preserves input order — needed so output is deterministic.
        results = list(ex.map(
            lambda img: _process_one_integrity_image(payload, img, extra_ctx),
            image_list,
        ))

    issues = []
    matched_set: set[str] = set()
    confirmations = []
    unverified = []
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
        # The Python judge emits no prose, so there is nothing to un-misfile.
        # Running the phrase-matching cleanup over it could only cause harm.
        if llm_result.get("_prejudged"):
            cleaned_issues = llm_result.get("issues") or []
        else:
            cleaned_issues = _clean_false_positive_issues(
                llm_result.get("issues"), matched_set)
        for issue in cleaned_issues:
            issue.update(img_ctx)
            issues.append(issue)
        for f in (llm_result.get("matched_fields") or []):
            matched_set.add(str(f))
        for c in (llm_result.get("confirmations") or []):
            c.update(img_ctx)
            confirmations.append(c)
        for u in (llm_result.get("unverified") or []):
            u.update(img_ctx)
            unverified.append(u)

    return {
        "issues": issues,
        "matched_fields": matched_set,
        "confirmations": confirmations,
        "unverified": unverified,
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
        parent_result = {"issues": [], "matched_fields": set(), "confirmations": [],
                         "unverified": [], "checked_image_count": 0, "errors": []}
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
            "confirmations": r.get("confirmations") or [],
            "unverified": r.get("unverified") or [],
            "checked_image_count": r["checked_image_count"],
            "errors": r["errors"],
        })

    return {
        "issues": parent_result["issues"],
        "matched_fields": sorted(parent_result["matched_fields"]),
        "confirmations": parent_result.get("confirmations") or [],
        "unverified": parent_result.get("unverified") or [],
        "checked_image_count": parent_result["checked_image_count"],
        "errors": parent_result["errors"],
        "records": records_out,
    }


# Statuses only a person sets. The worker never produces these, so seeing one
# means the row has been reviewed.
_HUMAN_DECIDED_STATUSES = frozenset({"approved", "rejected"})


def _write_dedup_outcome(conn, tx_id: int, candidates, integrity=None, reason=None):
    """Write dedup + integrity outcome to the parent transaction's
    `status` and `flags` columns AND each record's own `status` / `flags`.
    Records that were checked get their per-record integrity summary; records
    skipped (no images / no verifiable payload) get `passed` with
    `flags.integrity.skipped = true` so they're not stuck on `pending`.
    All updates committed in one small transaction."""
    integrity = integrity or {"issues": [], "matched_fields": [],
                              "confirmations": [], "unverified": [], "records": []}
    legacy_id_map = _fetch_legacy_ids(conn, [c.get("id") for c in candidates])
    flags_obj = {
        "duplicates": _summarize_candidates_for_flags(candidates, legacy_id_map),
        "integrity": {
            "issues": integrity.get("issues") or [],
            "matched_fields": integrity.get("matched_fields") or [],
            # Why each matched field passed, same shape as `issues`.
            "confirmations": integrity.get("confirmations") or [],
            "unverified": integrity.get("unverified") or [],
            "checked_image_count": integrity.get("checked_image_count", 0),
            "errors": integrity.get("errors") or [],
            "records": integrity.get("records") or [],
            "checked_at": _now_iso(),
        },
        "dedup_at": _now_iso(),
    }
    if reason:
        flags_obj["reason"] = reason
    # A person's decision outranks a re-run. status goes
    # pending -> passed|flagged|skipped from here, then approved|rejected once
    # a human reviews; re-processing a reviewed row used to overwrite that
    # silently, so a requeue or a replay threw away the review. The fresh
    # verdict still lands in `flags` — only `status` is held.
    new_status = _determine_status(candidates, integrity)
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM epr_transactions_embeded WHERE id = %s",
                    (tx_id,))
        row = cur.fetchone()
    prior = row[0] if row else None
    if prior in _HUMAN_DECIDED_STATUSES:
        logger.info("tx=%s keeping human status %r (ai said %r)",
                    tx_id, prior, new_status)
        flags_obj["ai_status"] = new_status
        new_status = prior
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
                        "confirmations": summary.get("confirmations") or [],
                        "unverified": summary.get("unverified") or [],
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
                        "confirmations": [],
                        "unverified": [],
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
       1. LLM-extract + description-embed every image with NULL extracted_data.
          Runs whether or not there's comparison data — extractions are
          needed for the per-transaction integrity check.
       2. Integrity check: payload (raw_data) vs image extractions.
       3. Dedup detection — only if other transactions exist in the project.
       4. Write combined outcome (status + flags) to the parent row.

    Every queued transaction is audited — there is no per-project on/off gate.

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

    # Step 1: extract any pending images for this transaction. Runs even when
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

    # Step 2: integrity check — vision LLM looks at each image (documents,
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

    # Step 3: dedup — only when there's something to compare against.
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

    # Step 4: write combined outcome (dedup + integrity) to the parent row.
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
