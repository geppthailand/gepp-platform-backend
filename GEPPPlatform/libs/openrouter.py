"""
OpenRouter client wrapper.

Active surface:
  - get_openrouter_client() : OpenAI SDK pointed at OpenRouter's compat endpoint
  - call_llm()              : generic chat-completion helper (text + optional images)
  - extract_image_data()    : vision-LLM JSON extraction for the EPR dedup pipeline
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"
# Integrity check uses a different model than extraction. The vision-LLM rules
# in INTEGRITY_PROMPT have nested "DO NOT" / "MUST NOT" / "OMIT" instructions
# that cheaper models routinely ignore on edge cases (numeric formatting,
# misread address numbers as dates, "consistent with" filed as issue, etc.).
#
# Trial history:
#   gpt-4o-mini          — handles PDFs + JSON mode, accuracy too weak
#   anthropic/haiku-4.5  — PDFs return 400 (OpenRouter chat-completions doesn't
#                          translate PDF data URLs for Anthropic), JPGs return
#                          empty content (response_format ignored)
#   openai/gpt-4.1-mini  — JPG accuracy excellent (zero false positives in
#                          tests), but PDFs return 400 — same OpenAI limit.
#                          ~60% of our images are PDFs (scale tickets / QC
#                          certs), so this blocked production use.
#   google/gemini-2.5-pro — Native PDF, 100% success rate, ~$0.022/call.
#                          Strong baseline.
#   google/gemini-3.5-flash — CURRENT. Newer Gemini generation. Pricing is
#                          actually similar to 2.5 Pro ($1.50/M input vs
#                          $1.25/M) — the "Flash" name is misleading. Native
#                          PDF support. Testing to see if it edges out 2.5 Pro
#                          on the trickier rule-following cases.
INTEGRITY_MODEL = "google/gemini-3.5-flash"
DEFAULT_TEXT_EMBEDDING_MODEL = "openai/text-embedding-3-small"  # 1536 dim
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 4096
EXTRACT_TIMEOUT_SECS = 90  # vision LLM round-trip headroom

EXTRACTION_PROMPT = """You are analyzing an image or PDF from a recycling/waste management transaction. The file may be:
- A structured document (invoice, tax invoice, receipt, payment voucher, ID card, production report, money transfer document)
- A scene photo (waste pile/material, weighing scale, vehicle with cargo, etc.)

Extract the following JSON. Use null for fields that don't apply. Don't guess — only extract what's clearly visible/readable.

{
  "scene_type": one of: "invoice", "tax_invoice", "receipt", "payment_voucher", "production_report", "id_card", "money_transfer_document", "waste_photo", "scale_reading", "vehicle_with_cargo", "other",
  "key_identifiers": array of any unique strings (invoice numbers, license plates, tax IDs, serial numbers, receipt numbers); empty array if none,
  "document_number": string or null,
  "vendor_name": string or null,
  "document_date": ISO date string (YYYY-MM-DD) or null,
  "total_amount": number or null,
  "currency": 3-letter code or null,
  "weight": {"value": number, "unit": string} or null,
  "license_plate": string or null,
  "visual_description": "1-2 sentence concise description of identifying features"
}

Return ONLY the JSON object. No commentary, no markdown fences."""


INTEGRITY_PROMPT = """You are verifying that a user-submitted EPR (recycling) transaction's payload matches what is visible in the image. The image can be a document (invoice/receipt/voucher), a scale reading, a waste pile, a vehicle with cargo, or other scene related to the transaction.

USER-SUBMITTED PAYLOAD (the claim being verified). A field with value `null` is NOT being claimed — DO NOT check it; just omit it from both buckets.
- transactionDate:  {transaction_date}
- totalQuantity:    {total_quantity}    (in kg or units — the claimed material weight/quantity)
- totalPrice:       {total_price}       (TOTAL price/amount for the whole transaction, in THB. Verify against grand-total/subtotal on the document.)
- pricePerUnit:     {price_per_unit}    (PER-UNIT price — baht per kg or per piece. Verify against the rate column / unit price on the document.)
- imageType:        {expected_type}     (the user's stated category for THIS image — verify the image's visible content matches this category)

Look carefully at the image. For each NON-NULL payload field, decide if the image's visible content AGREES, CONTRADICTS, or simply DOESN'T SHOW that field.

