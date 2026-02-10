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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional
from threading import Lock
from datetime import datetime

import yaml
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Force logging to flush immediately (important for Lambda)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
for handler in logger.handlers:
    handler.flush = lambda: sys.stdout.flush()

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
MODEL_NAME = "gemini-2.0-flash"

# Configurable limits
MAX_TRANSACTIONS_PER_CALL = 100  # Maximum household_ids per API call
MAX_TRANSACTION_WORKERS = 25     # Max concurrent transactions
MAX_MATERIAL_WORKERS = 4         # Max concurrent materials per transaction

# ---------------------------------------------------------------------------
# Prompt loading helpers
# ---------------------------------------------------------------------------
# From: backend/GEPPPlatform/services/custom/functions/ai_audit_v1/bma_audit_rule_set.py
# To:   backend/GEPPPlatform/prompts/ai_audit_v1/bma/extract.yaml (single unified file)
# Go up 5 levels to reach GEPPPlatform, then down to prompts
_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "ai_audit_v1" / "bma"


def _load_prompt(prompt_name: str) -> str:
    """Load a prompt template by name."""
    path = _PROMPT_DIR / f"{prompt_name}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("template", "")


def _render_visibility_prompt(claimed_type: str) -> str:
    """Render visibility check prompt (Step 1)."""
    template = _load_prompt("visibility_check")
    return template.format(claimed_type=claimed_type)


def _render_classify_prompt(claimed_type: str) -> str:
    """Render classification prompt (Step 2)."""
    template = _load_prompt("classify")
    return template.format(claimed_type=claimed_type)


# ---------------------------------------------------------------------------
# LangChain + Gemini caller
# ---------------------------------------------------------------------------

