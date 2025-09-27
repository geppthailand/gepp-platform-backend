"""
Auth Service DTOs
Data Transfer Objects for authentication and authorization operations
"""

from .auth_requests import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    VerifyTokenRequest,
    LogoutRequest,
    SocialLoginRequest
)

from .auth_responses import (
    LoginResponse,
    RegisterResponse,
    RefreshTokenResponse,
    ResetPasswordResponse,
    ChangePasswordResponse,
    VerifyTokenResponse,
    LogoutResponse,
    UserProfileResponse,
    TokenValidationResponse
)

__all__ = [
    # Request DTOs
    'LoginRequest',
    'RegisterRequest',
    'RefreshTokenRequest',
    'ResetPasswordRequest',
    'ChangePasswordRequest',
    'VerifyTokenRequest',
    'LogoutRequest',
    'SocialLoginRequest',

    # Response DTOs
    'LoginResponse',
    'RegisterResponse',
    'RefreshTokenResponse',
    'ResetPasswordResponse',
    'ChangePasswordResponse',
    'VerifyTokenResponse',
    'LogoutResponse',
    'UserProfileResponse',
    'TokenValidationResponse'
]