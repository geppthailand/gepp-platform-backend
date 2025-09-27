"""
Auth Service Response DTOs
Based on common authentication patterns and auth handlers
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class TokenInfo:
    """JWT token information"""
    token: str
    expires_at: str
    token_type: str = "Bearer"


@dataclass
class UserProfileResponse:
    """User profile information for authentication responses"""
    id: str
    display_name: str
    email: str
    username: Optional[str] = None
    phone: Optional[str] = None
    profile_image_url: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    locale: str = "TH"
    is_active: bool = True
    last_login_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class LoginResponse:
    """
    DTO for successful login response
    Maps to frontend auth response patterns
    """
    success: bool
    user: UserProfileResponse
    auth_token: str
    refresh_token: str
    expires_at: str
    message: Optional[str] = "Login successful"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'user': self.user.to_dict(),
            'auth_token': self.auth_token,
            'refresh_token': self.refresh_token,
            'expires_at': self.expires_at,
            'message': self.message
        }


@dataclass
class RegisterResponse:
    """
    DTO for successful registration response
    """
    success: bool
    user: UserProfileResponse
    auth_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[str] = None
    requires_verification: bool = False
    verification_sent_to: Optional[str] = None
    message: Optional[str] = "Registration successful"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'success': self.success,
            'user': self.user.to_dict(),
            'requires_verification': self.requires_verification,
            'message': self.message
        }

        if self.auth_token:
            result['auth_token'] = self.auth_token
        if self.refresh_token:
            result['refresh_token'] = self.refresh_token
        if self.expires_at:
            result['expires_at'] = self.expires_at
        if self.verification_sent_to:
            result['verification_sent_to'] = self.verification_sent_to

        return result


@dataclass
class RefreshTokenResponse:
    """
    DTO for token refresh response
    """
    success: bool
    auth_token: str
    refresh_token: Optional[str] = None
    expires_at: str = ""
    message: Optional[str] = "Token refreshed successfully"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'success': self.success,
            'auth_token': self.auth_token,
            'expires_at': self.expires_at,
            'message': self.message
        }

        if self.refresh_token:
            result['refresh_token'] = self.refresh_token

        return result


@dataclass
class ResetPasswordResponse:
    """
    DTO for password reset response
    """
    success: bool
    message: str
    reset_token_sent: bool = False
    sent_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'success': self.success,
            'message': self.message,
            'reset_token_sent': self.reset_token_sent
        }

        if self.sent_to:
            result['sent_to'] = self.sent_to

        return result


@dataclass
class ChangePasswordResponse:
    """
    DTO for password change response
    """
    success: bool
    message: str
    requires_reauth: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'message': self.message,
            'requires_reauth': self.requires_reauth
        }


@dataclass
class VerifyTokenResponse:
    """
    DTO for token verification response
    """
    valid: bool
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    expires_at: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {'valid': self.valid}

        if self.user_id:
            result['user_id'] = self.user_id
        if self.organization_id:
            result['organization_id'] = self.organization_id
        if self.expires_at:
            result['expires_at'] = self.expires_at
        if self.permissions:
            result['permissions'] = self.permissions
        if self.message:
            result['message'] = self.message

        return result


@dataclass
class LogoutResponse:
    """
    DTO for logout response
    """
    success: bool
    message: str = "Logout successful"
    tokens_invalidated: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'message': self.message,
            'tokens_invalidated': self.tokens_invalidated
        }


@dataclass
class TokenValidationResponse:
    """
    DTO for token validation middleware response
    """
    valid: bool
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for validation responses"""
        result = {'valid': self.valid}

        if self.user_id:
            result['user_id'] = self.user_id
        if self.organization_id:
            result['organization_id'] = self.organization_id
        if self.role:
            result['role'] = self.role
        if self.permissions:
            result['permissions'] = self.permissions
        if self.error:
            result['error'] = self.error

        return result