"""
AI Audit V1 Custom API Function

This module provides the AI-powered waste transaction audit API endpoint.
It wraps the existing TransactionAuditService for external API consumption.
"""

import json
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
    - POST /analyze - Run AI audit on transaction images
    - GET /status - Check audit service status
    - GET /quota - Get current quota usage
    
    Args:
        db_session: Database session
        organization_id: The organization making the request
        method: HTTP method
        path: Remaining path after service_path (e.g., '/analyze', '/status')
        query_params: URL query parameters
        body: Request body
        headers: Request headers
        
    Returns:
        API response dict
    """
    # Normalize path
    path = path.strip('/') if path else ''
    
    logger.info(f"AI Audit V1 API called: method={method}, path={path}, org_id={organization_id}")
    
    if path == 'test' and method == 'GET':
        # GET /test - Return organization info for testing
        return handle_test(db_session, organization_id)
    
    elif path == '' or path == 'status':
        # GET /status - Return service status
        return handle_status(db_session, organization_id)
    
    elif path == 'analyze' and method == 'POST':
        # POST /analyze - Run AI audit
        return handle_analyze(db_session, organization_id, body)
    
    elif path == 'sync' and method == 'POST':
        # POST /sync - Sync AI audit (process pending transactions)
        return handle_sync_audit(db_session, organization_id, body)
    
    elif path == 'quota':
        # GET /quota - Get quota information
        return handle_quota(db_session, organization_id)
    
    else:
        return {
            "success": False,
            "error": "ENDPOINT_NOT_FOUND",
            "message": f"Unknown endpoint: {method} /{path}",
            "available_endpoints": [
                "GET /test",
                "GET /status",
                "POST /analyze",
                "POST /sync",
                "GET /quota"
            ]
        }


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
    
    # Get organization data
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



def handle_analyze(db_session: Session, organization_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze transaction images using AI audit.
    
    Request body:
    {
        "transaction_id": int,  # Required - transaction to audit
        "images": [str],        # Optional - specific image URLs to analyze
        "options": {
            "detailed": bool,   # Return detailed analysis
            "language": str     # Response language (thai/english)
        }
    }
    """
    from GEPPPlatform.services.cores.transaction_audit.transaction_audit_service import TransactionAuditService
    from GEPPPlatform.models.transactions.transactions import Transaction
    
    transaction_id = body.get('transaction_id')
    if not transaction_id:
        return {
            "success": False,
            "error": "MISSING_TRANSACTION_ID",
            "message": "transaction_id is required"
        }
    
    # Verify transaction belongs to organization
    transaction = db_session.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.deleted_date.is_(None)
    ).first()
    
    if not transaction:
        return {
            "success": False,
            "error": "TRANSACTION_NOT_FOUND",
            "message": f"Transaction {transaction_id} not found"
        }
    
    # Get organization_id from transaction's user_location
    if transaction.user_location and hasattr(transaction.user_location, 'organization_id'):
        tx_org_id = transaction.user_location.organization_id
        if tx_org_id != organization_id:
            return {
                "success": False,
                "error": "ACCESS_DENIED",
                "message": "Transaction does not belong to this organization"
            }
    
    try:
        # Initialize audit service
        options = body.get('options', {})
        language = options.get('language', 'thai')
        detailed = options.get('detailed', True)
        
        audit_service = TransactionAuditService(
            response_language=language,
            extraction_mode='detailed' if detailed else 'simple'
        )
        
        # Run sync AI audit for this specific transaction
        result = audit_service.sync_ai_audit(
            db=db_session,
            organization_id=organization_id,
            transaction_ids=[transaction_id]
        )
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "audit_result": result
        }
        
    except Exception as e:
        logger.error(f"AI Audit analyze error: {e}", exc_info=True)
        return {
            "success": False,
            "error": "AUDIT_FAILED",
            "message": str(e)
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
        
        # Run sync AI audit
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
    
    # Get quota info for this organization's AI Audit API
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
