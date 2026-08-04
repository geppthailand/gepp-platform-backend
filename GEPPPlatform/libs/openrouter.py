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

Where to look for each field:
- transactionDate: on documents only (printed/written dates).
- totalQuantity: PRECISE source — scale display, document line-item total, printed sticker/label: read the number directly. ROUGH ESTIMATE source — a pile, cargo bed, bin, or stockpile photo with NO printed number: estimate from visible volume, packaging, material density, container size cues. Note your range in image_indicates (e.g. "approximately 50-100 kg").
- totalPrice: documents only. "Total", "Grand Total", "รวมเงิน", "รวมทั้งสิ้น", "Net Amount", or the final amount-payable line. Ignore subtotals that aren't the final figure.
- pricePerUnit: documents only. Unit-rate columns like "ราคา/หน่วย", "Unit Price", "Rate", "@", or a "price × quantity = total" expression where the per-unit rate is the first multiplicand.
- imageType: judge whether the image's CONTENT matches the uploader's stated category. See the imageType rule below.

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

DECISION FLOW — for each NON-NULL field, exactly one of:
  (a) MATCH       → field name goes in "matched_fields"
  (b) MISMATCH    → entry in "issues"
  (c) CANT VERIFY → omit from BOTH lists
Skip null fields entirely. Never put a field in both lists.

CANT VERIFY is not a mismatch. If the value is not readable or estimable in the
image, omit the field — do not write an issue saying it "is not visible" or
"cannot be determined". A genuine MISMATCH requires you to actually read a
DIFFERENT value on the image.

Cosmetic and formatting differences are never mismatches. Neither is "within
tolerance" or "consistent with" — those are MATCH. WHEN IN DOUBT, MATCH.

Numeric comparison (totalQuantity, totalPrice, pricePerUnit):
- Normalize both sides before comparing: strip thousands separators (comma or
  dot grouping), currency symbols ("฿", "$", "บาท", "THB"), unit suffixes
  ("kg", "kgs", "กก.", "บาท/กก."), whitespace, and trailing ".0"/".00".
  Compare as plain numeric values.

transactionDate rule:
- Compare ONLY the calendar date (year + month + day). Ignore time-of-day and
  timezone entirely — including any "T17:00:00" portion in the payload.
- BUDDHIST-ERA CONVERSION IS MANDATORY: Gregorian = Buddhist − 543. Thai
  documents print พ.ศ. years (2568 = 2025). 2-digit shorthand on Thai docs
  expands to "25YY" first ("26/11/68" → 2568 → 2025). Convert BEFORE comparing.
- ALLOW ±1 day tolerance after conversion (legacy timezone quirks).
- Use only dates that are CLEARLY date-labeled ("Date", "วันที่", "ลงวันที่",
  "Issue Date", "Issued", "ออกเมื่อ", "ออกใบ", "Delivery", "ส่งของ",
  "Received", "วันที่รับสินค้า", "Due", "Signed", "Inspected", "ตรวจ",
  "Transaction Date", "วันทำรายการ"), OR date-shaped with a 4-digit year, OR
  written out with a month name in Thai or English.
  A bare fragment like "27/9" with no label and no 4-digit year is NOT a date —
  it is almost certainly an address, phone number, tax ID, account number, or
  page number. Treat the field as CANT VERIFY. Never invent a date.
- MULTIPLE DATES (very common on Thai invoices: issue, delivery, due,
  inspection, signature, printed plus handwritten): if ANY visible date lands
  within ±1 day of the payload after conversion, that is a MATCH. Do not pick
  one date and flag when another would have matched. Set image_indicates to a
  brief list of the dates you saw. Flag only when NONE falls within ±1 day.

totalQuantity rule:
- PRECISE source: ±1% tolerance.
- ROUGH ESTIMATE: 0.5×–2× tolerance. Flag only on a clear order-of-magnitude
  mismatch (payload 5000 vs a visible pile of ~50). When uncertain, do not flag.
- Do NOT do arithmetic on visible numbers unless the document explicitly
  presents the result of that arithmetic as the total.

totalPrice rule:
- ±1% tolerance. Currency is THB.
- Compare against the FINAL total — grand total / net amount / "รวมทั้งสิ้น".
  Ignore intermediate subtotals if a larger final figure appears below them.
- No clear total line (scale ticket, photo, quality cert) → CANT VERIFY. Do not
  synthesize a total by multiplying.

pricePerUnit rule (DELIBERATELY LENIENT):
- If the payload value appears ANYWHERE on the image within ±1%, mark MATCH.
  This overrides every other signal on the page. Printed, handwritten,
  scribbled in a margin, on a sticker, in a labeled or unlabeled column, inside
  a multiplicative expression (either multiplicand counts), in a totals line or
  sub-calculation — any occurrence. Real Thai recycling documents scribble
  prices anywhere; be generous about what counts.
- A 0.00 / 0 / blank value in the labeled "ราคา/หน่วย" / "ราคา/กก." / "Unit
  Price" field is NEVER evidence of a mismatch — it is an unfilled template
  placeholder. The handwritten or calculated value elsewhere IS the real price.
  (payload 8, labeled field "ราคา/กก. 0.00", handwritten "13,750 × 8 = 110,000"
  elsewhere → MATCH. Do not explain that "the official field shows 0.00" —
  that reasoning is INVALID under this rule.)
- Payload value nowhere on the image → CANT VERIFY, omit from both lists.
- MISMATCH only when the image clearly shows a DIFFERENT per-unit price as the
  authoritative figure AND the payload value appears nowhere on the page.

imageType rule:
- Compare the stated `imageType` against what the image VISUALLY IS — not
  against the rest of the payload.
- CONTEXT: this is a recycling / WASTE-MANAGEMENT platform. The "product" IS
  the waste material. Piles, scrap, UBC/bottles/paper/plastic, material in bags
  or bins, loaded trucks/pickups, scrap-yard scenes are ALL legitimate product
  photos and are NEVER a mismatch for product_image / photo / image /
  waste_photo / cargo_photo / product / generic.
- Skip the check entirely (omit from both lists) when imageType is null or
  generic ("other", "photo", "image", "product_image", "product",
  "waste_photo", "cargo_photo"). These are too vague to verify.
- What each SPECIFIC category should look like:
    * "invoice", "tax_invoice", "receipt", "payment_voucher": a printed
      financial document with vendor/buyer info, line items, totals.
    * "scale_weight", "scale_reading", "product_weighing_sheet",
      "weighing_slip": a scale's LED/dial display OR a printed weighing slip
      with a clear weight figure. Composite slips with attached photos count.
    * "qc_file", "quality_cert", "quality_inspection": a QC / inspection
      document. Ones combining inspection notes with photos of the material
      count.
    * "money_transfer_document", "bank_transfer", "payment_slip": a bank or
      wallet transfer confirmation.
    * "production_report": a manufacturing/production summary.
    * "national_id", "id_card", "thai_id": a Thai national ID card, front side.
    * "vehicle_with_cargo": a vehicle carrying material.
- Flag ONLY an obvious category mismatch where the image is clearly the wrong
  kind of thing: "national_id" but the image is an invoice; "tax_invoice" but
  the image is trash bags with no document visible; "money_transfer_document"
  but the image is a scale ticket. Anything plausibly related → MATCH.
- payload_value is the raw imageType string; image_indicates describes what the
  image actually depicts.

General:
- Field not visible / not estimable in this image → omit from both lists.
- Only check the five fields listed above (when non-null). Invoice and document
  numbers are explicitly OUT OF SCOPE."""


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
