"""
Auth module for handling authentication and authorization routes
"""

from .auth_handlers import AuthHandlers
from ...exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)

def handle_auth_routes(path: str, data: dict, **commonParams):
    """
    Route handler for all /api/auth/* endpoints
    """
    method = commonParams["method"]
    db_session = commonParams.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    auth_handler = AuthHandlers(db_session)
    
    # Remove /api/auth prefix from path for internal routing
    internal_path = path.replace('/api/auth', '')
    
    if method == "POST":
        if internal_path == "/register":
            return auth_handler.register(data, **commonParams)
        elif internal_path == "/login":
            return auth_handler.login(data, **commonParams)
        elif internal_path == "/integration":
            return auth_handler.integration_login(data, **commonParams)
        elif internal_path == "/integration/secret":
            return auth_handler.generate_integration_secret(data, **commonParams)
        elif internal_path == "/validate":
            return auth_handler.validate_token(data, **commonParams)
        elif internal_path == "/refresh":
            return auth_handler.refresh_token(data, **commonParams)
        elif internal_path == "/iot-devices/login":
            return auth_handler.login_iot_device(data, **commonParams)
        elif internal_path == "/forgot-password":
            return auth_handler.forgot_password(data, **commonParams)
        elif internal_path == "/reset-password":
            return auth_handler.reset_password(data, **commonParams)
        else:
            raise NotFoundException(f"POST endpoint not found: {internal_path}")
    
    elif method == "GET":
        if internal_path == "/validate":
            return auth_handler.validate_token_header(**commonParams)
        elif internal_path == "/profile":
            return auth_handler.get_profile(**commonParams)
        elif internal_path == "/check-email":
            email = commonParams.get('query_params', {}).get('email', '')
            return auth_handler.check_email_exists(email)
        else:
            raise NotFoundException(f"GET endpoint not found: {internal_path}")
    
    elif method == "PUT":
        if internal_path == "/profile":
            return auth_handler.update_profile(data, **commonParams)
        elif internal_path == "/password":
            return auth_handler.change_password(data, **commonParams)
        else:
            raise NotFoundException(f"PUT endpoint not found: {internal_path}")
    
    elif method == "DELETE":
        if internal_path == "/logout":
            return auth_handler.logout(**commonParams)
        else:
            raise NotFoundException(f"DELETE endpoint not found: {internal_path}")
    
    else:
        raise BadRequestException(f"Method {method} not supported")