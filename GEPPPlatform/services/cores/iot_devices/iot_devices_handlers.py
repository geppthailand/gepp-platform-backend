"""
IoT Devices HTTP handlers
Handles all /api/iot-devices/* routes
"""

from typing import Dict, Any
from sqlalchemy.orm import joinedload

from GEPPPlatform.services.cores.transactions.transaction_handlers import handle_create_transaction
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.users.user_service import UserService
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.cores.references import Material
from GEPPPlatform.models.cores.iot_devices import IoTDevice

from ....exceptions import APIException, UnauthorizedException, ValidationException, NotFoundException


def handle_get_locations_by_membership(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any], db_session) -> Dict[str, Any]:
    """Handle POST /api/iot-devices/my-memberships - Get locations where current user is in members list (default role=dataInput)"""
    try:
        if not current_user or not current_user.get('user_id'):
            raise UnauthorizedException('Unauthorized')

        role = (query_params.get('role') or 'data_input').strip()
        organization_id = current_user.get('organization_id') if current_user else None

        if not organization_id:
            raise NotFoundException('User is not part of any organization')

        locations = user_service.get_locations_by_member(
            member_user_id=current_user['user_id'],
            role=role,
            organization_id=organization_id
        )
        
        # Get ALL materials (active and not deleted, no organization filtering)
        # Use eager loading to fetch category and main_material relationships
        all_materials = db_session.query(Material).options(
            joinedload(Material.category),
            joinedload(Material.main_material)
        ).filter(
            Material.is_active == True,
            Material.deleted_date.is_(None)
        ).all()
        
        # Format materials in the same structure as location materials
        materials_list = []
        for material in all_materials:
            material_obj = {
                'material_id': material.id,
                'name_en': material.name_en,
                'name_th': material.name_th,
                'category_id': material.category_id,
                'main_material_id': material.main_material_id,
                'unit_name_th': material.unit_name_th,
                'unit_name_en': material.unit_name_en,
                'unit_weight': float(material.unit_weight) if material.unit_weight is not None else None,
            }
            
            # Add category as object
            if material.category:
                material_obj['category'] = {
                    'id': material.category.id,
                    'name_en': material.category.name_en,
                    'name_th': material.category.name_th,
                    'code': material.category.code,
                }
            else:
                material_obj['category'] = None
            
            # Add main_material as object
            if material.main_material:
                material_obj['main_material'] = {
                    'id': material.main_material.id,
                    'name_en': material.main_material.name_en,
                    'name_th': material.main_material.name_th,
                    'name_local': material.main_material.name_local,
                    'code': material.main_material.code,
                }
            else:
                material_obj['main_material'] = None
            
            materials_list.append(material_obj)
        
        # Remove materials from each location (keep only origin_id and display_name)
        locations_list = []
        for location in locations:
            locations_list.append({
                'origin_id': location.get('origin_id'),
                'display_name': location.get('display_name')
            })
        
        return {
            'success': True,
            'data': {
                'locations': locations_list,
                'materials': materials_list
            }
        }

    except Exception as e:
        raise APIException(f'Error fetching member locations: {str(e)}')

# ========== MAIN ROUTE HANDLER ==========

def handle_iot_devices_routes(event: Dict[str, Any], data: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all IoT devices-related endpoints
    """
    db_session = common_params.get('db_session')
    method = common_params.get('method', '')
    query_params = common_params.get('query_params', {})
    current_device = common_params.get('current_device', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    if not current_device or not current_device.get('device_id'):
        raise UnauthorizedException('Unauthorized device')
    
    # Check organization match between device and user (if user is present)
    if current_user and current_user.get('user_id'):
        device_id = current_device.get('device_id')
        device = db_session.query(IoTDevice).filter_by(
            id=device_id,
            is_active=True
        ).first()
        
        if not device:
            raise NotFoundException('Device not found')
        
        user_organization_id = current_user.get('organization_id')
        device_organization_id = device.organization_id
        
        # Only check if both have organization IDs set
        if user_organization_id is not None and device_organization_id is not None:
            if user_organization_id != device_organization_id:
                raise UnauthorizedException('User organization does not match device organization')
    
    try:
        if method == '':
            raise APIException(
                f"Method is invalid",
                status_code=405,
                error_code="INVALID_METHOD"
            )

        if path == '/api/iot-devices/my-memberships':
            # Use UserService for membership-based location lookup
            user_service = UserService(db_session)
            return handle_get_locations_by_membership(user_service, query_params, current_user, db_session)
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
        if path == '/api/iot-devices/qr-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login_iot_user(data, **common_params)
        if path == '/api/iot-devices/manual-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login(data, **common_params)
        if path == '/api/iot-devices/user-id-login':
            auth_handler = AuthHandlers(db_session)
            # Use user_id from body to login, return as normal manual login
            user_id = data.get('user_id')
            
            if not user_id:
                raise ValidationException('user_id is required')
            
            # Get user by user_id
            user = db_session.query(UserLocation).filter_by(
                id=user_id,
                is_active=True
            ).first()
            
            if not user:
                raise UnauthorizedException('Invalid user_id')
            
            # Generate JWT auth and refresh tokens
            tokens = auth_handler.generate_jwt_tokens(user.id, user.organization_id, user.email)
            
            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 60 minutes in seconds
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'displayName': user.display_name,
                    'organizationId': user.organization_id
                }
            }
        # Unknown route under /api/iot-devices
        raise NotFoundException('Endpoint not found')

    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except UnauthorizedException as e:
        raise APIException(str(e), status_code=401, error_code="UNAUTHORIZED")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )
