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

MODEL_NAME = "gemini-2.5-flash-lite"

# Configurable limits
MAX_TRANSACTIONS_PER_CALL = 1000  # Maximum household_ids per API call
MAX_TRANSACTION_WORKERS = 10     # Max concurrent transactions
MAX_MATERIAL_WORKERS = 4         # Max concurrent materials per transaction

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
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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

    # Query for pattern matching this code
    pattern = db_session.query(AiAuditResponsePattern).filter(
        AiAuditResponsePattern.organization_id == organization_id,
        AiAuditResponsePattern.condition == code,
        AiAuditResponsePattern.is_active == True,
        AiAuditResponsePattern.deleted_date.is_(None)
    ).first()

    logger.info(f"[BMA_AUDIT] Pattern found: {pattern is not None}, pattern_id={pattern.id if pattern else 'None'}, pattern_text={pattern.pattern[:50] if pattern else 'None'}...")

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

    Results are saved directly to transactions.ai_audit_note and audit_tokens.
    Returns simplified JSON format grouped by ext_id_1/district/subdistrict/household_id.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord

    # Validate transaction count limit
    if len(transaction_ids) > MAX_TRANSACTIONS_PER_CALL:
        return {
            "success": False,
            "error": "TRANSACTION_LIMIT_EXCEEDED",
            "message": f"Maximum {MAX_TRANSACTIONS_PER_CALL} household_ids allowed per API call. Received: {len(transaction_ids)}",
            "limit": MAX_TRANSACTIONS_PER_CALL,
            "received": len(transaction_ids)
        }

    logger.info(
        f"[BMA_AUDIT] Starting audit for org={organization_id}, "
        f"transaction_count={len(transaction_ids)}, "
        f"transaction_ids_sample={transaction_ids[:5]}..." if len(transaction_ids) > 5 else f"transaction_ids={transaction_ids}"
    )

    # Load shared output format once
    output_format = _load_output_format()

    # Initialize LangChain Gemini model once
    llm = _get_langchain_gemini()

    # Thread-safe usage accumulator
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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
                    # No image provided - create error response
                    audit_result = _create_error_response(mat_key, "ui", "ไม่มีรูปภาพ")
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
                prompt = _render_prompt(task["material"], task["image_url"], output_format)
                gemini_resp = _call_gemini_with_langchain(
                    llm, prompt, task["image_url"], task["material"]
                )
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
                        audit_status = result.get("as", "r")  # a=approve, r=reject
                        code = result.get("rm", {}).get("co", "")
                        detect_type_id = int(result.get("rm", {}).get("de", {}).get("dt", "0"))
                        claimed_type_id = result.get("ct", 0)
                        warning_items = result.get("rm", {}).get("de", {}).get("wi", [])

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
    # Commit all audit results to database
    # ------------------------------------------------------------------
    try:
        db_session.commit()
        logger.info(f"[BMA_AUDIT] Committed audit results for {len(results)} transactions")
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
