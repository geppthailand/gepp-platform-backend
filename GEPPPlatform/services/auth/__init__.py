"""
Auth module for handling authentication and authorization routes
"""

import os

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
        elif internal_path == "/liff":
            # LINE LIFF login — exchange LINE access token for JWT
            from GEPPPlatform.services.esg.liff_auth_service import LiffAuthService
            if not data or not data.get('access_token'):
                raise BadRequestException('LINE access_token is required')
            liff_svc = LiffAuthService(db_session)
            try:
                return liff_svc.login_with_line(data['access_token'])
            except ValueError as ve:
                raise UnauthorizedException(str(ve))
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
        elif internal_path == "/permissions":
            return auth_handler.get_permissions(**commonParams)
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
        elif internal_path == "/link-company":
            # Link authenticated user to an organization via joining code (LIFF onboarding)
            # Auth routes skip global JWT middleware, so we parse the token manually here.
            import jwt as _jwt
            from GEPPPlatform.services.esg.liff_auth_service import LiffAuthService
            if not data or not data.get('joining_code'):
                raise BadRequestException('joining_code is required')
            headers = commonParams.get('headers', {}) or {}
            auth_header = headers.get('authorization') or headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '').strip() if auth_header else ''
            if not token:
                raise UnauthorizedException('Authentication required')
            try:
                secret = os.environ.get('JWT_SECRET', os.environ.get('JWT_SECRET_KEY', 'your-secret-key'))
                algo = os.environ.get('JWT_ALGORITHM', 'HS256')
                payload = _jwt.decode(token, secret, algorithms=[algo])
                user_id = payload.get('user_id')
                if not user_id:
                    raise UnauthorizedException('Invalid token')
            except _jwt.InvalidTokenError:
                raise UnauthorizedException('Invalid or expired token')
            liff_svc = LiffAuthService(db_session)
            try:
                return liff_svc.link_company(int(user_id), data['joining_code'])
            except ValueError as ve:
                raise BadRequestException(str(ve))
        else:
            raise NotFoundException(f"PUT endpoint not found: {internal_path}")
    
    elif method == "DELETE":
        if internal_path == "/logout":
            return auth_handler.logout(**commonParams)
        else:
            raise NotFoundException(f"DELETE endpoint not found: {internal_path}")
    
    else:
        raise BadRequestException(f"Method {method} not supported")