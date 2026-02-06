"""
BMA (Bangkok Metropolitan Administration) Audit Rule Set
Handles waste audit logic specific to BMA household waste collection.

Two-step checking:
  Step 1 – Coverage check: each transaction must have general, organic, recyclable
           (hazardous is optional but audited if present).
  Step 2 – Image audit: for each material record that has an image_url,
           call Gemini 2.5 Flash Lite with LangChain using material-specific prompt.

Output format: Abbreviated JSON structure for space optimization.
Results are saved directly to transactions.ai_audit_note and audit_tokens.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional
from threading import Lock
from datetime import datetime

import yaml
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_MATERIALS = {"general", "organic", "recyclable"}
OPTIONAL_MATERIALS = {"hazardous"}
ALL_MATERIALS = REQUIRED_MATERIALS | OPTIONAL_MATERIALS

MATERIAL_ID_TO_KEY: Dict[int, str] = {
    94: "general",
    77: "organic",
    298: "recyclable",
    113: "hazardous",
}

MATERIAL_KEY_TO_ID: Dict[str, int] = {
    "general": 94,
    "organic": 77,
    "recyclable": 298,
    "hazardous": 113,
}

# Thai names for materials
MATERIAL_ID_TO_THAI: Dict[int, str] = {
    94: "ขยะทั่วไป",
    77: "ขยะอินทรีย์",
    298: "ขยะรีไซเคิล",
    113: "ขยะอันตราย",
}

# MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME = "gemini-2.5-flash-lite"

# Configurable limits
MAX_TRANSACTIONS_PER_CALL = 50  # Maximum household_ids per API call
MAX_TRANSACTION_WORKERS = 10     # Max concurrent transactions
MAX_MATERIAL_WORKERS = 4         # Max concurrent materials per transaction

# ---------------------------------------------------------------------------
# Prompt loading helpers
# ---------------------------------------------------------------------------
# From: backend/GEPPPlatform/services/custom/functions/ai_audit_v1/bma_audit_rule_set.py
# To:   backend/GEPPPlatform/prompts/ai_audit_v1/bma/extract.yaml (single unified file)
# Go up 5 levels to reach GEPPPlatform, then down to prompts
_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "ai_audit_v1" / "bma"


def _load_extract_prompt() -> str:
    """Load the unified extract.yaml prompt template."""
    path = _PROMPT_DIR / "extract.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("template", "")


def _render_prompt(claimed_type: str) -> str:
    """Render the final prompt by injecting claimed_type."""
    template = _load_extract_prompt()
    return template.format(claimed_type=claimed_type)


# ---------------------------------------------------------------------------
# LangChain + Gemini caller
# ---------------------------------------------------------------------------

def _get_langchain_gemini():
    """Initialize LangChain ChatGoogleGenerativeAI model."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        logger.error("[BMA_AUDIT] langchain-google-genai package not installed")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("[BMA_AUDIT] GEMINI_API_KEY not set")
        return None

    logger.info(f"[BMA_AUDIT] Initializing ChatGoogleGenerativeAI with model: {MODEL_NAME}")
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=0.7,
        max_output_tokens=4096,
        google_api_key=api_key,
        generation_config={
            "candidate_count": 1,
            "temperature": 0.7,
            "thinking_config": {
                "thinking_budget": 1000,
            }
        }
    )


def _call_gemini_with_langchain(
    llm,
    prompt: str,
    image_url: str,
    material_key: str
) -> Dict[str, Any]:
    """
    Call Gemini 2.5 Flash Lite with LangChain using text prompt + image.

    Returns parsed JSON dict or an error dict.
    """
    try:
        from langchain_core.messages import HumanMessage
        import requests as http_requests
        from PIL import Image
        from io import BytesIO
        import base64

        # Download and encode image
        image_data = None
        if image_url:
            try:
                resp = http_requests.get(image_url, timeout=15)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content))

                # Resize image if needed (max 600px width or height, maintain aspect ratio)
                max_dimension = 512
                width, height = img.size

                if width > max_dimension or height > max_dimension:
                    if width > height:
                        new_width = max_dimension
                        new_height = int((max_dimension / width) * height)
                    else:
                        new_height = max_dimension
                        new_width = int((max_dimension / height) * width)

                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    logger.info(f"[BMA_AUDIT] Resized image from {width}x{height} to {new_width}x{new_height}")

                # Convert to base64
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_b64 = base64.b64encode(buffered.getvalue()).decode()
                image_data = img_b64
            except Exception as img_err:
                logger.warning(f"[BMA_AUDIT] Failed to download image {image_url}: {img_err}")
                return {
                    "success": True,
                    "result": _create_error_response(material_key, "ie", "ไม่สามารถดาวน์โหลดภาพได้"),
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "thinking_tokens": 0}
                }

        # Create message with text and image
        if image_data:
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ]
            )
        else:
            message = HumanMessage(content=prompt)

        # Invoke LangChain model
        response = llm.invoke([message])
        raw_text = response.content.strip()

        # Parse JSON response
        parsed = _parse_json_response(raw_text, material_key)

        # Extract token usage if available
        usage_metadata = getattr(response, "usage_metadata", {})

        # Log usage_metadata for debugging
        logger.info(f"[BMA_AUDIT] Raw usage_metadata: {usage_metadata}")
        logger.info(f"[BMA_AUDIT] usage_metadata type: {type(usage_metadata)}")
        logger.info(f"[BMA_AUDIT] usage_metadata keys: {usage_metadata.keys() if hasattr(usage_metadata, 'keys') else 'N/A'}")

        # Try to extract thinking tokens from various possible field names
        thinking_tokens = 0
        if hasattr(usage_metadata, 'get'):
            thinking_tokens = (
                usage_metadata.get("thinking_tokens") or
                usage_metadata.get("cached_content_token_count") or
                usage_metadata.get("candidates_token_count") or
                0
            )

        usage = {
            "input_tokens": usage_metadata.get("input_tokens", 0) if hasattr(usage_metadata, 'get') else 0,
            "output_tokens": usage_metadata.get("output_tokens", 0) if hasattr(usage_metadata, 'get') else 0,
            "total_tokens": usage_metadata.get("total_tokens", 0) if hasattr(usage_metadata, 'get') else 0,
            "thinking_tokens": thinking_tokens,
        }

        return {"success": True, "result": parsed, "usage": usage}

    except Exception as exc:
        logger.error(f"[BMA_AUDIT] LangChain Gemini call failed: {exc}", exc_info=True)
        return {
            "success": False,
            "error": str(exc),
            "result": _create_error_response(material_key, "pe", f"เกิดข้อผิดพลาด: {str(exc)}"),
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "thinking_tokens": 0}
        }


def _parse_json_response(text: str, material_key: str) -> Dict[str, Any]:
    """Extract a JSON object from the model response, tolerating markdown fences."""
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)

        # Validate extraction structure
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")

        # Ensure required extraction fields exist
        required_fields = ["img_quality", "bag_state", "main_content"]
        for field in required_fields:
            if field not in parsed:
                logger.warning(f"[BMA_AUDIT] Missing field {field}, setting default")
                if field == "img_quality":
                    parsed[field] = "ok"
                elif field == "bag_state":
                    parsed[field] = "no_bag"
                elif field == "main_content":
                    parsed[field] = "general"

        return parsed

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[BMA_AUDIT] Failed to parse JSON response: {e}\nRaw text: {text}")
        return {
            "img_quality": "blur",
            "has_zero_waste_sign": False,
            "is_empty_container": False,
            "bag_state": "no_bag",
            "is_milky_bag": False,
            "haz_detected": False,
            "haz_items": [],
            "main_content": "general",
            "contamination_items": ["parse_error"],
            "contamination_pct": 0,
            "is_curry_bag": False,
            "is_heavy_liquid": False
        }


def _create_abbreviated_response(
    material_key: str,
    code: str,
    status: str,
    dt: str,
    wi: List[str],
    confidence: float = 0.95
) -> Dict[str, Any]:
    """Create standardized abbreviated response format."""
    status_map = {
        "approve": "a",
        "reject": "r",
        "pending": "p"
    }
    return {
        "ct": MATERIAL_KEY_TO_ID.get(material_key, 0),
        "as": status_map.get(status, "r"),
        "cs": round(confidence, 2),
        "rm": {
            "co": code,
            "sv": "c",
            "de": {
                "dt": dt,
                "wi": wi
            }
        }
    }


# ---------------------------------------------------------------------------
# Decision Processing Function
# ---------------------------------------------------------------------------