Where to look for each field:
- transactionDate: on documents only (printed/written dates).
- totalQuantity (the claimed weight/quantity of material):
    * PRECISE source — scale's LED/dial display, document line-item total, printed sticker/label on cargo: read the number directly.
    * ROUGH ESTIMATE source — a waste pile, cargo bed, bin, or stockpile photo with NO printed number: estimate the apparent quantity from visible volume, packaging, material density, and any container size cues. Note your range in image_indicates (e.g. "approximately 50-100 kg").
- totalPrice: documents only. Look for "Total", "Grand Total", "รวมเงิน", "รวมทั้งสิ้น", "Net Amount", or the final amount-payable line. Ignore subtotals that aren't the final figure.
- pricePerUnit: documents only. Look for unit-rate columns like "ราคา/หน่วย", "Unit Price", "Rate", "@", or a "price × quantity = total" expression where the per-unit rate is the first multiplicand.
- imageType: judge whether the image's CONTENT matches the uploader's stated category. See the imageType rule below for what each category should look like.

DO NOT check invoice numbers, document numbers, reference codes, or any other identifier strings. They are intentionally OUT OF SCOPE for this verification.

Return ONLY this JSON shape (no commentary, no markdown fences):

{{
  "verdict": "passed" | "flagged",
  "issues": [
    {{
      "field": "<one of transactionDate, totalQuantity, totalPrice, pricePerUnit, imageType>",
      "payload_value": "<exact value the user submitted>",
      "image_indicates": "<what the image actually shows or your estimate>",
      "explanation": {{
        "en": "<brief reason this is a MISMATCH, in English>",
        "th": "<the same reason translated to natural Thai>"
      }}
    }}
  ],
  "matched_fields": ["<fields verified to clearly match>"]
}}

Both `explanation.en` and `explanation.th` are REQUIRED whenever an issue is reported. They must convey the same reasoning — Thai is a faithful translation of the English, not an alternative finding.

CRITICAL — per-field decision flow:
  For each NON-NULL field, make ONE decision:
    (a) MATCH       → add the field name to "matched_fields"
    (b) MISMATCH    → add an entry to "issues" describing the contradiction
    (c) CANT VERIFY → omit from BOTH lists (field not visible / not estimable)

  Skip null fields entirely — don't list them anywhere.
  A non-null field MUST appear in EXACTLY ONE of those buckets, or neither (case c).
  NEVER put a field in BOTH "matched_fields" AND "issues".

  An "issues" entry is ONLY for a genuine, substantive MISMATCH. If your
  explanation contains ANY of the following phrasings, you have NOT found
  a mismatch — the field belongs in matched_fields, NOT issues:
    "is a match" / "matches" / "this matches"
    "within tolerance" / "within the allowed" / "within ±1"
    "is consistent with" / "consistent with"
    "fits the type" / "fits the category" / "matches the stated type"
    "appears to be a [the type]"
    "missing comma" / "thousands separator" / "decimal formatting"
    "cosmetic difference" / "formatting difference"
  If your reasoning trends toward ANY of those: the answer is MATCH. Move the field
  to matched_fields and emit NO issue entry for it.

  ────────────────────────────────────────────────────────────────────────
  CRITICAL — CANT VERIFY is NOT a mismatch:
  If you cannot see the value in the image — no scale display, no document
  line, no number to read or estimate — that is CANT VERIFY, NOT a mismatch.
  CANT VERIFY means: OMIT the field from BOTH lists. Do NOT write an issue
  for it. EVER.

  Specifically, NEVER emit an issue entry where:
    - image_indicates says "Not visible" / "Not shown" / "Not displayed" /
      "Not specified" / "Cannot determine" / "No clear value" / "Unknown" /
      "N/A" / anything similar, OR
    - explanation says the value "is not visible / is not shown / cannot be
      determined / cannot be estimated / no clear indication / no specific
      total/price/weight / no precise figure" or any equivalent.
  In those cases the field is unverifiable for THIS image — OMIT it entirely.

  A genuine totalQuantity / totalPrice / pricePerUnit MISMATCH requires you
  to actually READ A DIFFERENT NUMBER on the image. If no number is readable
  for that field, the field is CANT VERIFY.

  A genuine transactionDate MISMATCH requires you to actually READ A
  DIFFERENT DATE on the image. If no date is readable, CANT VERIFY.

  A genuine imageType MISMATCH requires the image to OBVIOUSLY depict the
  wrong category. If the image plausibly fits, MATCH. If the image is too
  ambiguous to judge, OMIT (CANT VERIFY).
  ────────────────────────────────────────────────────────────────────────

