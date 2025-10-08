"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .reports_service import ReportsService
from ....exceptions import APIException, ValidationException, NotFoundException


def handle_reports_routes(event: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all reports-related endpoints
    
    Routes:
    - GET /api/reports - Get transaction records for the organization
    """
    
    db_session = common_params.get('db_session')
    method = common_params.get('method', 'GET')
    query_params = common_params.get('query_params', {})
    path_params = common_params.get('path_params', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    
    try:
        # Initialize service
        reports_service = ReportsService(db_session)
        
        # Only handle GET requests for now
        if method == 'GET':
            if path == '/api/reports/overview':
                # Get organization_id from current user
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                # Build filters from query params
                filters = {}
                if query_params.get('material_id'):
                    filters['material_id'] = int(query_params['material_id'])
                if query_params.get('origin_id'):
                    filters['origin_id'] = int(query_params['origin_id'])
                if query_params.get('date_from'):
                    filters['date_from'] = query_params['date_from']
                if query_params.get('date_to'):
                    filters['date_to'] = query_params['date_to']   
                
                # Get transaction records using service
                result = reports_service.get_transaction_records_by_organization(
                    organization_id=organization_id,
                    filters=filters if filters else None,
                    report_type='overview'
                )
                
                return result
            
            elif path == '/api/reports/origins':
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                result = reports_service.get_origin_by_organization(
                    organization_id=organization_id
                )
                
                return result
            
            elif path == '/api/reports/materials':
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                result = reports_service.get_material_by_organization(
                    organization_id=organization_id
                )
                
                return result
            else:
                raise APIException(
                    "Report endpoint not found",
                    status_code=404,
                    error_code="REPORT_NOT_FOUND"
                )
        
        else:
            raise APIException(
                f"Method {method} not supported yet. Only GET requests are available.",
                status_code=405,
                error_code="METHOD_NOT_ALLOWED"
            )
    
    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )

