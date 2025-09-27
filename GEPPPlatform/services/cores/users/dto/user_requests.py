"""
User Service Request DTOs
Based on frontend UserApiService patterns and user_management types
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class UserType(str, Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


class Platform(str, Enum):
    NA = "NA"
    GEPP_BUSINESS_WEB = "GEPP_BUSINESS_WEB"
    GEPP_REWARD_APP = "GEPP_REWARD_APP"
    ADMIN_WEB = "ADMIN_WEB"
    GEPP_EPR_WEB = "GEPP_EPR_WEB"


class BulkOperationType(str, Enum):
    UPDATE_ROLES = "update_roles"
    SUSPEND = "suspend"
    INVITE = "invite"
    REACTIVATE = "reactivate"
    DELETE = "delete"


@dataclass
class CreateUserRequest:
    """
    DTO for creating a new user
    Maps to frontend CreateUserRequest interface
    """
    display_name: str

    # Optional basic info
    name_en: Optional[str] = None
    name_th: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Role and organization
    organization_role_id: Optional[int] = None
    platform: Optional[Platform] = Platform.GEPP_BUSINESS_WEB

    # Business information
    company_name: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    tax_id: Optional[str] = None
    business_type: Optional[str] = None
    business_industry: Optional[str] = None
    business_sub_industry: Optional[str] = None

    # Location data
    address: Optional[str] = None
    postal_code: Optional[str] = None
    coordinate: Optional[str] = None
    country_id: Optional[str] = None
    province_id: Optional[str] = None
    district_id: Optional[str] = None
    subdistrict_id: Optional[str] = None

    # Organizational hierarchy
    organization_id: Optional[str] = None
    parent_user_id: Optional[str] = None

    # Additional fields
    locale: Optional[str] = "TH"
    note: Optional[str] = None
    functions: Optional[str] = None
    send_invitation: Optional[bool] = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class UpdateUserRequest:
    """
    DTO for updating an existing user
    Maps to frontend UpdateUserRequest interface
    """
    user_id: str
    updates: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return self.updates


@dataclass
class QuickCreateRequest:
    """
    DTO for quick user creation
    Maps to frontend QuickCreateData interface
    """
    email_or_phone: str
    organization_role_id: int
    password: Optional[str] = None
    display_name: Optional[str] = None
    company_name: Optional[str] = None
    business_industry: Optional[str] = None
    business_sub_industry: Optional[str] = None
    organization_id: Optional[str] = None
    parent_user_id: Optional[str] = None
    locale: Optional[str] = "TH"
    send_invitation: bool = True

    def to_create_user_request(self) -> CreateUserRequest:
        """Convert to CreateUserRequest"""
        is_email = "@" in self.email_or_phone

        return CreateUserRequest(
            display_name=self.display_name or (
                self.email_or_phone.split("@")[0] if is_email else self.email_or_phone
            ),
            email=self.email_or_phone if is_email else None,
            phone=self.email_or_phone if not is_email else None,
            password=self.password,
            organization_role_id=self.organization_role_id,
            platform=Platform.GEPP_BUSINESS_WEB,
            company_name=self.company_name,
            business_industry=self.business_industry,
            business_sub_industry=self.business_sub_industry,
            organization_id=self.organization_id,
            parent_user_id=self.parent_user_id,
            locale=self.locale,
            send_invitation=self.send_invitation
        )


@dataclass
class UserFiltersRequest:
    """
    DTO for user filtering and search
    Maps to frontend UserFilters interface
    """
    query: Optional[str] = None
    roles: Optional[List[str]] = None
    statuses: Optional[List[UserStatus]] = None
    types: Optional[List[UserType]] = None
    platforms: Optional[List[Platform]] = None
    organization_ids: Optional[List[str]] = None
    has_documents: Optional[bool] = None
    is_expired: Optional[bool] = None

    # Pagination
    page: int = 1
    page_size: int = 20
    sort_by: Optional[str] = "created_date"
    sort_order: Optional[str] = "desc"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for filtering operations"""
        result = {}

        if self.query:
            result['query'] = self.query
        if self.roles:
            result['roles'] = self.roles
        if self.statuses:
            result['statuses'] = [status.value for status in self.statuses]
        if self.types:
            result['types'] = [type_.value for type_ in self.types]
        if self.platforms:
            result['platforms'] = [platform.value for platform in self.platforms]
        if self.organization_ids:
            result['organization_ids'] = self.organization_ids
        if self.has_documents is not None:
            result['has_documents'] = self.has_documents
        if self.is_expired is not None:
            result['is_expired'] = self.is_expired

        return result


@dataclass
class BulkOperationRequest:
    """
    DTO for bulk operations on multiple users
    Maps to frontend BulkOperationRequest interface
    """
    operation: BulkOperationType
    user_ids: List[str]
    organization_role_id: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for bulk operations"""
        result = {
            'operation': self.operation.value,
            'user_ids': self.user_ids
        }

        if self.organization_role_id:
            result['organization_role_id'] = self.organization_role_id
        if self.reason:
            result['reason'] = self.reason

        return result


@dataclass
class InvitationRequest:
    """
    DTO for sending user invitations
    Maps to frontend InvitationRequest interface
    """
    email: str
    organization_id: str
    phone: Optional[str] = None
    organization_role_id: Optional[int] = None
    custom_message: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for invitation operations"""
        result = {
            'email': self.email,
            'organization_id': self.organization_id
        }

        if self.phone:
            result['phone'] = self.phone
        if self.organization_role_id:
            result['organization_role_id'] = self.organization_role_id
        if self.custom_message:
            result['custom_message'] = self.custom_message
        if self.additional_data:
            result['additional_data'] = self.additional_data

        return result


@dataclass
class AcceptInvitationRequest:
    """
    DTO for accepting user invitations
    Maps to frontend acceptInvitation method parameters
    """
    token: str
    display_name: str
    password: str
    name_en: Optional[str] = None
    name_th: Optional[str] = None
    phone: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for invitation acceptance"""
        result = {
            'display_name': self.display_name,
            'password': self.password
        }

        if self.name_en:
            result['name_en'] = self.name_en
        if self.name_th:
            result['name_th'] = self.name_th
        if self.phone:
            result['phone'] = self.phone

        return result


@dataclass
class ResetPasswordRequest:
    """
    DTO for password reset operations
    """
    user_id: str
    new_password: Optional[str] = None  # If None, generate temporary password
    send_notification: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for password reset operations"""
        return {
            'new_password': self.new_password,
            'send_notification': self.send_notification
        }


@dataclass
class UploadProfileImageRequest:
    """
    DTO for profile image upload operations
    """
    user_id: str
    file_data: bytes
    file_name: str
    content_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for image upload operations"""
        return {
            'file_name': self.file_name,
            'content_type': self.content_type
        }