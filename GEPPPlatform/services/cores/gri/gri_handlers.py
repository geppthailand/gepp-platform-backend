"""
GRI API Handlers
"""

from typing import Dict, Any, List
import logging
import json

from .gri_service import GriService
from ....exceptions import (
    APIException,
    BadRequestException
)

logger = logging.getLogger(__name__)

def handle_gri_routes(event: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for GRI routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})
    path_params = params.get('path_params', {})
    
    # Safely get body, ensuring it's not None
    body_raw = event.get("body")

    try:
        body_data = json.loads(body_raw) if body_raw else {}
    except Exception:
        raise BadRequestException("Invalid JSON body")
        
    if body_data is None:
        body_data = {}

    # Get database session
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    gri_service = GriService(db_session)

    # Extract user info
    current_user = params.get('current_user', {})
    organization_id = current_user.get('organization_id')
    user_id = current_user.get('user_id')

    if not organization_id:
        raise BadRequestException("Organization ID is required")

    # Simple routing
    
    # GET /api/gri/306-1
    if method == 'GET' and '/api/gri/306-1' in path:
         record_year = query_params.get('year')
         result = gri_service.get_gri306_1_records(organization_id, record_year)
         return {"data": result}
         
    # POST /api/gri/306-1
    if method == 'POST' and '/api/gri/306-1' in path:
        if not user_id:
            raise BadRequestException("User ID is required for creation")
            
        global_year = body_data.get('year', '')
        records_to_process = body_data.get('records', [])
        delete_records = body_data.get('deleted_ids', []) # Get IDs to delete
            
        if not isinstance(records_to_process, list):
             raise BadRequestException("Records must be an array")
             
        result = gri_service.create_gri306_1_records(
            organization_id, 
            user_id, 
            records_to_process,
            delete_records, # Pass to service
            str(global_year) if global_year else None
        )
        return {"data": result, "message": "Records processed successfully"}

    # GET /api/gri/306-2
    if method == 'GET' and '/api/gri/306-2' in path:
        record_year = query_params.get('year')
        result = gri_service.get_gri306_2_records(organization_id, record_year)
        return {"data": result}
        
    # POST /api/gri/306-2
    if method == 'POST' and '/api/gri/306-2' in path:
        if not user_id:
            raise BadRequestException("User ID is required for creation")
            
        global_year = body_data.get('year', '')
        records_to_process = body_data.get('records', [])
        delete_records = body_data.get('deleted_ids', [])
        
        if not isinstance(records_to_process, list):
             raise BadRequestException("Records must be an array")
             
        result = gri_service.create_gri306_2_records(
            organization_id,
            user_id,
            records_to_process,
            delete_records,
            str(global_year) if global_year else None
        )
        return {"data": result, "message": "GRI 306-2 Records processed successfully"}

    # GET /api/gri/306-3
    if method == 'GET' and '/api/gri/306-3' in path:
        record_year = query_params.get('year')
        result = gri_service.get_gri306_3_records(organization_id, record_year)
        return {"data": result}

    # POST /api/gri/306-3
    if method == 'POST' and '/api/gri/306-3' in path:
        if not user_id:
            raise BadRequestException("User ID is required for creation")
            
        global_year = body_data.get('year', '')
        records_to_process = body_data.get('records', [])
        delete_records = body_data.get('deleted_ids', [])
        
        if not isinstance(records_to_process, list):
             raise BadRequestException("Records must be an array")
             
        result = gri_service.create_gri306_3_records(
            organization_id,
            user_id,
            records_to_process,
            delete_records,
            str(global_year) if global_year else None
        )
        return {"data": result, "message": "GRI 306-3 Records processed successfully"}

    raise APIException(f"Route not found: {method} {path}", 404)
