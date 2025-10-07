"""
Main IoT Handlers
Main router for all IoT-related API endpoints
"""

from typing import Dict, Any
import logging

from .auth.iot_auth_handlers import IoTScaleAuthHandlers
from .iot_scale_handlers import IoTScaleHandlers

logger = logging.getLogger(__name__)

from ..exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_iot_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for all IoT-related routes
    Routes: /api/iot/*
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})
    path_params = params.get('path_params', {})
    headers = params.get('headers', {})
    
    # Get database session
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')
    
    # Initialize handlers
    auth_handler = IoTScaleAuthHandlers(db_session)
    scale_handler = IoTScaleHandlers(db_session)
    
    try:
        # IoT Authentication routes (no auth required)
        if "/api/iot/auth" in path:
            return handle_iot_auth_routes(auth_handler, path, method, data, headers, query_params)
        
        # IoT Scale management routes (require user authentication)
        elif "/api/iot/scales" in path:
            return handle_iot_scale_routes(scale_handler, path, method, data, params, query_params)
        
        # IoT Data access routes (require IoT device authentication)
        elif "/api/iot/user-info" in path or "/api/iot/location-info" in path:
            return handle_iot_data_routes(scale_handler, path, method, headers, query_params)
        
        # IoT Transaction routes (require IoT device authentication)
        elif "/api/iot/transactions" in path:
            return handle_iot_transaction_routes(scale_handler, path, method, data, headers, query_params)
        
        else:
            raise NotFoundException(f'IoT route not found: {path}')
    
    except Exception as e:
        logger.error(f"Error handling IoT route {path}: {str(e)}")
        if isinstance(e, (APIException, UnauthorizedException, NotFoundException, BadRequestException, ValidationException)):
            raise e
        raise APIException(f"Internal server error: {str(e)}")


def handle_iot_auth_routes(auth_handler, path: str, method: str, data: Dict[str, Any], headers: Dict[str, str], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IoT authentication routes"""
    
    if method == "POST":
        if path == "/api/iot/auth/login":
            return auth_handler.handle_login(data)
        elif path == "/api/iot/auth/refresh":
            return auth_handler.handle_refresh_token(data)
        elif path == "/api/iot/auth/validate":
            return auth_handler.handle_validate_token(data)
        else:
            raise NotFoundException(f"POST endpoint not found: {path}")
    
    elif method == "GET":
        if path == "/api/iot/auth/validate":
            return auth_handler.handle_validate_token_header(headers)
        else:
            raise NotFoundException(f"GET endpoint not found: {path}")
    
    else:
        raise BadRequestException(f"Method {method} not supported for IoT auth routes")


def handle_iot_scale_routes(scale_handler, path: str, method: str, data: Dict[str, Any], params: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IoT Scale management routes (require user authentication)"""
    
    # Get current user from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    
    if not current_user_id:
        raise UnauthorizedException('User authentication required for scale management')
    
    if method == "GET":
        if path == "/api/iot/scales":
            return scale_handler.handle_list_scales(current_user_id, query_params)
        
        elif "/api/iot/scales/" in path:
            # Extract scale ID from path: /api/iot/scales/{id}
            try:
                scale_id = int(path.split('/')[-1])
                return scale_handler.handle_get_scale(scale_id, current_user_id)
            except (ValueError, IndexError):
                raise BadRequestException('Invalid scale ID in path')
        
        else:
            raise NotFoundException(f"GET endpoint not found: {path}")
    
    elif method == "POST":
        if path == "/api/iot/scales":
            return scale_handler.handle_create_scale(data, current_user_id)
        else:
            raise NotFoundException(f"POST endpoint not found: {path}")
    
    elif method == "PUT":
        if "/api/iot/scales/" in path:
            try:
                scale_id = int(path.split('/')[-1])
                return scale_handler.handle_update_scale(scale_id, data, current_user_id)
            except (ValueError, IndexError):
                raise BadRequestException('Invalid scale ID in path')
        else:
            raise NotFoundException(f"PUT endpoint not found: {path}")
    
    elif method == "DELETE":
        if "/api/iot/scales/" in path:
            try:
                scale_id = int(path.split('/')[-1])
                soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
                return scale_handler.handle_delete_scale(scale_id, current_user_id, soft_delete)
            except (ValueError, IndexError):
                raise BadRequestException('Invalid scale ID in path')
        else:
            raise NotFoundException(f"DELETE endpoint not found: {path}")
    
    else:
        raise BadRequestException(f"Method {method} not supported for IoT scale routes")


def handle_iot_data_routes(scale_handler, path: str, method: str, headers: Dict[str, str], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IoT data access routes (require IoT device authentication)"""
    
    if method != "GET":
        raise BadRequestException(f"Method {method} not supported for IoT data routes")
    
    # Extract token from Authorization header
    auth_header = headers.get('Authorization') or headers.get('authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedException('Authorization header with Bearer token is required')
    
    token = auth_header.split(" ")[1]
    
    if path == "/api/iot/user-info":
        return scale_handler.handle_get_user_info(token)
    elif path == "/api/iot/location-info":
        return scale_handler.handle_get_location_info(token)
    else:
        raise NotFoundException(f"GET endpoint not found: {path}")


def handle_iot_transaction_routes(scale_handler, path: str, method: str, data: Dict[str, Any], headers: Dict[str, str], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IoT transaction routes (require IoT device authentication)"""
    
    # Extract token from Authorization header
    auth_header = headers.get('Authorization') or headers.get('authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedException('Authorization header with Bearer token is required')
    
    token = auth_header.split(" ")[1]
    
    if method == "POST":
        if path == "/api/iot/transactions":
            # TODO: Implement transaction creation from IoT device
            return {
                'success': True,
                'message': 'IoT transaction endpoint ready (implementation pending)',
                'data': {
                    'transaction_id': None,
                    'status': 'pending_implementation'
                }
            }
        else:
            raise NotFoundException(f"POST endpoint not found: {path}")
    
    elif method == "GET":
        if path == "/api/iot/transactions/recent":
            # TODO: Implement recent transactions retrieval
            return {
                'success': True,
                'message': 'IoT recent transactions endpoint ready (implementation pending)',
                'data': {
                    'transactions': [],
                    'total_count': 0
                }
            }
        else:
            raise NotFoundException(f"GET endpoint not found: {path}")
    
    else:
        raise BadRequestException(f"Method {method} not supported for IoT transaction routes")