Rules:
- "flagged" ONLY when the image CLEARLY and SUBSTANTIVELY contradicts the payload. Cosmetic/format differences are NEVER a mismatch. WHEN IN DOUBT, mark as MATCHED.

Numeric comparison (applies to totalQuantity, totalPrice, pricePerUnit):
- BEFORE comparing two numbers, NORMALIZE both by stripping ALL of: thousands separators (commas OR dots used as grouping), currency symbols ("฿", "$", "บาท", "THB"), unit suffixes ("kg", "kgs", "กก.", "บาท/กก."), and surrounding whitespace.
- Treat trailing ".0" / ".00" as equal to no decimals. Convert to a plain numeric value, THEN compare.
- These are ALL matches and MUST NOT be flagged:
    payload "29540"      vs image "29,540"        → MATCH (thousands separator)
    payload "29540"      vs image "29,540.00"     → MATCH (thousands separator + trailing zeros)
    payload 2040         vs image "2,040 บาท"     → MATCH (thousands separator + currency suffix)
    payload "12"         vs image "12.00"         → MATCH (decimal zeros)
    payload "1,234.56"   vs image "1234.56"       → MATCH (separator difference)
- NEVER write an issue whose explanation talks about "missing comma", "thousands separator", "decimal formatting", "should not have a comma", or any other purely cosmetic rendering difference. Format is NOT data.

transactionDate rule:
- Compare ONLY THE CALENDAR DATE (year + month + day). NEVER flag based on time-of-day, timezone, or "time not visible". IGNORE any "T17:00:00" / "T00:00" / time portion in the payload completely.

- ONLY use dates that are CLEARLY LABELED as date-related. A bare number like
  "27/9" with no surrounding date label is NOT a date — it's almost certainly
  an address, phone number, account number, page number, or ID fragment.
  Accept a date ONLY if at least one of these is true:
    (a) It is next to a date label such as: "Date", "วันที่", "ลงวันที่",
        "Issue Date", "Issued", "ออกเมื่อ", "ออกใบ", "Delivery", "ส่งของ",
        "Received", "วันที่รับสินค้า", "Due", "Signed", "Inspected", "ตรวจ",
        "Transaction Date", "วันทำรายการ".
    (b) It appears in a clearly date-shaped form: a 4-digit year alongside
        month + day (e.g. "2025-03-31", "31/03/2025", "31/03/2568", or
        Buddhist-shorthand "31/03/68" with the leading "DD/MM/" structure
        plus reasonable month/day values).
    (c) It is written out with a month name in Thai or English (e.g.
        "21 มกราคม 2568", "March 31, 2025").
  An isolated short fragment like "27/9", "12/5", or "3/68" with no label
  AND no 4-digit year is NOT acceptable as a transaction date — DO NOT use
  it. Treat the field as CANT VERIFY in that situation.

- AVOID these confusable sources (these are NEVER the transaction date):
  * Address numbers ("27/9 Soi 5", "บ้านเลขที่ 31/2")
  * Phone numbers (segments may contain "/" or "-")
  * Tax IDs, ID-card numbers, account numbers
  * Page numbers ("Page 1/3"), sequence numbers, line numbers
  * Quantities or prices that happen to use "/" as a separator

- If you cannot find a date with a clear label OR a clear 4-digit-year date
  format on the image, set image_indicates to "No clearly labeled date found"
  and OMIT the transactionDate field entirely from your response. DO NOT
  invent a date or pick a random number-with-a-slash hoping it's a date.

- BUDDHIST-ERA CONVERSION IS MANDATORY before comparing.
  Thai documents almost always print years in the Buddhist Era (พ.ศ.).
  Buddhist Era = Gregorian + 543. To convert:  Gregorian = Buddhist - 543.
  CONVERT FIRST, THEN COMPARE. NEVER compare a Buddhist year directly against
  a Gregorian year. NEVER write an explanation like "image says 2568, payload
  says 2025, mismatch" — that is WRONG because you forgot to convert.

  Conversion examples:
    image year 2568 → Gregorian 2025
    image year 2567 → Gregorian 2024
    image year 2561 → Gregorian 2018
    image year 2569 → Gregorian 2026
  2-digit Thai shorthand on documents (e.g. "26/11/68") = "26/11/2568" =
  Gregorian "26/11/2025". Always expand 2-digit years on Thai docs to "25YY"
  and then subtract 543.

  Concrete examples that MUST MATCH:
    payload "2025-11-26" + image "26/11/2568"  → MATCH (2568 = 2025)
    payload "2025-11-26" + image "26/11/68"    → MATCH (68 → 2568 → 2025)
    payload "2024-03-15" + image "15/3/67"     → MATCH (67 → 2567 → 2024)

- ALLOW ±1 day tolerance AFTER Buddhist conversion. Legacy timezone quirks
  can shift dates by exactly one day in either direction; treat any 1-day-off
  as a MATCH. These are ALL matches:
    payload "2025-10-27T17:00:00" + image "27 October 2025 16:27"     → MATCH (same date, time irrelevant)
    payload "2025-10-27T17:00:00" + image "26/10/2025"                 → MATCH (within ±1 day)
    payload "2025-10-27T17:00:00" + image "28/10/2025"                 → MATCH (within ±1 day)
    payload "2025-01-20" + image "21 มกราคม 2568"                       → MATCH (Buddhist conversion + within ±1 day)

- MULTIPLE DATES ON ONE DOCUMENT (very common): Thai invoices and receipts
  often display several dates — issue date, delivery date, due date,
  inspection date, signature date, "วันที่รับสินค้า" (received date),
  "วันที่ออกใบกำกับ" (issue date), printed-form date plus a handwritten one,
  etc. If ANY of the visible dates on the document, after Buddhist
  conversion, lands within ±1 day of the payload, that is a MATCH.
  DO NOT pick one date and flag because another date would have matched.
  Sighting any matching date anywhere on the document counts.

  When multiple dates appear, set image_indicates to a brief list of the
  dates you saw (e.g. "Issue: 29/03/2568, Delivery: 31/03/2568"), then make
  the MATCH/MISMATCH decision against the closest one to the payload.

  Examples that MUST MATCH (payload "2025-03-31"):
    image shows "Issue: 29/03/2568, Delivery: 31/03/2568"  → MATCH (delivery matches)
    image shows "Inspected 28/03/2568, Signed 01/04/2568"  → MATCH (within ±1 day of either)
    image shows "ออกใบ 28/03/68, รับ 30/03/68"               → MATCH (received date within ±1 day)

- ONLY flag transactionDate when NONE of the visible dates on the document,
  after Buddhist conversion, falls within ±1 day of the payload:
    payload "2025-10-27" + image only shows "29/10/2568"           → FLAG (2 days off, no closer date)
    payload "2025-10-27" + image only shows "27/11/2568"           → FLAG (different month)
    payload "2025-10-27" + image shows "27/10/2567" + "30/10/2567" → FLAG (2024 not 2025)

totalQuantity rule:
- From a PRECISE source (scale, printed total, single number): ±1% tolerance. Flag if off by more than 1%.
- From a ROUGH ESTIMATE (visual pile/cargo, no printed number): 0.5×–2× tolerance. ONLY flag on a CLEAR order-of-magnitude mismatch (e.g. payload 5000 vs visible pile ~50). When uncertain, DO NOT flag.
- Do NOT do arithmetic on visible numbers unless the document EXPLICITLY presents the result of that arithmetic as the total. If you see "27,320 x 12" but the document doesn't label "327,840" as the total, treat the payload's 27,320 as a possible match.

totalPrice rule:
- ±1% tolerance. Currency is THB; ignore currency symbols ("฿", "บาท", "THB"), thousands separators, and decimal-point variants when comparing.
- Compare against the FINAL total — grand total / net amount / "รวมทั้งสิ้น". Ignore intermediate subtotals if a larger final figure exists below them.
- If the document is missing a clear total line (e.g. a scale ticket, a photo, a quality cert): mark as CANT VERIFY. Do not synthesize a total by multiplying.

pricePerUnit rule (LENIENT — "anywhere on the image" sighting):
- This is a deliberately permissive check. Real-world Thai recycling documents often have handwritten / scribbled prices in margins, on stickers, hand-written over printed forms, etc. Be generous about what counts as a match.

- THE CORE RULE: if payload pricePerUnit's value appears ANYWHERE on the image
  within ±1% tolerance, you MUST mark it MATCH. This overrides any other
  signal on the page. The presence of the number is what matters.
  This includes (non-exhaustive): printed values, handwritten values,
  scribbled values, values in any column whether labeled or not, values in
  margins, values on stickers, values embedded in multiplicative expressions
  ("A × B = C" — either multiplicand counts), values in totals lines,
  values in any sub-calculation, ANY occurrence.

