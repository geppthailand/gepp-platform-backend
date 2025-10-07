"""
IoT Scale Authentication Handlers
Handles HTTP requests for IoT Scale authentication
"""

from typing import Dict, Any
import logging

from .iot_auth_service import IoTScaleAuthService
from ..dto.iot_requests import IoTLoginRequest
from ..dto.iot_responses import IoTLoginResponse, IoTScaleInfo

logger = logging.getLogger(__name__)

from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


class IoTScaleAuthHandlers:
    """
    Handlers for IoT Scale authentication endpoints
    """
    
    def __init__(self, db_session):
        self.db_session = db_session
        self.auth_service = IoTScaleAuthService(db_session)
    
    def handle_login(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle IoT Scale login request"""
        try:
            # Validate input data
            scale_name = data.get('scale_name')
            password = data.get('password')
            
            if not scale_name or not password:
                raise ValidationException('scale_name and password are required')
            
            # Perform authentication
            auth_result = self.auth_service.login_scale(scale_name, password)
            
            # Create response DTO
            scale_info = IoTScaleInfo(
                id=auth_result['scale']['id'],
                scale_name=auth_result['scale']['scale_name'],
                status=auth_result['scale']['status'],
                location_id=auth_result['scale']['location_id'],
                owner_id=auth_result['scale']['owner_id'],
                added_date=auth_result['scale']['added_date']
            )
            
            login_response = IoTLoginResponse(
                success=auth_result['success'],
                auth_token=auth_result['auth_token'],
                refresh_token=auth_result['refresh_token'],
                token_type=auth_result['token_type'],
                expires_in=auth_result['expires_in'],
                scale=scale_info,
                message="IoT Scale login successful"
            )
            
            return login_response.to_dict()
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, ValidationException)):
                raise e
            logger.error(f"IoT Scale login error: {str(e)}")
            raise APIException(f"Login failed: {str(e)}")

    def handle_refresh_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle IoT Scale token refresh request"""
        try:
            refresh_token = data.get('refresh_token')
            
            if not refresh_token:
                raise ValidationException('refresh_token is required')
            
            # Perform token refresh
            refresh_result = self.auth_service.refresh_iot_token(refresh_token)
            
            return {
                'success': refresh_result['success'],
                'auth_token': refresh_result['auth_token'],
                'refresh_token': refresh_result['refresh_token'],
                'token_type': refresh_result['token_type'],
                'expires_in': refresh_result['expires_in'],
                'message': 'Token refreshed successfully'
            }
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, ValidationException)):
                raise e
            logger.error(f"IoT Scale token refresh error: {str(e)}")
            raise APIException(f"Token refresh failed: {str(e)}")

    def handle_validate_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle IoT Scale token validation request"""
        try:
            token = data.get('token')
            
            if not token:
                raise ValidationException('token is required')
            
            # Perform token validation
            validation_result = self.auth_service.validate_iot_token(token)
            
            return {
                'success': validation_result['success'],
                'scale': validation_result['scale'],
                'message': 'Token is valid'
            }
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, ValidationException)):
                raise e
            logger.error(f"IoT Scale token validation error: {str(e)}")
            raise APIException(f"Token validation failed: {str(e)}")

    def handle_validate_token_header(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """Handle IoT Scale token validation from Authorization header"""
        try:
            auth_header = headers.get('Authorization') or headers.get('authorization')
            
            if not auth_header or not auth_header.startswith("Bearer "):
                raise UnauthorizedException('Authorization header with Bearer token is required')
            
            token = auth_header.split(" ")[1]
            
            # Perform token validation
            validation_result = self.auth_service.validate_iot_token(token)
            
            return {
                'success': validation_result['success'],
                'scale': validation_result['scale'],
                'message': 'Token is valid'
            }
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, ValidationException)):
                raise e
            logger.error(f"IoT Scale token validation error: {str(e)}")
            raise APIException(f"Token validation failed: {str(e)}")