def process_decision(claimed_type: str, ai_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decides BMA audit result based on extracted AI features.
    Matches strict rules for General, Hazardous, Organic, and Recyclable.

    Args:
        claimed_type: "general" | "organic" | "recyclable" | "hazardous"
        ai_json: Extracted features from Gemini with structure:
            {
                "img_quality": "ok" | "artificial_ui" | "blur",
                "has_zero_waste_sign": boolean,
                "is_empty_container": boolean,
                "bag_state": "tied_opaque" | "tied_clear" | "open_visible" | "no_bag",
                "is_milky_bag": boolean,
                "haz_detected": boolean,
                "haz_items": ["item1"],
                "main_content": "general" | "general_plastic" | "organic" | "recyclable" | "hazardous",
                "contamination_items": ["item1"],
                "contamination_pct": int (0-100),
                "is_curry_bag": boolean,
                "is_heavy_liquid": boolean
            }

    Returns:
        {"code": str, "status": "approve/reject", "dt": str, "wi": list}
    """
    # --- 1. PRE-CHECKS (AI/Screen Capture/Blur) ---
    if ai_json.get("img_quality") == "artificial_ui":
        return {"code": "ai", "status": "pending", "dt": "0", "wi": []}

    if ai_json.get("img_quality") == "blur":
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ภาพเบลอ/มองไม่เห็น"]}

    # --- 1.5. EMPTY CONTAINER CHECK ---
    # ถ้าเป็นถังเปล่า/มีแต่น้ำ -> ไม่ใช่ขยะ -> Reject UI
    if ai_json.get("is_empty_container"):
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ไม่พบขยะ (ภาชนะเปล่า)"]}

    # --- 2. EXTRACT VARIABLES ---
    bag_state = ai_json.get("bag_state", "no_bag")
    is_milky = ai_json.get("is_milky_bag", False)
    haz_detected = ai_json.get("haz_detected", False)
    haz_items = ai_json.get("haz_items", [])
    main = ai_json.get("main_content", "general")
    items = ai_json.get("contamination_items", [])
    pct = ai_json.get("contamination_pct", 0)
    is_curry = ai_json.get("is_curry_bag", False)
    is_heavy_liquid = ai_json.get("is_heavy_liquid", False)

    # --- 3. SPECIAL BYPASS: HAZARDOUS SIGN ---
    # ถ้า Claim Hazardous แล้วเจอป้าย "ไม่มีขยะอันตราย" -> ให้ผ่านทันที (กฎข้อ 0.5)
    if claimed_type == "hazardous" and ai_json.get("has_zero_waste_sign"):
        return {"code": "cc", "status": "approve", "dt": "113", "wi": []}

    # --- 4. GLOBAL HAZARDOUS CHECK (ZERO TOLERANCE) ---
    # ถ้าเจอของอันตรายจริง แต่ไม่ได้ Claim ว่าเป็น Hazardous -> Reject WC 113
    if claimed_type != "hazardous" and haz_detected:
        return {"code": "wc", "status": "reject", "dt": "113", "wi": haz_items}

    # --- 5. VISIBILITY CHECKS (GLOBAL) ---
    # ถุงทึบมัดปาก = UI เสมอ (ยกเว้น General ที่อาจจะเป็นกองขยะผสม แต่กฎหลักคือ UI)
    if bag_state == "tied_opaque":
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ถุงมัดปากมองไม่เห็น"]}


    # ==================================================
    # CASE 1: GENERAL WASTE (94)
    # ==================================================
    if claimed_type == "general":
        # *** NEW RULE: MILKY BAG CHECK FOR GENERAL ***
        # ถ้าถุงมัดปาก (tied_clear) และเป็นถุงขุ่น (milky) -> UI
        # เพราะมองไม่เห็นข้างใน ไม่สามารถยืนยันได้ว่าเป็นขยะทั่วไปจริง
        if bag_state == "tied_clear" and is_milky:
            return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ถุงขุ่นมัดปาก (ตรวจสอบไม่ได้)"]}

        # Rule: Pure Recyclable (Bottle pile) -> WC 298
        if main == "recyclable" and pct < 20:
             return {"code": "wc", "status": "reject", "dt": "298", "wi": ["ขยะรีไซเคิล"]}

        # Rule: Pure Organic (Loose food) -> WC 77
        if main == "organic" and pct < 20:
             return {"code": "wc", "status": "reject", "dt": "77", "wi": ["ขยะเศษอาหาร"]}

        # *** SIMPLIFIED: General Plastic (Food containers/Straws) = General (94)
        # ไม่แยก Branch เพราะทั้ง general และ general_plastic ถือเป็นขยะทั่วไป
        # Mixed/General -> CC 94
        return {"code": "cc", "status": "approve", "dt": "94", "wi": []}


    # ==================================================
    # CASE 2: HAZARDOUS (113)
    # ==================================================
    elif claimed_type == "hazardous":
        # Rule: Visibility Check (Label Trap)
        # ถ้าถุงมัดปาก แม้จะมีป้ายบอกว่าอันตราย ก็ต้องเป็น UI (Prompt ข้อ 1)
        if bag_state in ["tied_opaque", "tied_clear"] and not haz_detected:
             return {"code": "ui", "status": "reject", "dt": "0", "wi": ["มองไม่เห็นขยะข้างใน"]}

        # Rule: False Friends (M-150/Water bottles) -> WC 298
        # ถ้าไม่เจอ Haz จริงๆ แต่เจอขวดน้ำ/ขวดแก้วเยอะๆ
        if not haz_detected and (main == "recyclable" or "ขวด" in str(items)):
             return {"code": "wc", "status": "reject", "dt": "298", "wi": ["ขยะรีไซเคิล (ขวด)"]}

        # Rule: Real Hazardous Items Visible
        if haz_detected:
             # เช็ค Contamination
             if pct > 20: return {"code": "hc", "status": "reject", "dt": "113", "wi": items}
             if pct > 0:  return {"code": "lc", "status": "approve", "dt": "113", "wi": items}
             return {"code": "cc", "status": "approve", "dt": "113", "wi": []}

        # ถ้าไม่เจออะไรเลย
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ไม่พบขยะอันตราย"]}


    # ==================================================
    # CASE 3: ORGANIC (77)
    # ==================================================
    elif claimed_type == "organic":
        # *** STRICT RULE FOR ORGANIC BAGS ***
        # อนุญาตแค่:
        # 1. ถุงเปิด/กองเปิด (open_visible)
        # 2. ถุงแกงใสใบเล็ก (is_curry=True AND NOT milky)

        # เช็คกรณีถุงมัด (Tied Clear)
        if bag_state == "tied_clear":
            # ถ้าขุ่น (Milky) -> UI ทันที (เคสถุงขาวในรูป)
            if is_milky:
                return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ถุงขุ่นมัดปาก (ตรวจสอบไม่ได้)"]}

            # ถ้าใสแต่ไม่ใช่ถุงแกง (เช่นถุงใหญ่) -> UI (เพราะ Prompt บอก Curry Only)
            if not is_curry:
                return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ถุงมัดปาก (อนุญาตเฉพาะถุงแกงใส)"]}

        # ถ้าถึงจุดนี้ แปลว่าผ่าน Bag Check แล้ว
        # tied_opaque จะถูกจัดการใน Visibility ด้านบน (artificial_ui/blur)
        # ที่นี่จะเหลือแค่: open_visible, no_bag, หรือ tied_clear ที่เป็น curry bag ใส

        # Rule: Content Logic
        # ถ้าเห็นกระดาษ/พลาสติกใส ใน organic bin -> AI จะ detect เป็น "general" -> reject
        if main == "recyclable" or main == "general" or main == "general_plastic":
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะทั่วไป"]}

        # Rule: Purity Rules
        if pct > 20: # Soft Contam > 20%
             return {"code": "wc", "status": "reject", "dt": "94", "wi": items}
        elif pct > 0: # Soft Contam < 20%
             return {"code": "lc", "status": "approve", "dt": "77", "wi": items}

        return {"code": "cc", "status": "approve", "dt": "77", "wi": []}


    # ==================================================
    # CASE 4: RECYCLABLE (298)
    # ==================================================
    elif claimed_type == "recyclable":
        # Rule: Visibility (Bulk Rule)
        # Recyclable อนุญาตถุงขุ่น/ขาว (Milky) ถ้าเห็นขวดข้างนอก (Prompt ข้อ 1)
        # ดังนั้น bag_state == 'tied_clear' (รวม milky) ให้ผ่านได้เลย ไม่ต้องเช็ค is_milky แบบ Organic

        # Rule: Definition Check (General Plastic vs Recyclable)
        if main == "general_plastic":
             # Food containers, Straws, Spoons -> WC 94
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["พลาสติกกำพร้า/กล่องอาหาร"]}

        if main == "organic":
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะเศษอาหาร"]}

        if main == "general":
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะทั่วไป"]}

        # Rule: Hard Contamination (Heavy Liquid)
        if is_heavy_liquid:
             return {"code": "hc", "status": "reject", "dt": "298", "wi": ["ขวดมีน้ำเหลือ"]}

        # Rule: Purity & Tolerance
        if pct > 50:
             return {"code": "hc", "status": "reject", "dt": "298", "wi": items}
        elif pct > 20:
             # Prompt Rule B: > 20% (Messy/Dirty) -> WC 94
             return {"code": "wc", "status": "reject", "dt": "94", "wi": items}
        elif pct > 0:
             # Prompt Rule B: < 20% -> LC 298
             return {"code": "lc", "status": "approve", "dt": "298", "wi": items}

        return {"code": "cc", "status": "approve", "dt": "298", "wi": []}

    # Fallback
    return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ระบุประเภทไม่ได้"]}


# ---------------------------------------------------------------------------
# Custom message function
# ---------------------------------------------------------------------------

def _get_custom_message(
    db_session: Session,
    organization_id: int,
    code: str,
    detect_type_id: int,
    claimed_type_id: int,
    warning_items: List[str]
) -> str:
    """
    Get custom message from ai_audit_response_patterns table.

    Checks material-specific patterns first (WHERE material_id = claimed_type_id),
    then falls back to default patterns (WHERE material_id IS NULL).

    Args:
        db_session: Database session
        organization_id: Organization ID
        code: Audit code (cc, wc, ui, hc, lc, ncm, pe, ie)
        detect_type_id: Detected material type ID
        claimed_type_id: Claimed material type ID
        warning_items: List of wrong items (Thai names)

    Returns:
        Formatted custom message string
    """
    from GEPPPlatform.models.ai_audit_models import AiAuditResponsePattern

    # Debug logging
    logger.info(f"[BMA_AUDIT] _get_custom_message called with: org_id={organization_id}, code='{code}', detect_type={detect_type_id}, claimed_type={claimed_type_id}")

    pattern = None

    # First: Try to find material-specific pattern (material_id = claimed_type_id)
    if claimed_type_id > 0:
        pattern = db_session.query(AiAuditResponsePattern).filter(
            AiAuditResponsePattern.organization_id == organization_id,
            AiAuditResponsePattern.condition == code,
            AiAuditResponsePattern.material_id == claimed_type_id,
            AiAuditResponsePattern.is_active == True,
            AiAuditResponsePattern.deleted_date.is_(None)
        ).first()

        if pattern:
            logger.info(f"[BMA_AUDIT] Material-specific pattern found: pattern_id={pattern.id}, material_id={claimed_type_id}")

    # Second: Fall back to default pattern (material_id IS NULL)
    if not pattern:
        pattern = db_session.query(AiAuditResponsePattern).filter(
            AiAuditResponsePattern.organization_id == organization_id,
            AiAuditResponsePattern.condition == code,
            AiAuditResponsePattern.material_id.is_(None),
            AiAuditResponsePattern.is_active == True,
            AiAuditResponsePattern.deleted_date.is_(None)
        ).first()

        if pattern:
            logger.info(f"[BMA_AUDIT] Default pattern found: pattern_id={pattern.id}, material_id=NULL")

    if not pattern:
        # Return default message if no pattern found
        logger.warning(f"[BMA_AUDIT] No pattern found for org_id={organization_id}, code='{code}', returning fallback")
        return f"รหัสผล: {code}"

    # Get material names
    # If ID is 0, use empty string (for transaction-level messages where material type is not applicable)
    detect_type_name = "" if detect_type_id == 0 else MATERIAL_ID_TO_THAI.get(detect_type_id, str(detect_type_id))
    claimed_type_name = "" if claimed_type_id == 0 else MATERIAL_ID_TO_THAI.get(claimed_type_id, str(claimed_type_id))
    warning_items_str = ", ".join(warning_items) if warning_items else ""

    # Replace placeholders
    message = pattern.pattern
    message = message.replace("{{code}}", code)
    message = message.replace("{{detect_type}}", detect_type_name)
    message = message.replace("{{claimed_type}}", claimed_type_name)
    message = message.replace("{{warning_items}}", warning_items_str)

    return message


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute(
    db_session: Session,
    organization_id: int,
    transaction_ids: List[int],
    body: Dict[str, Any],
    **kwargs,
) -> Dict[str, Any]:
    """
    BMA audit rule set – two-step checking with parallel processing.

    Limits: Maximum MAX_TRANSACTIONS_PER_CALL household_ids per API call.
    Note: User can have only 1 district/subdistrict/ext_id_1 per call.

    Step 1: Coverage – verify each transaction has the 3 required material
            records (general, organic, recyclable). hazardous is optional.
    Step 2: Image audit – for every material record that has an image_url,
            call Gemini with LangChain using material-specific prompt.

    Parallel Processing:
    - Transactions are processed in parallel (max MAX_TRANSACTION_WORKERS concurrent)
    - Material records within each transaction are processed in parallel (max MAX_MATERIAL_WORKERS concurrent)

    Quota Management:
    - Checks api_call_quota and process_quota before processing
    - 1 API call = 1 unit of api_call_quota
    - 1 process unit = 1 material image to be audited
    - Updates quota usage after successful processing

    Results are saved directly to transactions.ai_audit_note and audit_tokens.
    Returns simplified JSON format grouped by ext_id_1/district/subdistrict/household_id.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.custom.custom_apis import CustomApi, OrganizationCustomApi

    # Validate transaction count limit
    if len(transaction_ids) > MAX_TRANSACTIONS_PER_CALL:
        return {
            "success": False,
            "error": "TRANSACTION_LIMIT_EXCEEDED",
            "message": f"Maximum {MAX_TRANSACTIONS_PER_CALL} household_ids allowed per API call. Received: {len(transaction_ids)}",
            "limit": MAX_TRANSACTIONS_PER_CALL,
            "received": len(transaction_ids)
        }

    # ------------------------------------------------------------------
    # Check quota limits
    # ------------------------------------------------------------------
    # Get organization's custom API quota record
    org_custom_api = db_session.query(OrganizationCustomApi).join(CustomApi).filter(
        OrganizationCustomApi.organization_id == organization_id,
        CustomApi.service_path == 'ai_audit/v1',
        OrganizationCustomApi.deleted_date.is_(None)
    ).first()

    if not org_custom_api:
        logger.error(f"[BMA_AUDIT] No custom API access found for organization {organization_id}")
        return {
            "success": False,
            "error": "NO_API_ACCESS",
            "message": "Organization does not have AI Audit API access configured"
        }

    # Check API call quota
    if not org_custom_api.has_api_quota():
        logger.warning(f"[BMA_AUDIT] API call quota exceeded for org {organization_id}")
        return {
            "success": False,
            "error": "API_CALL_QUOTA_EXCEEDED",
            "message": "API call quota exceeded",
            "quota": {
                "api_call_quota": org_custom_api.api_call_quota,
                "api_call_used": org_custom_api.api_call_used,
                "remaining": (org_custom_api.api_call_quota or 0) - (org_custom_api.api_call_used or 0)
            }
        }

    # Count images in all transaction records for process quota check
    num_images = 0
    for txn_id in transaction_ids:
        records = db_session.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == txn_id,
            TransactionRecord.deleted_date.is_(None)
        ).all()
        for rec in records:
            # Count images in this record
            if rec.images and len(rec.images) > 0:
                # Each record uses its first image for audit (1 process unit per record with image)
                num_images += 1

    logger.info(f"[BMA_AUDIT] Total images to process: {num_images}")

    # Check process quota
    if not org_custom_api.has_process_quota(num_images):
        logger.warning(
            f"[BMA_AUDIT] Process quota exceeded for org {organization_id}: "
            f"used={org_custom_api.process_used}, quota={org_custom_api.process_quota}, "
            f"require_quota_for_this_call={num_images}, "
            f"remaining={(org_custom_api.process_quota or 0) - (org_custom_api.process_used or 0)}"
        )
        return {
            "success": False,
            "error": "PROCESS_QUOTA_EXCEEDED",
            "message": "Process quota exceeded",
            "process_units": {
                "used": org_custom_api.process_used or 0,
                "quota": org_custom_api.process_quota,
                "remaining": (org_custom_api.process_quota or 0) - (org_custom_api.process_used or 0),
                "require_quota_for_this_call": num_images
            }
        }

    # Note: API call quota is incremented by app.py's record_api_call() after this function returns
    # We only check quota here and update process usage at the end
    logger.info(f"[BMA_AUDIT] API call quota check passed: {org_custom_api.api_call_used}/{org_custom_api.api_call_quota}")

    logger.info(
        f"[BMA_AUDIT] Starting audit for org={organization_id}, "
        f"transaction_count={len(transaction_ids)}, "
        f"images_to_process={num_images}, "
        f"transaction_ids_sample={transaction_ids[:5]}..." if len(transaction_ids) > 5 else f"transaction_ids={transaction_ids}"
    )

    # Initialize LangChain Gemini model once
    llm = _get_langchain_gemini()

    # Thread-safe usage accumulator
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "thinking_tokens": 0}
    usage_lock = Lock()

    # Simplified response structure
    simplified_response: Dict[str, Any] = {}

    def _process_transaction(txn_id: int) -> Optional[Dict[str, Any]]:
        """Process a single transaction with parallel material audits."""
        txn = db_session.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.deleted_date.is_(None),
        ).first()

        if not txn:
            logger.warning(f"[BMA_AUDIT] Transaction {txn_id} not found in database")
            # Return error response instead of None to ensure all transaction_ids get a result
            return {
                "ext_id_1": "unknown",
                "district": "unknown",
                "subdistrict": "unknown",
                "household_id": str(txn_id),
                "status": "error",
                "message": f"Transaction {txn_id} not found",
                "materials": {}
            }

        # Load active records for this transaction
        records = db_session.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == txn_id,
            TransactionRecord.deleted_date.is_(None),
        ).all()

        # Map material_id → record
        records_by_key: Dict[str, TransactionRecord] = {}
        for rec in records:
            mat_key = MATERIAL_ID_TO_KEY.get(rec.material_id)
            if mat_key:
                records_by_key[mat_key] = rec

        # ------------------------------------------------------------------
        # Step 1: Coverage check
        # ------------------------------------------------------------------
        present_keys = set(records_by_key.keys())
        missing = REQUIRED_MATERIALS - present_keys
        has_all_required = len(missing) == 0

        # Prepare transaction-level audit note
        transaction_audit_note = {
            "type": "bma",
            "step_1": {
                "status": "pass" if has_all_required else "fail",
                "required": sorted(REQUIRED_MATERIALS),
                "present": sorted(present_keys & ALL_MATERIALS),
                "missing": sorted(missing),
            },
            "step_2": {}
        }

        # Initialize transaction tokens
        transaction_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        # Determine overall transaction status
        transaction_status = "approve"
        transaction_message = ""

        if not has_all_required:
            transaction_status = "reject"
            missing_thai = {
                "general": "ขยะทั่วไป",
                "organic": "ขยะอินทรีย์",
                "recyclable": "ขยะรีไซเคิล",
            }
            missing_items = [missing_thai.get(m, m) for m in missing]

            # Use custom message pattern for ncm (non-complete material)
            # For transaction-level message:
            # - code: "ncm"
            # - detect_type_id: 0 (empty string for {{detect_type}})
            # - claimed_type_id: 0 (empty string for {{claimed_type}})
            # - warning_items: list of missing material types in Thai
            transaction_message = _get_custom_message(
                db_session, organization_id, "ncm",
                detect_type_id=0,
                claimed_type_id=0,
                warning_items=missing_items
            )

        # ------------------------------------------------------------------
        # Step 2: Image audit per material (parallel)
        # ------------------------------------------------------------------
        materials_data: Dict[str, Any] = {}

        # Skip Step 2 entirely if Step 1 failed or LLM not available
        if not has_all_required:
            # Step 1 failed - do not run Step 2
            pass
        elif llm is None:
            # LLM not available - cannot run Step 2
            logger.warning("[BMA_AUDIT] Gemini LangChain model not available")
        else:
            # Step 1 passed - run Step 2 with parallel processing
            # Collect audit tasks for materials that have images
            audit_tasks: List[Dict[str, Any]] = []
            for mat_key in sorted(present_keys & ALL_MATERIALS):
                rec = records_by_key[mat_key]
                images = rec.images if rec.images else []
                image_url = images[0] if images else None

                if not image_url:
                    # No image provided - create abbreviated response
                    audit_result = _create_abbreviated_response(
                        mat_key, "ui", "reject", "0", ["ไม่มีรูปภาพ"]
                    )
                    transaction_audit_note["step_2"][mat_key] = audit_result

                    # Get custom message
                    custom_msg = _get_custom_message(
                        db_session, organization_id, "ui",
                        MATERIAL_KEY_TO_ID.get(mat_key, 0),
                        MATERIAL_KEY_TO_ID.get(mat_key, 0),
                        ["ไม่มีรูปภาพ"]
                    )

                    materials_data[mat_key] = {
                        "image_url": "",
                        "detect": "unknown",
                        "status": "reject",
                        "message": custom_msg
                    }

                    if transaction_status == "approve":
                        transaction_status = "reject"
                else:
                    audit_tasks.append({
                        "material": mat_key,
                        "record_id": rec.id,
                        "image_url": image_url,
                    })

            # Run Gemini calls in parallel (max MAX_MATERIAL_WORKERS concurrent)
            def _audit_one(task: Dict[str, Any]) -> Dict[str, Any]:
                prompt = _render_prompt(task["material"])
                gemini_resp = _call_gemini_with_langchain(
                    llm, prompt, task["image_url"], task["material"]
                )

                # Process decision with hierarchical logic
                if gemini_resp.get("success") and "result" in gemini_resp:
                    extraction = gemini_resp["result"]
                    decision = process_decision(task["material"], extraction)

                    # Convert decision to abbreviated format
                    audit_result = _create_abbreviated_response(
                        task["material"],
                        decision["code"],
                        decision["status"],
                        decision["dt"],
                        decision["wi"]
                    )

                    logger.info(f"[BMA_AUDIT] Decision for {task['material']}: {decision}")
                    gemini_resp["result"] = audit_result
                else:
                    # If extraction failed, create error response
                    audit_result = _create_abbreviated_response(
                        task["material"], "pe", "reject", "0", ["ไม่สามารถแปลงผลลัพธ์จาก AI ได้"]
                    )
                    gemini_resp["result"] = audit_result

                return {
                    "material": task["material"],
                    "record_id": task["record_id"],
                    "image_url": task["image_url"],
                    **gemini_resp,
                }

            if audit_tasks:
                with ThreadPoolExecutor(max_workers=min(MAX_MATERIAL_WORKERS, len(audit_tasks))) as pool:
                    futures = {pool.submit(_audit_one, t): t for t in audit_tasks}
                    for future in as_completed(futures):
                        audit_out = future.result()
                        mat_key = audit_out["material"]
                        result = audit_out.get("result", {})

                        # Save to transaction audit note
                        transaction_audit_note["step_2"][mat_key] = result

                        # Accumulate token usage (thread-safe)
                        usage = audit_out.get("usage", {})
                        for k in transaction_tokens:
                            transaction_tokens[k] += usage.get(k, 0)

                        with usage_lock:
                            for k in total_usage:
                                total_usage[k] += usage.get(k, 0)

                        # Extract data for simplified response
                        audit_status = result.get("as", "r")  # a=approve, r=reject, p=pending
                        code = result.get("rm", {}).get("co", "")
                        dt_str = result.get("rm", {}).get("de", {}).get("dt", "0")
                        # Handle dt: can be int (material_id) or "p" (pending) or "0" (error)
                        if dt_str == "p":
                            detect_type_id = 0  # pending = no specific type detected
                        elif dt_str.isdigit():
                            detect_type_id = int(dt_str)
                        else:
                            detect_type_id = 0  # default to error
                        # claimed_type comes from the material_id of the record, not from AI response
                        claimed_type_id = MATERIAL_KEY_TO_ID.get(mat_key, 0)
                        warning_items = result.get("rm", {}).get("de", {}).get("wi", [])

                        # Fix: Infer correct status from code if there's a contradiction
                        # cc (correct_category) and lc (light_contamination) should ALWAYS be approve
                        # wc (wrong_category), ui (unclear_image), hc (heavy_contamination) should ALWAYS be reject
                        # ai (artificial/screenshot) should be pending
                        expected_status_by_code = {
                            "cc": "a",  # correct_category -> approve
                            "lc": "a",  # light_contamination -> approve with warning
                            "wc": "r",  # wrong_category -> reject
                            "ui": "r",  # unclear_image -> reject
                            "hc": "r",  # heavy_contamination -> reject
                            "ncm": "r", # non_complete_material -> reject
                            "pe": "r",  # parse_error -> reject
                            "ie": "r",  # image_error -> reject
                            "ai": "p",  # artificial/screenshot -> pending
                        }

                        if code in expected_status_by_code:
                            expected_status = expected_status_by_code[code]
                            if audit_status != expected_status:
                                logger.warning(
                                    f"[BMA_AUDIT] Status mismatch for transaction {txn_id}, material {mat_key}: "
                                    f"code='{code}' expects status='{expected_status}' but got '{audit_status}'. "
                                    f"Correcting to '{expected_status}'."
                                )
                                audit_status = expected_status

                        # CRITICAL: Validate that detected type matches claimed type
                        # If AI detected a different category (and it's not unclear/error), force reject as "wc"
                        if detect_type_id != 0 and detect_type_id != claimed_type_id:
                            # Only override if AI incorrectly approved
                            if audit_status == "a" or code == "cc":
                                logger.warning(
                                    f"[BMA_AUDIT] Type mismatch for transaction {txn_id}, material {mat_key}: "
                                    f"claimed_type={claimed_type_id} but detected_type={detect_type_id}. "
                                    f"Forcing reject with code 'wc' (was status='{audit_status}', code='{code}')."
                                )
                                audit_status = "r"  # Force reject
                                code = "wc"  # Wrong category

                        # Debug: log extracted values
                        logger.info(f"[BMA_AUDIT] Extracted from Gemini result - mat_key={mat_key}, code='{code}', status={audit_status}, detect_type={detect_type_id}, claimed_type={claimed_type_id}")

                        # Get custom message
                        custom_msg = _get_custom_message(
                            db_session, organization_id, code,
                            detect_type_id, claimed_type_id, warning_items
                        )

                        # Determine detect material key
                        detect_key = MATERIAL_ID_TO_KEY.get(detect_type_id, "unknown")

                        materials_data[mat_key] = {
                            "image_url": audit_out.get("image_url", ""),
                            "detect": detect_key,
                            "status": "approve" if audit_status == "a" else "reject",
                            "message": custom_msg
                        }

                        # Update transaction status if any material is rejected
                        if audit_status == "r" and transaction_status == "approve":
                            transaction_status = "reject"

        # ------------------------------------------------------------------
        # Update transaction with audit results (do not commit here - will commit after all threads complete)
        # ------------------------------------------------------------------
        try:
            # Update transaction with audit results
            txn.ai_audit_note = transaction_audit_note
            txn.audit_tokens = transaction_tokens
            txn.ai_audit_status = AIAuditStatus.approved if transaction_status == "approve" else AIAuditStatus.rejected
            txn.ai_audit_date = datetime.utcnow()

            logger.info(f"[BMA_AUDIT] Prepared audit results for transaction {txn_id}")
        except Exception as e:
            logger.error(f"[BMA_AUDIT] Failed to prepare audit results for transaction {txn_id}: {e}", exc_info=True)

        # ------------------------------------------------------------------
        # Build simplified response
        # ------------------------------------------------------------------
        # Extract location info
        ext_id_1 = txn.ext_id_1 or "unknown"
        ext_id_2 = txn.ext_id_2 or "unknown"

        # TODO: Extract district and subdistrict from transaction
        # For now, use placeholder values
        district = "เขตยานนาวา"  # Placeholder
        subdistrict = "แขวงช่องนนทรี"  # Placeholder

        return {
            "ext_id_1": ext_id_1,
            "district": district,
            "subdistrict": subdistrict,
            "household_id": ext_id_2,
            "status": transaction_status,
            "message": transaction_message,
            "materials": materials_data
        }

    # ------------------------------------------------------------------
    # Process all transactions in parallel
    # ------------------------------------------------------------------
    results: List[Optional[Dict[str, Any]]] = []
    failed_transactions: List[int] = []

    with ThreadPoolExecutor(max_workers=min(MAX_TRANSACTION_WORKERS, len(transaction_ids))) as executor:
        futures = {executor.submit(_process_transaction, txn_id): txn_id for txn_id in transaction_ids}
        for future in as_completed(futures):
            txn_id = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                else:
                    logger.warning(f"[BMA_AUDIT] Transaction {txn_id} returned None/empty result")
                    failed_transactions.append(txn_id)
            except Exception as exc:
                logger.error(f"[BMA_AUDIT] Transaction {txn_id} failed with exception: {exc}", exc_info=True)
                failed_transactions.append(txn_id)

    # ------------------------------------------------------------------
    # Update process usage quota and commit all audit results to database
    # ------------------------------------------------------------------
    # Increment process usage by the number of images actually processed
    org_custom_api.increment_process_usage(num_images)
    logger.info(
        f"[BMA_AUDIT] Updated process quota: {org_custom_api.process_used}/{org_custom_api.process_quota} "
        f"(+{num_images} for this call)"
    )

    try:
        db_session.commit()
        logger.info(f"[BMA_AUDIT] Committed audit results for {len(results)} transactions and updated quota usage")
    except Exception as e:
        logger.error(f"[BMA_AUDIT] Failed to commit audit results: {e}", exc_info=True)
        db_session.rollback()
        return {
            "success": False,
            "error": "COMMIT_FAILED",
            "message": f"Failed to save audit results: {str(e)}",
            "organization_id": organization_id,
            "total_transactions": len(transaction_ids),
            "processed_transactions": len(results),
            "failed_transactions": len(failed_transactions)
        }

    # ------------------------------------------------------------------
    # Build simplified nested response
    # ------------------------------------------------------------------
    for result in results:
        if not result:
            continue

        ext_id_1 = result["ext_id_1"]
        district = result["district"]
        subdistrict = result["subdistrict"]
        household_id = result["household_id"]

        # Initialize nested structure
        if ext_id_1 not in simplified_response:
            simplified_response[ext_id_1] = {}
        if district not in simplified_response[ext_id_1]:
            simplified_response[ext_id_1][district] = {}
        if subdistrict not in simplified_response[ext_id_1][district]:
            simplified_response[ext_id_1][district][subdistrict] = {}

        # Add household data
        simplified_response[ext_id_1][district][subdistrict][household_id] = {
            "status": result["status"],
            "message": result["message"],
            "materials": result["materials"]
        }

    # Log summary
    logger.info(f"[BMA_AUDIT] Completed: {len(results)}/{len(transaction_ids)} transactions processed successfully")
    if failed_transactions:
        logger.warning(f"[BMA_AUDIT] Failed transactions: {failed_transactions}")

    return {
        "success": True,
        "rule_set": "bma_audit_rule_set",
        "organization_id": organization_id,
        "total_transactions": len(transaction_ids),
        "processed_transactions": len(results),
        "failed_transactions": len(failed_transactions),
        "failed_transaction_ids": failed_transactions if failed_transactions else [],
        "token_usage": total_usage,
        "results": simplified_response
    }
