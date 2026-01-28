"""
AI Audit V1 Custom API Function

This module provides the AI-powered waste transaction audit API endpoint.
It wraps the existing TransactionAuditService for external API consumption.

POST /call  – Receive household waste data, upsert transactions, then
              dispatch to the organisation's configured audit rule set.
"""

import json
import logging
import importlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Material mapping – only these 4 materials are allowed via /call
# ---------------------------------------------------------------------------
MATERIAL_KEY_TO_ID: Dict[str, int] = {
    "general": 94,
    "organic": 77,
    "recyclable": 298,
    "hazardous": 113,
}


# ---------------------------------------------------------------------------
# Rule-set registry (module path relative to this package)
# ---------------------------------------------------------------------------
RULE_SET_REGISTRY: Dict[str, str] = {
    "default_audit_rule_set": ".default_audit_rule_set",
    "bma_audit_rule_set": ".bma_audit_rule_set",
}


# ===================================================================
# Entry-point
# ===================================================================

def execute(
    db_session: Session,
    organization_id: int,
    method: str,
    path: str,
    query_params: Dict[str, Any],
    body: Dict[str, Any],
    headers: Dict[str, str],
    **kwargs
) -> Dict[str, Any]:
    """
    Execute AI Audit V1 API operations.

    Supported endpoints:
    - POST /call   - Receive data, upsert transactions, run audit rule set
    - GET  /test   - Return organisation info for testing
    - GET  /status - Service health
    - POST /sync   - Process pending transactions with AI audit
    - GET  /quota  - Current quota usage
    """
    path = path.strip('/') if path else ''

    logger.info(f"AI Audit V1 API called: method={method}, path={path}, org_id={organization_id}")

    if path == 'test' and method == 'GET':
        return handle_test(db_session, organization_id)

    elif path == '' or path == 'status':
        return handle_status(db_session, organization_id)

    elif path == 'call' and method == 'POST':
        return handle_call(db_session, organization_id, method, body, **kwargs)

    elif path == 'sync' and method == 'POST':
        return handle_sync_audit(db_session, organization_id, body)

    elif path == 'quota':
        return handle_quota(db_session, organization_id)

    else:
        return {
            "success": False,
            "error": "ENDPOINT_NOT_FOUND",
            "message": f"Unknown endpoint: {method} /{path}",
            "available_endpoints": [
                "GET  /test",
                "GET  /status",
                "POST /call",
                "POST /sync",
                "GET  /quota"
            ]
        }


# ===================================================================
# POST /call
# ===================================================================

