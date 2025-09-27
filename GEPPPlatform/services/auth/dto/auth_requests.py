"""
Auth Service Request DTOs
Based on common authentication patterns and auth handlers
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class SocialProvider(str, Enum):
    GOOGLE = "google"
    FACEBOOK = "facebook"
    APPLE = "apple"


@dataclass
class LoginRequest:
    """
    DTO for user login
    Supports email/username and password authentication
    """
    email_or_username: str
    password: str
    remember_me: Optional[bool] = False
    device_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for authentication operations"""
        result = {
            'email_or_username': self.email_or_username,
            'password': self.password,
            'remember_me': self.remember_me
        }

        if self.device_info:
            result['device_info'] = self.device_info

        return result


@dataclass
class SocialLoginRequest:
    """
    DTO for social media login (Google, Facebook, Apple)
    """
    provider: SocialProvider
    provider_token: str
    provider_user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for social authentication operations"""
        result = {
            'provider': self.provider.value,
            'provider_token': self.provider_token,
            'provider_user_id': self.provider_user_id
        }

        if self.email:
            result['email'] = self.email
        if self.display_name:
            result['display_name'] = self.display_name
        if self.device_info:
            result['device_info'] = self.device_info

        return result


@dataclass
class RegisterRequest:
    """
    DTO for user registration
    """
    display_name: str
    email: str
    password: str
    confirm_password: str
    phone: Optional[str] = None
    organization_name: Optional[str] = None
    business_type: Optional[str] = None
    business_industry: Optional[str] = None
    tax_id: Optional[str] = None
    locale: Optional[str] = "TH"
    terms_accepted: bool = True
    marketing_consent: Optional[bool] = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for registration operations"""
        result = {
            'display_name': self.display_name,
            'email': self.email,
            'password': self.password,
            'confirm_password': self.confirm_password,
            'locale': self.locale,
            'terms_accepted': self.terms_accepted,
            'marketing_consent': self.marketing_consent
        }

        if self.phone:
            result['phone'] = self.phone
        if self.organization_name:
            result['organization_name'] = self.organization_name
        if self.business_type:
            result['business_type'] = self.business_type
        if self.business_industry:
            result['business_industry'] = self.business_industry
        if self.tax_id:
            result['tax_id'] = self.tax_id

        return result


@dataclass
class RefreshTokenRequest:
    """
    DTO for refreshing authentication tokens
    """
    refresh_token: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for token refresh operations"""
        return {'refresh_token': self.refresh_token}


@dataclass
class ResetPasswordRequest:
    """
    DTO for password reset initiation
    """
    email: str
    callback_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for password reset operations"""
        result = {'email': self.email}
        if self.callback_url:
            result['callback_url'] = self.callback_url
        return result


@dataclass
class ChangePasswordRequest:
    """
    DTO for changing user password
    """
    current_password: str
    new_password: str
    confirm_new_password: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for password change operations"""
        return {
            'current_password': self.current_password,
            'new_password': self.new_password,
            'confirm_new_password': self.confirm_new_password
        }


@dataclass
class VerifyTokenRequest:
    """
    DTO for token verification
    """
    token: str
    token_type: Optional[str] = "auth"  # auth, refresh, reset, invitation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for token verification operations"""
        return {
            'token': self.token,
            'token_type': self.token_type
        }


@dataclass
class LogoutRequest:
    """
    DTO for user logout
    """
    refresh_token: Optional[str] = None
    logout_all_devices: Optional[bool] = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logout operations"""
        result = {'logout_all_devices': self.logout_all_devices}
        if self.refresh_token:
            result['refresh_token'] = self.refresh_token
        return result