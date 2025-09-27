"""
User Service Response DTOs
Based on frontend UserApiService response patterns and user_management types
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LocationReference:
    """Reference to location entities"""
    id: str
    name: str
    code: Optional[str] = None


@dataclass
class OrganizationTree:
    """Organization hierarchy information"""
    level: int
    path: str
    parent: Optional[Dict[str, str]] = None
    children_count: int = 0


@dataclass
class SubscriptionStatus:
    """User subscription status information"""
    has_active_subscription: bool
    package_name: str
    expires_at: Optional[str] = None


@dataclass
class UserFlags:
    """User validation and status flags"""
    missing_username: Optional[bool] = None
    missing_company: Optional[bool] = None
    invalid_phone: Optional[bool] = None
    unverified_email: Optional[bool] = None
    no_activity_30d: Optional[bool] = None
    duplicate_email: Optional[bool] = None
    duplicate_phone: Optional[bool] = None
    missing_business_info: Optional[bool] = None
    expired_documents: Optional[bool] = None


@dataclass
class UserResponse:
    """
    DTO for user data response
    Maps to frontend UserLocation interface
    """
    # Core identification
    id: str
    display_name: str

    # User/Location flags
    is_user: bool = True
    is_location: bool = False

    # Basic information
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    email: Optional[str] = None
    is_email_active: bool = False
    email_notification: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None

    # Platform & Roles
    platform: str = "GEPP_BUSINESS_WEB"
    role: str = "viewer"
    organization_role_id: Optional[int] = None
    status: str = "active"
    type: str = "business"

    # Business information
    company_name: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    tax_id: Optional[str] = None
    business_type: Optional[str] = None
    business_industry: Optional[str] = None
    business_sub_industry: Optional[str] = None

    # Location data
    coordinate: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[LocationReference] = None
    province: Optional[LocationReference] = None
    district: Optional[LocationReference] = None
    subdistrict: Optional[LocationReference] = None

    # Waste management specific
    functions: Optional[str] = None
    material: Optional[str] = None
    population: Optional[str] = None

    # Profile & Documents
    profile_image_url: Optional[str] = None
    avatar: Optional[str] = None
    national_id: Optional[str] = None
    national_card_image: Optional[str] = None
    business_registration_certificate: Optional[str] = None

    # Organizational hierarchy
    organization_id: Optional[str] = None
    parent_user_id: Optional[str] = None
    organization_level: int = 0
    organization_path: Optional[str] = None

    # Localization
    locale: str = "TH"
    nationality: Optional[LocationReference] = None
    currency: Optional[LocationReference] = None
    phone_code: Optional[LocationReference] = None

    # Additional
    note: Optional[str] = None
    expired_date: Optional[str] = None
    footprint: Optional[float] = None

    # Computed fields
    flags: Optional[UserFlags] = None
    last_active_at: Optional[str] = None
    invited_at: Optional[str] = None

    # Audit fields
    created_at: str = ""
    updated_at: str = ""
    created_date: Optional[str] = None
    updated_date: Optional[str] = None
    is_active: bool = True

    # Metadata
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ActivityResponse:
    """
    DTO for user activity data
    Maps to frontend Activity interface
    """
    id: str
    user_id: str
    actor_id: str
    actor_name: str
    at: str
    type: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PermissionsResponse:
    """
    DTO for user permissions data
    """
    can_view: bool = False
    can_edit: bool = False
    can_create: bool = False
    can_delete: bool = False
    can_invite: bool = False
    can_suspend: bool = False
    can_manage_organization: bool = False
    can_view_logs: bool = False
    can_bulk_edit: bool = False
    can_export: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class UserDetailsResponse:
    """
    DTO for detailed user information
    Maps to frontend UserDetailsResponse interface
    """
    user: UserResponse
    activities: List[ActivityResponse]
    permissions: PermissionsResponse
    organization_tree: OrganizationTree
    subscription_status: SubscriptionStatus

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'user': self.user.to_dict(),
            'activities': [activity.to_dict() for activity in self.activities],
            'permissions': self.permissions.to_dict(),
            'organization_tree': self.organization_tree.__dict__,
            'subscription_status': self.subscription_status.__dict__
        }


@dataclass
class UsersListResponse:
    """
    DTO for paginated users list
    Maps to frontend UsersResponse interface
    """
    data: List[UserResponse]
    total: int
    page: int
    size: int
    has_more: bool
    aggregations: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'data': [user.to_dict() for user in self.data],
            'total': self.total,
            'page': self.page,
            'size': self.size,
            'hasMore': self.has_more,
            'aggregations': self.aggregations
        }


@dataclass
class BulkOperationResponse:
    """
    DTO for bulk operation results
    Maps to frontend bulk operation response patterns
    """
    operation: str
    total_requested: int
    updated_count: Optional[int] = None
    suspended_count: Optional[int] = None
    invited_count: Optional[int] = None
    reactivated_count: Optional[int] = None
    deleted_count: Optional[int] = None
    errors: Optional[List[str]] = None
    users: Optional[List[UserResponse]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'operation': self.operation,
            'total_requested': self.total_requested
        }

        if self.updated_count is not None:
            result['updated_count'] = self.updated_count
        if self.suspended_count is not None:
            result['suspended_count'] = self.suspended_count
        if self.invited_count is not None:
            result['invited_count'] = self.invited_count
        if self.reactivated_count is not None:
            result['reactivated_count'] = self.reactivated_count
        if self.deleted_count is not None:
            result['deleted_count'] = self.deleted_count
        if self.errors:
            result['errors'] = self.errors
        if self.users:
            result['users'] = [user.to_dict() for user in self.users]

        return result


@dataclass
class InvitationResponse:
    """
    DTO for invitation operation results
    Maps to frontend sendInvitation response
    """
    id: str
    email: str
    token: str
    expires_at: str
    invitation_url: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class ResetPasswordResponse:
    """
    DTO for password reset operation results
    Maps to frontend resetPassword response
    """
    message: str
    temp_password: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {'message': self.message}
        if self.temp_password:
            result['temp_password'] = self.temp_password
        return result


@dataclass
class ProfileImageResponse:
    """
    DTO for profile image upload results
    Maps to frontend uploadProfileImage response
    """
    profile_image_url: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class ValidationResponse:
    """
    DTO for validation operation results
    """
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    flags: UserFlags

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'isValid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'flags': self.flags.__dict__ if self.flags else {}
        }