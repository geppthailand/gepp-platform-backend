"""
BMA (Bangkok Metropolitan Administration) Audit Rule Set
Handles waste audit logic specific to BMA household waste collection.

Two-step checking:
  Step 1 – Coverage check: each transaction must have general, organic, recyclable
           (hazardous is optional but audited if present).
  Step 2 – Image audit: for each material record that has an image_url,
           call Gemini 2.5 Flash Lite with LangChain using material-specific prompt.

Output format: Abbreviated JSON structure for space optimization.
See: backend/GEPPPlatform/prompts/ai_audit_v1/bma/Document.md for full documentation.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional

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

MODEL_NAME = "gemini-2.5-flash-lite"

# ---------------------------------------------------------------------------
# Prompt loading helpers
# ---------------------------------------------------------------------------
# From: backend/GEPPPlatform/services/custom/functions/ai_audit_v1/bma_audit_rule_set.py
# To:   backend/GEPPPlatform/prompts/ai_audit_v1/bma/
# Go up 5 levels to reach GEPPPlatform, then down to prompts
_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "ai_audit_v1" / "bma"


def _load_output_format() -> str:
    """Load the shared output_format.yaml template text."""
    path = _PROMPT_DIR / "output_format.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("template", "")


def _load_material_prompt(material_key: str) -> str:
    """Load a material-specific prompt template string."""
    path = _PROMPT_DIR / f"{material_key}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("template", "")


def _render_prompt(material_key: str, image_url: str, output_format: str) -> str:
    """Render the final prompt by injecting claimed_type, image_url and output_format."""
    template = _load_material_prompt(material_key)
    return template.format(
        claimed_type=material_key,
        image_url=image_url,
        output_format=output_format,
    )


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

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=0.1,
        max_output_tokens=2048,
        google_api_key=api_key,
    )


def _call_gemini_with_langchain(
    llm,
    prompt: str,
    image_url: str,
    material_key: str
) -> Dict[str, Any]:
    """
    Call Gemini 2.0 Flash Exp with LangChain using text prompt + image.

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

                # Convert to base64
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_b64 = base64.b64encode(buffered.getvalue()).decode()
                image_data = img_b64
            except Exception as img_err:
                logger.warning(f"[BMA_AUDIT] Failed to download image {image_url}: {img_err}")
                return _create_error_response(material_key, "ie", "ไม่สามารถดาวน์โหลดภาพได้")

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
        usage = {
            "input_tokens": getattr(response, "usage_metadata", {}).get("input_tokens", 0),
            "output_tokens": getattr(response, "usage_metadata", {}).get("output_tokens", 0),
            "total_tokens": getattr(response, "usage_metadata", {}).get("total_tokens", 0),
        }

        return {"success": True, "result": parsed, "usage": usage}

    except Exception as exc:
        logger.error(f"[BMA_AUDIT] LangChain Gemini call failed: {exc}", exc_info=True)
        return {
            "success": False,
            "error": str(exc),
            "result": _create_error_response(material_key, "pe", f"เกิดข้อผิดพลาด: {str(exc)}")
        }


def _parse_json_response(text: str, material_key: str) -> Dict[str, Any]:
    """Extract a JSON object from the model response, tolerating markdown fences."""
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)

        # Validate abbreviated structure
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")

        # Ensure required fields exist
        required_fields = ["ct", "as", "cs", "rm"]
        for field in required_fields:
            if field not in parsed:
                raise ValueError(f"Missing required field: {field}")

        # Validate confidence score format (2 decimal places)
        if isinstance(parsed.get("cs"), float):
            parsed["cs"] = round(parsed["cs"], 2)

        return parsed

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[BMA_AUDIT] Failed to parse JSON response: {e}\nRaw text: {text}")
        return _create_error_response(material_key, "pe", "ไม่สามารถแปลงผลลัพธ์จาก AI ได้")