def handle_call(
    db_session: Session,
    organization_id: int,
    method: str,
    body: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    Main /call handler.

    1. Record the API calling
    2. Upsert transactions from the nested payload
    3. Look up the organisation's audit rule set
    4. Dispatch to the matched rule-set function
    5. Update the calling record with results

    Expected body:
    {
      "<ext_id_1>": {
        "<district_name>": {
          "<subdistrict_name>": {
            "<household_id>": {
              "materials": {
                "general":    { "image_url": "..." },
                "organic":    { "image_url": "..." },
                "recyclable": { "image_url": "..." },
                "hazardous":  { "image_url": "..." }
              }
            }, ...
          }, ...
        }, ...
      }
    }
    """
    from GEPPPlatform.models.custom.custom_api_callings import CustomApiCalling
    from GEPPPlatform.models.subscriptions.organizations import Organization
    from GEPPPlatform.models.ai_audit_models import AiAuditRuleSet

    current_user = kwargs.get('current_user', {})
    caller_id = current_user.get('user_id')
    api_path = kwargs.get('api_path', '')
    custom_api_id = kwargs.get('custom_api_id')
    full_path = kwargs.get('full_path', '')

    # -- 1. Create calling record ------------------------------------------
    calling = CustomApiCalling(
        status='pending',
        organization_id=organization_id,
        api_path=api_path,
        custom_api_id=custom_api_id,
        full_path=full_path,
        api_method=method,
        caller_id=caller_id,
        created_transactions=[],
        updated_transactions=[],
        deleted_transactions=[],
    )
    db_session.add(calling)
    db_session.flush()  # get calling.id

    try:
        # -- 2. Upsert transactions ----------------------------------------
        created_ids, updated_ids = _upsert_transactions(
            db_session, organization_id, caller_id, body
        )

        all_txn_ids = list(set(created_ids + updated_ids))

        calling.created_transactions = created_ids
        calling.updated_transactions = updated_ids

        # -- 3. Resolve audit rule set -------------------------------------
        org = db_session.query(Organization).filter(
            Organization.id == organization_id,
            Organization.deleted_date.is_(None)
        ).first()

        if not org:
            calling.status = 'failed'
            db_session.commit()
            return {"success": False, "error": "ORGANIZATION_NOT_FOUND"}

        rule_set_id = org.ai_audit_rule_set_id or 1
        rule_set = db_session.query(AiAuditRuleSet).filter(
            AiAuditRuleSet.id == rule_set_id,
            AiAuditRuleSet.deleted_date.is_(None)
        ).first()

        function_name = rule_set.function_name if rule_set else 'default_audit_rule_set'

        # -- 4. Dispatch to rule-set function ------------------------------
        audit_result = _dispatch_rule_set(
            function_name=function_name,
            db_session=db_session,
            organization_id=organization_id,
            transaction_ids=all_txn_ids,
            body=body,
        )

        # -- 5. Finalise calling record ------------------------------------
        calling.status = 'success'
        db_session.commit()

        return {
            "success": True,
            "calling_id": calling.id,
            "rule_set": function_name,
            "transactions": {
                "created": created_ids,
                "updated": updated_ids,
            },
            "audit_result": audit_result,
        }

    except Exception as exc:
        logger.error(f"[CALL] Error: {exc}", exc_info=True)
        calling.status = 'failed'
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
        return {
            "success": False,
            "error": "CALL_FAILED",
            "message": str(exc),
            "calling_id": calling.id if calling.id else None,
        }


# ===================================================================
# Transaction upsert helpers
# ===================================================================

def _upsert_transactions(
    db_session: Session,
    organization_id: int,
    caller_id: Optional[int],
    payload: Dict[str, Any],
) -> Tuple[List[int], List[int]]:
    """
    Walk the nested payload and create / update transactions.

    Returns (created_ids, updated_ids).
    """
    from GEPPPlatform.models.transactions.transactions import Transaction, TransactionStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.cores.references import Material
    from GEPPPlatform.models.users.user_location import UserLocation

    created_ids: List[int] = []
    updated_ids: List[int] = []

    # Pre-load the 4 allowed materials to get their category_id and main_material_id
    material_meta: Dict[int, Dict[str, Any]] = {}
    for mat_key, mat_id in MATERIAL_KEY_TO_ID.items():
        mat = db_session.query(Material).filter(Material.id == mat_id).first()
        if mat:
            material_meta[mat_id] = {
                "category_id": mat.category_id,
                "main_material_id": mat.main_material_id,
            }
        else:
            logger.warning(f"[CALL] Material id={mat_id} ({mat_key}) not found in DB")

    # Cache for subdistrict name → user_location.id lookups
    _origin_cache: Dict[str, Optional[int]] = {}

    # Iterate: ext_id_1 → district → subdistrict → household_id
    for ext_id_1, districts in payload.items():
        if not isinstance(districts, dict):
            continue

        for district_name, subdistricts in districts.items():
            if not isinstance(subdistricts, dict):
                continue

            for subdistrict_name, households in subdistricts.items():
                if not isinstance(households, dict):
                    continue

                # --- Resolve origin_id from user_locations ---
                if subdistrict_name not in _origin_cache:
                    location = db_session.query(UserLocation).filter(
                        and_(
                            UserLocation.organization_id == organization_id,
                            UserLocation.name_en == subdistrict_name,
                            UserLocation.is_location == True,
                            UserLocation.deleted_date.is_(None),
                        )
                    ).first()
                    _origin_cache[subdistrict_name] = location.id if location else None
                    if not location:
                        logger.warning(
                            f"[CALL] No user_location found for name_en='{subdistrict_name}' "
                            f"in org={organization_id}"
                        )

                origin_id = _origin_cache[subdistrict_name]

                for household_id, household_data in households.items():
                    if not isinstance(household_data, dict):
                        continue

                    ext_id_2 = str(household_id)
                    materials_data = household_data.get('materials', {})

                    # --- Lookup existing transaction ---
                    existing_txn = db_session.query(Transaction).filter(
                        and_(
                            Transaction.organization_id == organization_id,
                            Transaction.ext_id_1 == str(ext_id_1),
                            Transaction.ext_id_2 == ext_id_2,
                            Transaction.deleted_date.is_(None),
                        )
                    ).first()

                    if existing_txn:
                        # UPDATE path
                        _update_transaction_records(
                            db_session, existing_txn, materials_data, material_meta, caller_id
                        )
                        existing_txn.updated_date = datetime.utcnow()
                        if caller_id:
                            existing_txn.updated_by_id = caller_id
                        if origin_id:
                            existing_txn.origin_id = origin_id
                        updated_ids.append(existing_txn.id)
                    else:
                        # CREATE path
                        txn = Transaction(
                            organization_id=organization_id,
                            ext_id_1=str(ext_id_1),
                            ext_id_2=ext_id_2,
                            status=TransactionStatus.pending,
                            transaction_method='origin',
                            origin_id=origin_id or caller_id,
                            created_by_id=caller_id,
                            notes=json.dumps({
                                "district": district_name,
                                "subdistrict": subdistrict_name,
                                "source": "ai_audit_v1/call",
                            }),
                            transaction_records=[],
                            images=[],
                        )
                        db_session.add(txn)
                        db_session.flush()  # get txn.id

                        record_ids = _create_transaction_records(
                            db_session, txn.id, materials_data, material_meta, caller_id
                        )
                        txn.transaction_records = record_ids
                        created_ids.append(txn.id)

    db_session.flush()
    return created_ids, updated_ids


def _create_transaction_records(
    db_session: Session,
    transaction_id: int,
    materials_data: Dict[str, Any],
    material_meta: Dict[int, Dict[str, Any]],
    caller_id: Optional[int],
) -> List[int]:
    """Create TransactionRecord rows for each material key present."""
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord

    record_ids: List[int] = []

    for mat_key, mat_value in materials_data.items():
        mat_id = MATERIAL_KEY_TO_ID.get(mat_key)
        if mat_id is None:
            logger.warning(f"[CALL] Unknown material key '{mat_key}', skipping")
            continue
        if not isinstance(mat_value, dict):
            continue

        meta = material_meta.get(mat_id, {})
        image_url = mat_value.get('image_url', '')
        images = [image_url] if image_url else []

        record = TransactionRecord(
            created_transaction_id=transaction_id,
            material_id=mat_id,
            main_material_id=meta.get('main_material_id', 0),
            category_id=meta.get('category_id', 0),
            transaction_type='manual_input',
            status='pending',
            unit='kg',
            origin_quantity=0,
            origin_weight_kg=0,
            origin_price_per_unit=0,
            total_amount=0,
            images=images,
            tags=[],
            created_by_id=caller_id or 0,
        )
        db_session.add(record)
        db_session.flush()
        record_ids.append(record.id)

    return record_ids


def _update_transaction_records(
    db_session: Session,
    txn,  # Transaction instance
    materials_data: Dict[str, Any],
    material_meta: Dict[int, Dict[str, Any]],
    caller_id: Optional[int],
) -> None:
    """
    For an existing transaction, sync records to match the incoming materials:
    - Materials present in payload with an active record   → update images
    - Materials present in payload with a soft-deleted record → revert delete, update images
    - Materials present in payload with no record at all   → create new record
    - Active records whose material is NOT in the payload  → soft-delete
    """
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord

    now = datetime.utcnow()

    # Load ALL records for this transaction (including soft-deleted)
    all_records = db_session.query(TransactionRecord).filter(
        TransactionRecord.created_transaction_id == txn.id,
    ).all()

    # Index by material_id, separating active vs soft-deleted
    active_by_material: Dict[int, TransactionRecord] = {}
    deleted_by_material: Dict[int, TransactionRecord] = {}
    for rec in all_records:
        if not rec.material_id:
            continue
        if rec.deleted_date is None:
            active_by_material[rec.material_id] = rec
        else:
            deleted_by_material[rec.material_id] = rec

    # Build the set of material_ids present in this payload
    incoming_material_ids: set = set()
    new_record_ids: List[int] = []

    for mat_key, mat_value in materials_data.items():
        mat_id = MATERIAL_KEY_TO_ID.get(mat_key)
        if mat_id is None:
            continue
        if not isinstance(mat_value, dict):
            continue

        incoming_material_ids.add(mat_id)
        image_url = mat_value.get('image_url', '')
        images = [image_url] if image_url else []

        if mat_id in active_by_material:
            # Case 1: active record exists → update images
            rec = active_by_material[mat_id]
            rec.images = images
            rec.updated_date = now
        elif mat_id in deleted_by_material:
            # Case 2: soft-deleted record exists → revert delete, update images
            rec = deleted_by_material[mat_id]
            rec.deleted_date = None
            rec.images = images
            rec.updated_date = now
        else:
            # Case 3: no record at all → create new
            meta = material_meta.get(mat_id, {})
            record = TransactionRecord(
                created_transaction_id=txn.id,
                material_id=mat_id,
                main_material_id=meta.get('main_material_id', 0),
                category_id=meta.get('category_id', 0),
                transaction_type='manual_input',
                status='pending',
                unit='kg',
                origin_quantity=0,
                origin_weight_kg=0,
                origin_price_per_unit=0,
                total_amount=0,
                images=images,
                tags=[],
                created_by_id=caller_id or 0,
            )
            db_session.add(record)
            db_session.flush()
            new_record_ids.append(record.id)

    # Case 4: soft-delete active records whose material is NOT in the payload
    for mat_id, rec in active_by_material.items():
        if mat_id not in incoming_material_ids:
            rec.deleted_date = now
            rec.updated_date = now

    # Rebuild transaction_records array = active record ids only
    live_ids = [
        rec.id for rec in all_records
        if rec.deleted_date is None
    ] + new_record_ids
    txn.transaction_records = live_ids


# ===================================================================
# Rule-set dispatcher
# ===================================================================

def _dispatch_rule_set(
    function_name: str,
    db_session: Session,
    organization_id: int,
    transaction_ids: List[int],
    body: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dynamically import and execute the audit rule-set module
    identified by ``function_name``.
    """
    module_rel_path = RULE_SET_REGISTRY.get(function_name)

    if module_rel_path is None:
        logger.warning(f"[CALL] function_name '{function_name}' not in registry, falling back to default")
        module_rel_path = RULE_SET_REGISTRY['default_audit_rule_set']

    try:
        module = importlib.import_module(
            module_rel_path,
            package='GEPPPlatform.services.custom.functions.ai_audit_v1'
        )
        return module.execute(
            db_session=db_session,
            organization_id=organization_id,
            transaction_ids=transaction_ids,
            body=body,
        )
    except Exception as exc:
        logger.error(f"[CALL] Failed to dispatch rule set '{function_name}': {exc}", exc_info=True)
        return {
            "success": False,
            "error": "RULE_SET_DISPATCH_FAILED",
            "function_name": function_name,
            "message": str(exc)
        }


# ===================================================================
# Existing endpoints (unchanged)
# ===================================================================

def handle_status(db_session: Session, organization_id: int) -> Dict[str, Any]:
    """Return service status and capabilities"""
    return {
        "success": True,
        "service": "ai_audit",
        "version": "v1",
        "organization_id": organization_id,
        "status": "operational",
        "capabilities": [
            "waste_classification",
            "contamination_detection",
            "quality_assessment"
        ],
        "supported_waste_types": [
            "general",
            "recyclable",
            "organic",
            "hazardous"
        ]
    }


def handle_test(db_session: Session, organization_id: int) -> Dict[str, Any]:
    """
    Test endpoint - returns organization information.
    Useful for verifying API access and authentication.
    """
    from GEPPPlatform.models.subscriptions.organizations import Organization

    org = db_session.query(Organization).filter(
        Organization.id == organization_id,
        Organization.deleted_date.is_(None)
    ).first()

    if not org:
        return {
            "success": False,
            "error": "ORGANIZATION_NOT_FOUND",
            "message": f"Organization {organization_id} not found"
        }

    return {
        "success": True,
        "message": "API connection successful",
        "organization": {
            "id": org.id,
            "name": org.name,
            "description": org.description,
            "api_path": org.api_path if hasattr(org, 'api_path') else None,
            "allow_ai_audit": org.allow_ai_audit if hasattr(org, 'allow_ai_audit') else False,
            "enable_ai_audit_api": org.enable_ai_audit_api if hasattr(org, 'enable_ai_audit_api') else False,
            "ai_audit_rule_set_id": org.ai_audit_rule_set_id if hasattr(org, 'ai_audit_rule_set_id') else None,
            "is_active": org.is_active,
            "created_date": org.created_date.isoformat() if org.created_date else None
        },
        "authenticated_at": "success",
        "api_version": "v1"
    }


def handle_sync_audit(db_session: Session, organization_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process pending transactions with AI audit.

    Request body:
    {
        "limit": int,           # Optional - max transactions to process (default: 10)
        "transaction_ids": [int] # Optional - specific transaction IDs to process
    }
    """
    from GEPPPlatform.services.cores.transaction_audit.transaction_audit_service import TransactionAuditService

    try:
        limit = body.get('limit', 10)
        transaction_ids = body.get('transaction_ids', None)

        audit_service = TransactionAuditService(
            response_language='thai',
            extraction_mode='detailed'
        )

        result = audit_service.sync_ai_audit(
            db=db_session,
            organization_id=organization_id,
            transaction_ids=transaction_ids,
            limit=limit if not transaction_ids else None
        )

        return {
            "success": True,
            "result": result
        }

    except Exception as e:
        logger.error(f"AI Audit sync error: {e}", exc_info=True)
        return {
            "success": False,
            "error": "SYNC_FAILED",
            "message": str(e)
        }


def handle_quota(db_session: Session, organization_id: int) -> Dict[str, Any]:
    """Return current API quota usage"""
    from GEPPPlatform.models.custom.custom_apis import OrganizationCustomApi, CustomApi

    org_api = db_session.query(OrganizationCustomApi).join(CustomApi).filter(
        OrganizationCustomApi.organization_id == organization_id,
        CustomApi.service_path == 'ai_audit/v1',
        OrganizationCustomApi.deleted_date.is_(None)
    ).first()

    if not org_api:
        return {
            "success": False,
            "error": "NO_API_ACCESS",
            "message": "Organization does not have AI Audit API access configured"
        }

    return {
        "success": True,
        "organization_id": organization_id,
        "quota": {
            "api_calls": {
                "used": org_api.api_call_used or 0,
                "limit": org_api.api_call_quota,
                "remaining": (org_api.api_call_quota or 0) - (org_api.api_call_used or 0) if org_api.api_call_quota else None
            },
            "process_units": {
                "used": org_api.process_used or 0,
                "limit": org_api.process_quota,
                "remaining": (org_api.process_quota or 0) - (org_api.process_used or 0) if org_api.process_quota else None
            }
        },
        "expired_date": org_api.expired_date.isoformat() if org_api.expired_date else None,
        "enabled": org_api.enable
    }
