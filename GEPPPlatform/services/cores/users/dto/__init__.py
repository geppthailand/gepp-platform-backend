"""
User Service DTOs
Data Transfer Objects for user management operations
"""

from .user_requests import (
    CreateUserRequest,
    UpdateUserRequest,
    BulkOperationRequest,
    InvitationRequest,
    QuickCreateRequest,
    UserFiltersRequest,
    AcceptInvitationRequest,
    ResetPasswordRequest,
    UploadProfileImageRequest
)

from .user_responses import (
    UserResponse,
    UserDetailsResponse,
    UsersListResponse,
    BulkOperationResponse,
    InvitationResponse,
    ActivityResponse,
    ValidationResponse,
    PermissionsResponse,
    ProfileImageResponse,
    ResetPasswordResponse
)

__all__ = [
    # Request DTOs
    'CreateUserRequest',
    'UpdateUserRequest',
    'BulkOperationRequest',
    'InvitationRequest',
    'QuickCreateRequest',
    'UserFiltersRequest',
    'AcceptInvitationRequest',
    'ResetPasswordRequest',
    'UploadProfileImageRequest',

    # Response DTOs
    'UserResponse',
    'UserDetailsResponse',
    'UsersListResponse',
    'BulkOperationResponse',
    'InvitationResponse',
    'ActivityResponse',
    'ValidationResponse',
    'PermissionsResponse',
    'ProfileImageResponse',
    'ResetPasswordResponse'
]