def _create_error_response(material_key: str, code: str, message: str) -> Dict[str, Any]:
    """Create standardized error response in abbreviated format."""
    return {
        "ct": MATERIAL_KEY_TO_ID.get(material_key, 0),
        "as": "r",
        "cs": 0.00,
        "rm": {
            "co": code,
            "sv": "c",
            "de": {
                "dt": "0",
                "wi": [message]
            }
        }
    }


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
    BMA audit rule set – two-step checking.

    Step 1: Coverage – verify each transaction has the 3 required material
            records (general, organic, recyclable). hazardous is optional.
    Step 2: Image audit – for every material record that has an image_url,
            call Gemini with LangChain using material-specific prompt.

    Returns abbreviated JSON format for space optimization.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord

    logger.info(
        f"[BMA_AUDIT] Running for org={organization_id}, "
        f"txn_count={len(transaction_ids)}"
    )

    # Load shared output format once
    output_format = _load_output_format()

    # Initialize LangChain Gemini model once
    llm = _get_langchain_gemini()

    results: List[Dict[str, Any]] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for txn_id in transaction_ids:
        txn = db_session.query(Transaction).filter(
            Transaction.id == txn_id,
            Transaction.deleted_date.is_(None),
        ).first()

        if not txn:
            results.append({
                "transaction_id": txn_id,
                "step_1": {"status": "error", "message": "Transaction not found"},
                "step_2": [],
            })
            continue

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

        step_1_result = {
            "status": "pass" if has_all_required else "fail",
            "required": sorted(REQUIRED_MATERIALS),
            "present": sorted(present_keys & ALL_MATERIALS),
            "missing": sorted(missing),
        }

        # If Step 1 fails, create non-complete material response
        if not has_all_required:
            missing_thai = {
                "general": "ขยะทั่วไป",
                "organic": "ขยะอินทรีย์",
                "recyclable": "ขยะรีไซเคิล",
                "hazardous": "ขยะอันตราย"
            }
            missing_items = [f"ไม่มี{missing_thai.get(m, m)}" for m in missing]

            step_1_result["audit"] = {
                "ct": 0,
                "as": "r",
                "cs": 0.00,
                "rm": {
                    "co": "ncm",
                    "sv": "c",
                    "de": {
                        "dt": "0",
                        "wi": missing_items
                    }
                }
            }

        # ------------------------------------------------------------------
        # Step 2: Image audit per material
        # ------------------------------------------------------------------
        step_2_results: List[Dict[str, Any]] = []

        if llm is None:
            step_2_results.append({
                "material": "all",
                "status": "skipped",
                "reason": "Gemini LangChain model not available",
            })
        elif not has_all_required:
            # Skip Step 2 if Step 1 failed
            step_2_results.append({
                "material": "all",
                "status": "skipped",
                "reason": "Step 1 failed - incomplete materials",
            })
        else:
            # Collect audit tasks for materials that have images
            audit_tasks: List[Dict[str, Any]] = []
            for mat_key in sorted(present_keys & ALL_MATERIALS):
                rec = records_by_key[mat_key]
                images = rec.images if rec.images else []
                image_url = images[0] if images else None

                if not image_url:
                    # No image provided - create error response
                    step_2_results.append({
                        "material": mat_key,
                        "record_id": rec.id,
                        "success": True,
                        "result": _create_error_response(mat_key, "ui", "ไม่มีรูปภาพ"),
                        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                    })
                    continue

                audit_tasks.append({
                    "material": mat_key,
                    "record_id": rec.id,
                    "image_url": image_url,
                })

            # Run Gemini calls in parallel (max 4 concurrent)
            def _audit_one(task: Dict[str, Any]) -> Dict[str, Any]:
                prompt = _render_prompt(task["material"], task["image_url"], output_format)
                gemini_resp = _call_gemini_with_langchain(
                    llm, prompt, task["image_url"], task["material"]
                )
                return {
                    "material": task["material"],
                    "record_id": task["record_id"],
                    **gemini_resp,
                }

            if audit_tasks:
                with ThreadPoolExecutor(max_workers=min(4, len(audit_tasks))) as pool:
                    futures = {pool.submit(_audit_one, t): t for t in audit_tasks}
                    for future in as_completed(futures):
                        audit_out = future.result()
                        step_2_results.append(audit_out)
                        # Accumulate token usage
                        usage = audit_out.get("usage", {})
                        for k in total_usage:
                            total_usage[k] += usage.get(k, 0)

        results.append({
            "transaction_id": txn_id,
            "ext_id_1": txn.ext_id_1,
            "ext_id_2": txn.ext_id_2,
            "step_1": step_1_result,
            "step_2": step_2_results,
        })

    # ------------------------------------------------------------------
    # Aggregate summary
    # ------------------------------------------------------------------
    passed_step1 = sum(1 for r in results if r.get("step_1", {}).get("status") == "pass")
    total_audited = sum(
        1 for r in results
        for s in r.get("step_2", [])
        if s.get("success") is True
    )

    return {
        "success": True,
        "rule_set": "bma_audit_rule_set",
        "organization_id": organization_id,
        "total_transactions": len(transaction_ids),
        "summary": {
            "step_1_passed": passed_step1,
            "step_1_failed": len(transaction_ids) - passed_step1,
            "step_2_materials_audited": total_audited,
        },
        "token_usage": total_usage,
        "results": results,
    }