def _get_langchain_gemini():
    """Initialize LangChain ChatGoogleGenerativeAI model."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        logger.error(f"[BMA_AUDIT] Required package not installed: {e}")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("[BMA_AUDIT] GEMINI_API_KEY not set")
        return None

    logger.info(f"[BMA_AUDIT] Initializing ChatGoogleGenerativeAI with model: {MODEL_NAME}")

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=api_key,
        temperature=0.7,
        max_output_tokens=4096
    )


def _create_error_response(material_key: str, code: str, reason: str) -> Dict[str, Any]:
    """Create error response in abbreviated format."""
    return _create_abbreviated_response(material_key, code, "reject", "0", [reason])


def _call_gemini_single(llm, prompt: str, image_data: str) -> Dict[str, Any]:
    """Helper: Call Gemini once with prompt + image."""
    try:
        from langchain_core.messages import HumanMessage

        # Debug: Log request details
        prompt_length = len(prompt)
        image_size = len(image_data) if image_data else 0
        logger.info(f"[BMA_AUDIT] Calling Gemini - prompt_length={prompt_length}, image_b64_length={image_size}")

        if image_data:
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                ]
            )
        else:
            message = HumanMessage(content=prompt)

        response = llm.invoke([message])
        raw_text = response.content.strip()
        usage_metadata = getattr(response, "usage_metadata", {})

        logger.info(f"[BMA_AUDIT] Gemini response received - response_length={len(raw_text)}")
        return {"raw_text": raw_text, "usage": usage_metadata}
    except Exception as exc:
        logger.error(f"[BMA_AUDIT] Gemini call failed: {exc}", exc_info=True)
        # Log more details about the error
        error_type = type(exc).__name__
        error_msg = str(exc)
        logger.error(f"[BMA_AUDIT] Error details - type={error_type}, message={error_msg}")
        raise


def _call_gemini_with_langchain(
    llm,
    claimed_type: str,
    image_url: str,
    material_key: str
) -> Dict[str, Any]:
    """
    2-STEP audit: (1) Check visibility, (2) Classify if visible.

    Returns combined result dict or error dict.
    """
    try:
        import requests as http_requests
        from PIL import Image
        from io import BytesIO
        import base64

        # Download and encode image ONCE
        image_data = None
        if image_url:
            try:
                logger.info(f"[BMA_AUDIT] Downloading image: {image_url[:100]}...")
                resp = http_requests.get(image_url, timeout=15)
                resp.raise_for_status()

                original_size = len(resp.content)
                logger.info(f"[BMA_AUDIT] Downloaded {original_size} bytes")

                img = Image.open(BytesIO(resp.content))

                # Resize image if needed
                max_dimension = 384
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
                img_bytes = buffered.getvalue()
                img_b64 = base64.b64encode(img_bytes).decode()
                image_data = img_b64

                logger.info(f"[BMA_AUDIT] Encoded image - final_bytes={len(img_bytes)}, b64_length={len(img_b64)}")
            except Exception as img_err:
                logger.error(f"[BMA_AUDIT] Failed to download/process image {image_url}: {img_err}", exc_info=True)
                return {
                    "success": True,
                    "result": _create_error_response(material_key, "ie", "ไม่สามารถดาวน์โหลดภาพได้"),
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                }

        # --- STEP 1: Visibility Check ---
        visibility_prompt = _render_visibility_prompt(claimed_type)
        logger.info(f"[BMA_AUDIT] 🔍 Step 1 - Visibility Check for material_key={material_key}, claimed_type={claimed_type}")
        logger.info(f"[BMA_AUDIT] 📸 Image URL: {image_url[:100]}...")

        step1 = _call_gemini_single(llm, visibility_prompt, image_data)

        raw_text = step1["raw_text"].strip()
        logger.info(f"[BMA_AUDIT] 📤 Step 1 raw response (first 500 chars): {raw_text[:500]}")

        # Clean markdown fences
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r"\s*```$", "", raw_text, flags=re.MULTILINE)
        raw_text = raw_text.strip()

        try:
            visibility_result = json.loads(raw_text)
            visibility_status = visibility_result.get("visibility_status", "opaque")
            reason = visibility_result.get("reason", "")
        except json.JSONDecodeError as e:
            logger.error(f"[BMA_AUDIT] ❌ Step 1 JSON parse error: {e}. Raw text: {raw_text}")
            # Fallback: treat as opaque if we can't parse
            visibility_status = "opaque"
            reason = "ไม่สามารถวิเคราะห์การมองเห็นได้"

        logger.info(f"[BMA_AUDIT] ✅ Step 1 Result - visibility_status='{visibility_status}', reason='{reason}'")

        # If not visible, return early
        if visibility_status != "visible":
            result = {
                "bag_state": "opaque",
                "img_quality": "blur" if visibility_status == "blur" else ("artificial_ui" if visibility_status == "artificial" else "ok"),
                "is_empty_container": visibility_status == "empty",
                "main_content": "general",
                "contamination_items": [reason] if reason else [],
                "contamination_pct": 0,
                "haz_detected": False,
                "is_heavy_liquid": False,
                # Debug info
                "_debug": {
                    "claimed_type": claimed_type,
                    "material_key": material_key,
                    "visibility_raw": raw_text[:200],
                    "visibility_status": visibility_status,
                    "visibility_reason": reason,
                    "step2_skipped": True,
                    "reason": "visibility_check_failed"
                }
            }

            usage1 = step1["usage"]
            total_usage = {
                "input_tokens": usage1.get("input_tokens", 0) if hasattr(usage1, 'get') else 0,
                "output_tokens": usage1.get("output_tokens", 0) if hasattr(usage1, 'get') else 0,
                "total_tokens": usage1.get("total_tokens", 0) if hasattr(usage1, 'get') else 0,
                "thinking_tokens": 0
            }

            return {"success": True, "result": result, "usage": total_usage}

        # --- STEP 2: Classification (only if visible) ---
        classify_prompt = _render_classify_prompt(claimed_type)
        logger.info(f"[BMA_AUDIT] 🔍 Step 2 - Classification for material_key={material_key}, claimed_type={claimed_type}")

        step2 = _call_gemini_single(llm, classify_prompt, image_data)

        raw_text2 = step2["raw_text"].strip()
        logger.info(f"[BMA_AUDIT] 📤 Step 2 raw response (first 500 chars): {raw_text2[:500]}")

        # Clean markdown fences
        raw_text2 = re.sub(r"^```(?:json)?\s*", "", raw_text2, flags=re.MULTILINE)
        raw_text2 = re.sub(r"\s*```$", "", raw_text2, flags=re.MULTILINE)
        raw_text2 = raw_text2.strip()

        try:
            classify_result = json.loads(raw_text2)
            logger.info(f"[BMA_AUDIT] ✅ Step 2 - Classification parsed: {classify_result}")
        except json.JSONDecodeError as e:
            logger.error(f"[BMA_AUDIT] ❌ Step 2 JSON parse error: {e}. Raw text: {raw_text2}")
            # Fallback: treat as general waste with contamination note
            classify_result = {
                "main_content": "general",
                "haz_detected": False,
                "contamination_items": ["ไม่สามารถวิเคราะห์ประเภทขยะได้"],
                "contamination_pct": 0,
                "is_heavy_liquid": False
            }

        # Combine results with debug info
        result = {
            "bag_state": "visible",
            "img_quality": "ok",
            "is_empty_container": False,
            "main_content": classify_result.get("main_content", "general"),
            "contamination_items": classify_result.get("contamination_items", []),
            "contamination_pct": classify_result.get("contamination_pct", 0),
            "haz_detected": classify_result.get("haz_detected", False),
            "is_heavy_liquid": classify_result.get("is_heavy_liquid", False),
            # Debug info
            "_debug": {
                "claimed_type": claimed_type,
                "material_key": material_key,
                "visibility_raw": raw_text[:200],
                "visibility_status": visibility_status,
                "visibility_reason": reason,
                "classify_raw": raw_text2[:200],
                "classify_parsed": classify_result
            }
        }

        # Combine usage
        usage1 = step1["usage"]
        usage2 = step2["usage"]
        total_usage = {
            "input_tokens": (usage1.get("input_tokens", 0) if hasattr(usage1, 'get') else 0) + (usage2.get("input_tokens", 0) if hasattr(usage2, 'get') else 0),
            "output_tokens": (usage1.get("output_tokens", 0) if hasattr(usage1, 'get') else 0) + (usage2.get("output_tokens", 0) if hasattr(usage2, 'get') else 0),
            "total_tokens": (usage1.get("total_tokens", 0) if hasattr(usage1, 'get') else 0) + (usage2.get("total_tokens", 0) if hasattr(usage2, 'get') else 0),
            "thinking_tokens": 0
        }

        return {"success": True, "result": result, "usage": total_usage}

    except Exception as exc:
        logger.error(f"[BMA_AUDIT] 2-step audit failed: {exc}", exc_info=True)
        return {
            "success": False,
            "error": str(exc),
            "result": _create_error_response(material_key, "pe", f"เกิดข้อผิดพลาด: {str(exc)}"),
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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
                    parsed[field] = "visible"
                elif field == "main_content":
                    parsed[field] = "general"

        return parsed

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[BMA_AUDIT] Failed to parse JSON response: {e}\nRaw text: {text}")
        return {
            "img_quality": "blur",
            "is_empty_container": False,
            "bag_state": "opaque",
            "haz_detected": False,
            "main_content": "general",
            "contamination_items": ["parse_error"],
            "contamination_pct": 0,
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
                "is_empty_container": boolean,
                "bag_state": "visible" | "opaque",
                "haz_detected": boolean,
                "main_content": "general" | "general_plastic" | "organic" | "recyclable" | "hazardous",
                "contamination_items": ["item1"],
                "contamination_pct": int (0-100),
                "is_heavy_liquid": boolean
            }

    Returns:
        {"code": str, "status": "approve/reject", "dt": str, "wi": list}
    """
    logger.info(f"[BMA_AUDIT] 🧠 process_decision called: claimed_type='{claimed_type}'")
    logger.info(f"[BMA_AUDIT] 📊 AI extraction result: {ai_json}")

    # --- 1. PRE-CHECKS (AI/Screen Capture/Blur) ---
    if ai_json.get("img_quality") == "artificial_ui":
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: artificial_ui detected → pending")
        return {"code": "ai", "status": "pending", "dt": "0", "wi": ["ภาพจากแอปพลิเคชัน/UI"]}

    if ai_json.get("img_quality") == "blur":
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: blur detected → reject")
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ภาพเบลอ/มองไม่เห็น"]}

    # --- 1.5. EMPTY CONTAINER CHECK ---
    # ถ้าเป็นถังเปล่า/มีแต่น้ำ -> ไม่ใช่ขยะ -> Reject UI
    if ai_json.get("is_empty_container"):
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: empty_container detected → reject")
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ไม่พบขยะ (ภาชนะเปล่า)"]}

    # --- 2. EXTRACT VARIABLES ---
    bag_state = ai_json.get("bag_state", "visible")
    haz_detected = ai_json.get("haz_detected", False)
    main = ai_json.get("main_content", "general")
    items = ai_json.get("contamination_items", [])
    haz_items = ai_json.get("haz_items", [])  # Add haz_items extraction
    pct = ai_json.get("contamination_pct", 0)
    is_heavy_liquid = ai_json.get("is_heavy_liquid", False)

    logger.info(f"[BMA_AUDIT] 📊 Extracted: bag_state={bag_state}, haz_detected={haz_detected}, main={main}, pct={pct}, items={items}, haz_items={haz_items}")

    # --- 3. GLOBAL HAZARDOUS CHECK (ZERO TOLERANCE) ---
    # ถ้าเจอของอันตรายจริง แต่ไม่ได้ Claim ว่าเป็น Hazardous -> Reject WC 113
    if claimed_type != "hazardous" and haz_detected:
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: hazardous detected in non-hazardous bin → reject WC 113")
        # Use haz_items instead of contamination_items for hazardous detection
        warning_items = haz_items if haz_items else ["ขยะอันตราย"]
        return {"code": "wc", "status": "reject", "dt": "113", "wi": warning_items}

    # --- 4. VISIBILITY CHECKS (GLOBAL) ---
    # ถุงทึบ/มัดปาก/มองไม่เห็น = UI เสมอ
    if bag_state == "opaque":
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: opaque bag_state → reject UI")
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["มองไม่เห็นขยะข้างใน"]}


    # ==================================================
    # CASE 1: GENERAL WASTE (94)
    # ==================================================
    if claimed_type == "general":
        logger.info(f"[BMA_AUDIT] 🗑️  CASE 1: GENERAL WASTE - main={main}, pct={pct}")

        # Rule: Pure Recyclable (Bottle pile) -> WC 298
        if main == "recyclable" and pct < 20:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Pure recyclable in general bin → reject WC 298")
             return {"code": "wc", "status": "reject", "dt": "298", "wi": ["ขยะรีไซเคิล"]}

        # Rule: Pure Organic (Loose food) -> WC 77
        if main == "organic" and pct < 20:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Pure organic in general bin → reject WC 77")
             return {"code": "wc", "status": "reject", "dt": "77", "wi": ["ขยะเศษอาหาร"]}

        # *** SIMPLIFIED: General Plastic (Food containers/Straws) = General (94)
        # ไม่แยก Branch เพราะทั้ง general และ general_plastic ถือเป็นขยะทั่วไป
        # Mixed/General -> CC 94
        logger.info(f"[BMA_AUDIT] ✅ Decision: Mixed/general waste → approve CC 94")
        return {"code": "cc", "status": "approve", "dt": "94", "wi": []}


    # ==================================================
    # CASE 2: HAZARDOUS (113)
    # ==================================================
    elif claimed_type == "hazardous":
        logger.info(f"[BMA_AUDIT] ☢️  CASE 2: HAZARDOUS WASTE - haz_detected={haz_detected}, main={main}, pct={pct}")

        # Rule: Real Hazardous Items Visible FIRST
        if haz_detected:
             logger.info(f"[BMA_AUDIT] ⚠️  Hazardous items detected! pct={pct}")
             # เช็ค Contamination
             if pct > 20:
                 logger.info(f"[BMA_AUDIT] ✅ Decision: Heavy contamination (pct={pct}) → reject HC 113")
                 return {"code": "hc", "status": "reject", "dt": "113", "wi": items}
             if pct > 0:
                 logger.info(f"[BMA_AUDIT] ✅ Decision: Light contamination (pct={pct}) → approve LC 113")
                 return {"code": "lc", "status": "approve", "dt": "113", "wi": items}
             logger.info(f"[BMA_AUDIT] ✅ Decision: Pure hazardous (pct=0) → approve CC 113")
             return {"code": "cc", "status": "approve", "dt": "113", "wi": []}

        # Rule: Wrong Category Detection
        # ถ้าไม่เจอ Haz จริงๆ (haz_detected=false) แต่เจอของประเภทอื่น
        if not haz_detected:
            # False Friends (M-150/Water bottles) -> WC 298
            if main == "recyclable" or "ขวด" in str(items):
                logger.info(f"[BMA_AUDIT] ✅ Decision: Recyclable in hazardous bin → reject WC 298")
                return {"code": "wc", "status": "reject", "dt": "298", "wi": ["ขยะรีไซเคิล (ขวด)"]}

            # General waste in hazardous bin -> WC 94
            if main == "general" or main == "general_plastic":
                logger.info(f"[BMA_AUDIT] ✅ Decision: General waste in hazardous bin → reject WC 94")
                return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะทั่วไป"]}

            # Organic waste in hazardous bin -> WC 77
            if main == "organic":
                logger.info(f"[BMA_AUDIT] ✅ Decision: Organic waste in hazardous bin → reject WC 77")
                return {"code": "wc", "status": "reject", "dt": "77", "wi": ["ขยะอินทรีย์"]}

            # ⚠️ CRITICAL FIX: AI classified as "hazardous" but haz_detected=false
            # This means AI is confused or image is unclear -> WC with unknown category
            if main == "hazardous":
                logger.info(f"[BMA_AUDIT] ✅ Decision: AI said hazardous but haz_detected=false → reject WC 94 (default to general)")
                return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ไม่พบขยะอันตราย แต่อาจเป็นขยะทั่วไป"]}

        # ถ้าไม่เจออะไรเลย (empty/unclear) - This should rarely happen now
        logger.info(f"[BMA_AUDIT] ⚠️  Decision: No identifiable waste found → reject UI")
        return {"code": "ui", "status": "reject", "dt": "0", "wi": ["ไม่พบขยะอันตราย"]}


    # ==================================================
    # CASE 3: ORGANIC (77)
    # ==================================================
    elif claimed_type == "organic":
        logger.info(f"[BMA_AUDIT] 🍃 CASE 3: ORGANIC WASTE - main={main}, pct={pct}")

        # Rule: Content Logic
        # ถ้าเห็นกระดาษ/พลาสติกใส ใน organic bin -> AI จะ detect เป็น "general" -> reject
        if main == "recyclable" or main == "general" or main == "general_plastic":
             logger.info(f"[BMA_AUDIT] ✅ Decision: Wrong content type in organic bin → reject WC 94")
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะทั่วไป"]}

        # Rule: Purity Rules
        if pct > 20: # Soft Contam > 20%
             logger.info(f"[BMA_AUDIT] ✅ Decision: High contamination (pct={pct}) → reject WC 94")
             return {"code": "wc", "status": "reject", "dt": "94", "wi": items}
        elif pct > 0: # Soft Contam < 20%
             logger.info(f"[BMA_AUDIT] ✅ Decision: Light contamination (pct={pct}) → approve LC 77")
             return {"code": "lc", "status": "approve", "dt": "77", "wi": items}

        logger.info(f"[BMA_AUDIT] ✅ Decision: Pure organic (pct=0) → approve CC 77")
        return {"code": "cc", "status": "approve", "dt": "77", "wi": []}


    # ==================================================
    # CASE 4: RECYCLABLE (298)
    # ==================================================
    elif claimed_type == "recyclable":
        logger.info(f"[BMA_AUDIT] ♻️  CASE 4: RECYCLABLE WASTE - main={main}, pct={pct}, is_heavy_liquid={is_heavy_liquid}")

        # Rule: Definition Check (General Plastic vs Recyclable)
        if main == "general_plastic":
             logger.info(f"[BMA_AUDIT] ✅ Decision: General plastic in recyclable bin → reject WC 94")
             # Food containers, Straws, Spoons -> WC 94
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["พลาสติกกำพร้า/กล่องอาหาร"]}

        if main == "organic":
             logger.info(f"[BMA_AUDIT] ✅ Decision: Organic in recyclable bin → reject WC 94")
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะเศษอาหาร"]}

        if main == "general":
             logger.info(f"[BMA_AUDIT] ✅ Decision: General in recyclable bin → reject WC 94")
             return {"code": "wc", "status": "reject", "dt": "94", "wi": ["ขยะทั่วไป"]}

        # Rule: Hard Contamination (Heavy Liquid)
        if is_heavy_liquid:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Heavy liquid detected → reject HC 298")
             return {"code": "hc", "status": "reject", "dt": "298", "wi": ["ขวดมีน้ำเหลือ"]}

        # Rule: Purity & Tolerance
        if pct > 50:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Very high contamination (pct={pct}) → reject HC 298")
             return {"code": "hc", "status": "reject", "dt": "298", "wi": items}
        elif pct > 20:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Moderate contamination (pct={pct}) → reject WC 94")
             # Prompt Rule B: > 20% (Messy/Dirty) -> WC 94
             return {"code": "wc", "status": "reject", "dt": "94", "wi": items}
        elif pct > 0:
             logger.info(f"[BMA_AUDIT] ✅ Decision: Light contamination (pct={pct}) → approve LC 298")
             # Prompt Rule B: < 20% -> LC 298
             return {"code": "lc", "status": "approve", "dt": "298", "wi": items}

        logger.info(f"[BMA_AUDIT] ✅ Decision: Pure recyclable (pct=0) → approve CC 298")
        return {"code": "cc", "status": "approve", "dt": "298", "wi": []}

    # Fallback
    logger.warning(f"[BMA_AUDIT] ⚠️  FALLBACK: Unknown claimed_type='{claimed_type}' → reject UI")
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

    # Log entry point
    logger.info(f"[BMA_AUDIT] ========================================")
    logger.info(f"[BMA_AUDIT] 🔵 Execute function called")
    logger.info(f"[BMA_AUDIT] Organization ID: {organization_id}")
    logger.info(f"[BMA_AUDIT] Transaction IDs count: {len(transaction_ids)}")
    logger.info(f"[BMA_AUDIT] Transaction IDs: {transaction_ids[:20]}{'...' if len(transaction_ids) > 20 else ''}")
    logger.info(f"[BMA_AUDIT] Body keys: {list(body.keys()) if body else 'None'}")
    logger.info(f"[BMA_AUDIT] ========================================")

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
        f"[BMA_AUDIT] ========================================\n"
        f"[BMA_AUDIT] 🚀 Starting Batch Audit\n"
        f"[BMA_AUDIT] Organization: {organization_id}\n"
        f"[BMA_AUDIT] Transactions: {len(transaction_ids)}\n"
        f"[BMA_AUDIT] Images to process: {num_images}\n"
        f"[BMA_AUDIT] Quota: {org_custom_api.process_used}/{org_custom_api.process_quota}\n"
        f"[BMA_AUDIT] Transaction IDs: {transaction_ids[:10]}{'...' if len(transaction_ids) > 10 else ''}\n"
        f"[BMA_AUDIT] ========================================"
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
        logger.info(f"[BMA_AUDIT] 🏠 Processing transaction_id={txn_id}")

        txn = db_session.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.deleted_date.is_(None),
        ).first()

        if not txn:
            logger.warning(f"[BMA_AUDIT] ❌ Transaction {txn_id} not found in database")
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

        logger.info(f"[BMA_AUDIT] 📋 Transaction found: ext_id_1={txn.ext_id_1}, ext_id_2={txn.ext_id_2}")

        # Load active records for this transaction
        records = db_session.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == txn_id,
            TransactionRecord.deleted_date.is_(None),
        ).all()

        logger.info(f"[BMA_AUDIT] 📦 Found {len(records)} material records for transaction {txn_id}")

        # Map material_id → record
        records_by_key: Dict[str, TransactionRecord] = {}
        for rec in records:
            mat_key = MATERIAL_ID_TO_KEY.get(rec.material_id)
            if mat_key:
                records_by_key[mat_key] = rec
                images_count = len(rec.images) if rec.images else 0
                logger.info(f"[BMA_AUDIT]   - {mat_key} (material_id={rec.material_id}): {images_count} images")

        # ------------------------------------------------------------------
        # Step 1: Coverage check
        # ------------------------------------------------------------------
        present_keys = set(records_by_key.keys())
        missing = REQUIRED_MATERIALS - present_keys
        has_all_required = len(missing) == 0

        # Prepare transaction-level audit note
        transaction_audit_note = {
            "type": "bma",
            "transaction_id": txn_id,
            "ext_id_1": txn.ext_id_1,
            "ext_id_2": txn.ext_id_2,
            "household_id": txn.ext_id_2,  # For easy lookup
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
                try:
                    logger.info(f"[BMA_AUDIT] Starting audit for transaction={txn_id}, material={task['material']}, image_url={task['image_url'][:100]}...")

                    # 2-step audit: visibility check → classification
                    gemini_resp = _call_gemini_with_langchain(
                        llm, task["material"], task["image_url"], task["material"]
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

                        # Add debug info to audit result
                        audit_result["_debug"] = extraction.get("_debug", {})
                        audit_result["_debug"]["decision"] = decision

                        logger.info(f"[BMA_AUDIT] ✅ Success - txn={txn_id}, material={task['material']}, decision={decision}")
                        gemini_resp["result"] = audit_result
                    else:
                        # If extraction failed, create error response
                        logger.error(f"[BMA_AUDIT] ❌ Extraction failed - txn={txn_id}, material={task['material']}, resp={gemini_resp}")
                        audit_result = _create_abbreviated_response(
                            task["material"], "pe", "reject", "0", ["ไม่สามารถแปลงผลลัพธ์จาก AI ได้"]
                        )
                        gemini_resp["result"] = audit_result
                except Exception as audit_exc:
                    logger.error(f"[BMA_AUDIT] ❌ Audit exception - txn={txn_id}, material={task['material']}: {audit_exc}", exc_info=True)
                    # Return error response
                    gemini_resp = {
                        "success": False,
                        "error": str(audit_exc),
                        "result": _create_abbreviated_response(
                            task["material"], "pe", "reject", "0", [f"เกิดข้อผิดพลาด: {str(audit_exc)[:50]}"]
                        ),
                        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                    }

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

                        # Map status: a -> approve, r -> reject, p -> pending
                        status_map = {
                            "a": "approve",
                            "r": "reject",
                            "p": "pending"
                        }
                        material_status = status_map.get(audit_status, "reject")

                        materials_data[mat_key] = {
                            "image_url": audit_out.get("image_url", ""),
                            "detect": detect_key,
                            "status": material_status,
                            "message": custom_msg
                        }

                        # Update transaction status if any material is rejected or pending
                        if audit_status == "r" and transaction_status == "approve":
                            transaction_status = "reject"
                        elif audit_status == "p" and transaction_status == "approve":
                            transaction_status = "pending"

        # ------------------------------------------------------------------
        # Update transaction with audit results (do not commit here - will commit after all threads complete)
        # ------------------------------------------------------------------
        try:
            # Update transaction with audit results
            txn.ai_audit_note = transaction_audit_note
            txn.audit_tokens = transaction_tokens

            # Map transaction status to AIAuditStatus enum
            if transaction_status == "approve":
                txn.ai_audit_status = AIAuditStatus.approved
            elif transaction_status == "pending":
                txn.ai_audit_status = AIAuditStatus.no_action  # Use no_action for pending cases
            else:  # reject
                txn.ai_audit_status = AIAuditStatus.rejected

            txn.ai_audit_date = datetime.utcnow()

            logger.info(f"[BMA_AUDIT] Prepared audit results for transaction {txn_id} with status {transaction_status}")
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

        logger.info(f"[BMA_AUDIT] 🏁 Transaction {txn_id} completed:")
        logger.info(f"[BMA_AUDIT]   - ext_id_1={ext_id_1}, household_id={ext_id_2}")
        logger.info(f"[BMA_AUDIT]   - status={transaction_status}, message={transaction_message}")
        logger.info(f"[BMA_AUDIT]   - materials={list(materials_data.keys())}")
        for mat_key, mat_data in materials_data.items():
            logger.info(f"[BMA_AUDIT]     • {mat_key}: detect={mat_data['detect']}, status={mat_data['status']}")

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
    logger.info(
        f"[BMA_AUDIT] ========================================\n"
        f"[BMA_AUDIT] ✅ Batch Audit Completed\n"
        f"[BMA_AUDIT] Processed: {len(results)}/{len(transaction_ids)} transactions\n"
        f"[BMA_AUDIT] Failed: {len(failed_transactions)} transactions\n"
        f"[BMA_AUDIT] Token usage: input={total_usage['input_tokens']}, output={total_usage['output_tokens']}, total={total_usage['total_tokens']}\n"
        f"[BMA_AUDIT] {'⚠️  Failed IDs: ' + str(failed_transactions) if failed_transactions else '✓ All transactions successful'}\n"
        f"[BMA_AUDIT] ========================================"
    )

    sys.stdout.flush()  # Force flush all logs before returning
    return {
        "success": True,
        "rule_set": "bma_audit_rule_set",
        "organization_id": organization_id,
        "total_transactions": len(transaction_ids),
        "processed_transactions": len(results),
        "failed_transactions": len(failed_transactions),
        "failed_transaction_ids": failed_transactions if failed_transactions else [],
        # "token_usage": total_usage,
        "results": simplified_response
    }