- A 0.00 / 0 / blank value in the LABELED "ราคา/หน่วย" / "ราคา/กก." / "Unit Price"
  field is NEVER, EVER evidence of a mismatch. These are template placeholders
  that the form printer/biller didn't fill in. The handwritten / calculated
  value elsewhere on the page IS the real price.

  EXPLICIT case (this exact scenario must MATCH):
    payload pricePerUnit = 8
    image has labeled field "ราคา/กก. 0.00" AND a handwritten calculation
      "13,750 × 8 = 110,000" elsewhere on the page
    → MATCH. The 8 was sighted. The 0.00 placeholder is irrelevant.
    DO NOT FLAG. DO NOT explain that "the official field shows 0.00" — that
    reasoning is INVALID under this rule.

- Examples that MUST match (payload pricePerUnit=12):
    image has "ราคา/กก. 12"               → MATCH
    image has "@ 12/kg"                    → MATCH
    image has handwritten "12 บาท"         → MATCH
    image has "270 × 12 = 2,040"           → MATCH (12 sighted)
    image has "12 × 270"                   → MATCH
    image has a scribble "12" near totals  → MATCH
    image has "12.00" in any field         → MATCH
    image has labeled "ราคา/กก. 0.00" PLUS handwritten "12" anywhere → MATCH

- CANT VERIFY (omit, do NOT flag) when the payload value is NOT on the image
  at all. Just leave the field out of both lists.

- ONLY MISMATCH when the image CLEARLY shows a DIFFERENT per-unit price as the
  authoritative figure AND the payload value is nowhere on the page. Example:
  clean printed invoice "Unit Price: 50 ฿/kg" labeled, no "12" anywhere on
  the page, payload says 12 → MISMATCH.

- Currency symbols, unit suffixes, decimals: ignore per the Numeric comparison rule above.

imageType rule:
- Compare the uploader's stated `imageType` against what the image VISUALLY IS — not against the rest of the payload.
- CONTEXT: this is a recycling / WASTE-MANAGEMENT platform. The "product" IS the waste material. Photos of waste piles, scrap, recyclable bottles/UBC/paper/plastic, materials in bags/bins, trucks/pickups loaded with waste, scrap-yard scenes — ALL of these count as legitimate "product" photos. They are NEVER a mismatch when the type is product_image / photo / image / waste_photo / cargo_photo / product / generic.
- Skip the check entirely (omit from both lists) when imageType is null, "other", "photo", "image", "product_image", "product", "waste_photo", "cargo_photo", or any other clearly generic value. These are too vague to verify.
- What each SPECIFIC category SHOULD look like:
    * "invoice", "tax_invoice", "receipt", "payment_voucher": a printed financial document with vendor/buyer info, line items, totals.
    * "scale_weight", "scale_reading", "product_weighing_sheet", "weighing_slip": a weighing scale's LED/dial display OR a printed weighing slip with a clear weight figure. Multi-photo / composite weighing-slip documents (a scanned slip with attached photos) still count.
    * "qc_file", "quality_cert", "quality_inspection": a quality control / inspection document, usually with product details and pass/fail. Documents that combine inspection notes with photos of the inspected material count.
    * "money_transfer_document", "bank_transfer", "payment_slip": a bank/wallet transfer confirmation.
    * "production_report": a manufacturing/production summary.
    * "national_id", "id_card", "thai_id": a Thai national ID card (front side: name in Thai+English, 13-digit ID number, date of birth, photo).
    * "vehicle_with_cargo": a vehicle (truck/pickup) carrying material.
- ONLY flag a CLEAR category mismatch where the image is OBVIOUSLY the wrong kind of thing. Examples that MUST flag:
    "national_id" but image is an invoice document → MISMATCH
    "tax_invoice" but image is a photo of trash bags with NO document visible → MISMATCH
    "money_transfer_document" but image is a scale ticket → MISMATCH
- Examples that MUST NOT flag (BE LENIENT):
    "product_image" + photo of a waste pile / scrap / UBC bottles → MATCH (waste IS the product here)
    "product_image" + a composite document with multiple waste photos → MATCH
    "scale_weight" + a weighing slip that has photos attached → MATCH (still a weighing document)
    Any generic type + any plausibly-related content → MATCH
