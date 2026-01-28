"""
BMA (Bangkok Metropolitan Administration) Audit Rule Set
Handles waste audit logic specific to BMA household waste collection.

Two-step checking:
  Step 1 – Coverage check: each transaction must have general, organic, recyclable
           (hazardous is optional but audited if present).
  Step 2 – Image audit: for each material record that has an image_url,
           call Gemini 2.5 Flash Lite with the material-specific prompt.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
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

MODEL_NAME = "gemini-2.5-flash-lite"

# ---------------------------------------------------------------------------
# Prompt loading helpers
# ---------------------------------------------------------------------------
_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "ai_audit_v1" / "bma"


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
# Gemini caller
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """Lazy-init a google-genai client."""
    try:
        from google import genai
    except ImportError:
        logger.error("[BMA_AUDIT] google-genai package not installed")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("[BMA_AUDIT] GEMINI_API_KEY not set")
        return None

    return genai.Client(api_key=api_key)


def _call_gemini(client, prompt: str, image_url: str) -> Dict[str, Any]:
    """
    Call Gemini 2.5 Flash Lite with a text prompt + one image.

    Returns parsed JSON dict or an error dict.
    """
    import requests as http_requests
    from PIL import Image

    gemini_content = [prompt]

    # Download and attach image
    if image_url:
        try:
            resp = http_requests.get(image_url, timeout=15)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content))
            gemini_content.append(img)
        except Exception as img_err:
            logger.warning(f"[BMA_AUDIT] Failed to download image {image_url}: {img_err}")
            gemini_content.append(f"[Image unavailable: {img_err}]")

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=gemini_content,
            config={
                "temperature": 0.0,
                "thinkingConfig": {"thinkingBudget": 0},
                "max_output_tokens": 2048,
            },
        )

        usage_metadata = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": getattr(usage_metadata, "prompt_token_count", 0) if usage_metadata else 0,
            "output_tokens": getattr(usage_metadata, "candidates_token_count", 0) if usage_metadata else 0,
            "total_tokens": getattr(usage_metadata, "total_token_count", 0) if usage_metadata else 0,
        }

        raw_text = response.text.strip()
        parsed = _parse_json_response(raw_text)

        return {"success": True, "result": parsed, "usage": usage}

    except Exception as exc:
        logger.error(f"[BMA_AUDIT] Gemini call failed: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}


def _parse_json_response(text: str) -> Dict[str, Any]:
    """Extract a JSON object from the model response, tolerating markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "claimed_type": "unknown",
            "audit_status": "reject",
            "confidence_score": 0.0,
            "remark": {
                "code": "parse_error",
                "severity": "critical",
                "details": {
                    "detected": "unknown",
                    "reason": "Failed to parse model response as JSON",
                    "items": "",
                },
                "correction_action": "Re-run audit",
            },
            "_raw_response": text,
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
            call Gemini with the material-specific prompt and collect results.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord

    logger.info(
        f"[BMA_AUDIT] Running for org={organization_id}, "
        f"txn_count={len(transaction_ids)}"
    )

    # Load shared output format once
    output_format = _load_output_format()

    # Initialise Gemini client once
    client = _get_gemini_client()

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

        step_1 = {
            "status": "pass" if has_all_required else "fail",
            "required": sorted(REQUIRED_MATERIALS),
            "present": sorted(present_keys & ALL_MATERIALS),
            "missing": sorted(missing),
        }

        # ------------------------------------------------------------------
        # Step 2: Image audit per material
        # ------------------------------------------------------------------
        step_2_results: List[Dict[str, Any]] = []

        if client is None:
            step_2_results.append({
                "material": "all",
                "status": "skipped",
                "reason": "Gemini client not available",
            })
        else:
            # Collect audit tasks for materials that have images
            audit_tasks: List[Dict[str, Any]] = []
            for mat_key in sorted(present_keys & ALL_MATERIALS):
                rec = records_by_key[mat_key]
                images = rec.images if rec.images else []
                image_url = images[0] if images else None

                if not image_url:
                    step_2_results.append({
                        "material": mat_key,
                        "record_id": rec.id,
                        "status": "skipped",
                        "reason": "No image_url provided",
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
                gemini_resp = _call_gemini(client, prompt, task["image_url"])
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
            "step_1": step_1,
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
