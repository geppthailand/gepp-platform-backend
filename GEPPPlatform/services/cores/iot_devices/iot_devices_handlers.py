"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

from typing import Dict, Any

from GEPPPlatform.services.cores.transactions.transaction_handlers import handle_create_transaction
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.users.user_service import UserService

from .iot_devices_service import IotDevicesService
from ....exceptions import APIException, UnauthorizedException, ValidationException, NotFoundException


def handle_get_locations_by_membership(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /api/locations/my-memberships - Get locations where current user is in members list (default role=dataInput)"""
    try:
        if not current_user or not current_user.get('user_id'):
            raise UnauthorizedException('Unauthorized')

        role = (query_params.get('role') or 'dataInput').strip()
        organization_id = current_user.get('organization_id') if current_user else None

        if not organization_id:
            raise NotFoundException('User is not part of any organization')

        locations = user_service.get_locations_by_member(
            member_user_id=current_user['user_id'],
            role=role,
            organization_id=organization_id
        )
        # Reduced response: only id, display_name, and materials list
        return {
            'success': True,
            'data': locations
        }

    except Exception as e:
        raise APIException(f'Error fetching member locations: {str(e)}')

# ========== MAIN ROUTE HANDLER ==========

def handle_iot_devices_routes(event: Dict[str, Any], data: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all reports-related endpoints
    """
    db_session = common_params.get('db_session')
    method = common_params.get('method', '')
    query_params = common_params.get('query_params', {})
    current_device = common_params.get('current_device', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    
    try:
        # Initialize service
        iot_devices_service = IotDevicesService(db_session)
        
        if method == '':
            raise APIException(
                f"Method is invalid",
                status_code=405,
                error_code="INVALID_METHOD"
            )

        if path == '/api/iot-devices/my-memberships':
            # Use UserService for membership-based location lookup
            user_service = UserService(db_session)
            return handle_get_locations_by_membership(user_service, query_params, current_user)
        if path == '/api/iot-devices/records':
            data = data.get('data')
            if not data:
                raise ValidationException('Data is required')
            transaction_service = TransactionService(db_session)
            current_user_id = current_user.get('user_id')
            current_user_organization_id = current_user.get('organization_id')
            return handle_create_transaction(
                transaction_service,
                data,
                current_user_id,
                current_user_organization_id
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