- payload_value should be the raw imageType string; image_indicates should describe what the image actually depicts.

General:
- If a field is NOT visible / not estimable in this image: do NOT flag it AND do NOT add it to matched_fields. Just omit.
- Only check the five fields listed above (when non-null). Invoice / document numbers are explicitly OUT OF SCOPE."""


def get_openrouter_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def call_llm(
    prompt: str,
    image_urls: Optional[List[str]] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Dict[str, Any]:
    client = get_openrouter_client()

    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    if image_urls:
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    usage = {}
    if response.usage:
        usage = {
            "input_tokens": response.usage.prompt_tokens or 0,
            "output_tokens": response.usage.completion_tokens or 0,
        }

    return {
        "content": response.choices[0].message.content.strip(),
        "usage": usage,
    }


def _normalize_payload_date(date_str):
    """Apply the legacy convention: a transactionDate ending in T17:00:00 is
    UTC representing midnight in Bangkok (UTC+7), so the actual calendar
    date intended is +1 day. Returns YYYY-MM-DD.

    Examples:
      "2025-03-30T17:00:00"   → "2025-03-31"  (T17 rule applied)
      "2025-03-30T00:00:00Z"  → "2025-03-30"  (no T17, leave alone)
      "2025-03-30"            → "2025-03-30"
      None / ""               → None
    """
    if not date_str:
        return None
    import datetime as _dt
    s = str(date_str).strip()
    if len(s) < 10:
        return None
    date_part = s[:10]
    if "T17:00:00" not in s:
        return date_part
    try:
        dt = _dt.datetime.strptime(date_part, "%Y-%m-%d")
        return (dt + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return date_part


def verify_integrity_against_image(
    file_data_url: str,
    payload: Dict[str, Any],
    expected_type: Optional[str] = None,
    model: str = INTEGRITY_MODEL,
    timeout: int = EXTRACT_TIMEOUT_SECS,
) -> Dict[str, Any]:
    """Ask the vision LLM whether the image content agrees with the user's payload.

    `payload` only needs the fields the integrity check verifies — invoiceNo,
    transactionDate, totalQuantity. Missing/None values get the literal string
    "null" in the prompt so the LLM knows it's unspecified.

    transactionDate handling has TWO layers:
      1. Python normalization here applies the legacy "T17:00:00 = next day
         in Bangkok" convention before sending to the LLM.
      2. The prompt also gives the LLM a ±1 day tolerance so cases where the
         legacy convention doesn't quite fit still match.

    Returns parsed JSON: {"verdict": "passed"|"flagged",
                          "issues": [...], "matched_fields": [...]}
    Raises on HTTP error or unparseable JSON (caller decides whether to swallow).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")

    def _fmt(v):
        if v is None or v == "":
            return "null"
        return repr(v)

    prompt = INTEGRITY_PROMPT.format(
        transaction_date=_fmt(_normalize_payload_date(payload.get("transactionDate"))),
        total_quantity=_fmt(payload.get("totalQuantity")),
        total_price=_fmt(payload.get("totalPrice")),
        price_per_unit=_fmt(payload.get("pricePerUnit")),
        expected_type=_fmt(expected_type),
    )

    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": file_data_url}},
                ],
            }],
            "response_format": {"type": "json_object"},
            "temperature": DEFAULT_TEMPERATURE,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def embed_text(text: str, model: str = DEFAULT_TEXT_EMBEDDING_MODEL) -> List[float]:
    """Embed a short text into a 1536-dim vector for cosine-similarity search.

    Used by the EPR dedup pipeline to embed the LLM's `visual_description` field
    so we can find semantically-similar images even when no exact field matches.
    """
    client = get_openrouter_client()
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding


def extract_image_data(
    file_data_url: str,
    model: str = DEFAULT_MODEL,
    timeout: int = EXTRACT_TIMEOUT_SECS,
) -> Dict[str, Any]:
    """Send an image or PDF to the vision LLM and return parsed extraction JSON.

    `file_data_url` must be a base64 data URL ("data:image/jpeg;base64,..." or
    "data:application/pdf;base64,..."). Build via
    GEPPPlatform.libs.image_processing.safe_process_image().

    Raises on HTTP error or unparseable JSON so callers can decide to swallow.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")

    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": file_data_url}},
                ],
            }],
            "response_format": {"type": "json_object"},
            "temperature": DEFAULT_TEMPERATURE,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)
