"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .locations_service import LocationsService
from ....exceptions import APIException, ValidationException, NotFoundException
from GEPPPlatform.models.cores.references import MainMaterial, MaterialCategory
from GEPPPlatform.models.users.user_location import UserLocation


def _validate_organization_id(current_user: Dict[str, Any]) -> int:
    """Validate and extract organization_id from current_user"""
    organization_id = current_user.get('organization_id')
    if not organization_id:
        raise ValidationException("Organization ID is required")
    return organization_id

def handle_get_locations(locations_service: LocationsService, organization_id: int) -> Dict[str, Any]:
    """Handle GET /api/locations - Get all locations"""
    return locations_service.get_locations(organization_id)


# ========== MAIN ROUTE HANDLER ==========

def handle_locations_routes(event: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all locations-related endpoints
    
    Routes:
    - GET /api/locations - Get all locations
    """
    
    db_session = common_params.get('db_session')
    method = common_params.get('method', 'GET')
    query_params = common_params.get('query_params', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    
    try:
        # Initialize service
        locations_service = LocationsService(db_session)
        # Validate organization ID for all routes
        organization_id = _validate_organization_id(current_user)
        
        # Route to appropriate handler
        if path == '/api/locations':
            return handle_get_locations(locations_service, organization_id)

        # elif path == '/api/reports/performance':
        #     filters = _build_filters_from_query_params(query_params)
        #     return _handle_performance_report(reports_service, organization_id, filters)
    
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
