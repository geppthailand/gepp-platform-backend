"""
DTO Index
Central registry for all Data Transfer Objects across services
"""

# Base DTO classes and utilities
from .base_dto import (
    BaseDTO,
    ApiResponseDTO,
    PaginationMeta,
    ErrorDTO,
    DTOValidationMixin,
    DTOFactory
)

# User Service DTOs
from .cores.users.dto import (
    # User Requests
    CreateUserRequest,
    UpdateUserRequest,
    BulkOperationRequest,
    InvitationRequest,
    QuickCreateRequest,
    UserFiltersRequest,
    AcceptInvitationRequest,
    ResetPasswordRequest,
    UploadProfileImageRequest,

    # User Responses
    UserResponse,
    UserDetailsResponse,
    UsersListResponse,
    BulkOperationResponse,
    InvitationResponse,
    ActivityResponse,
    ValidationResponse,
    PermissionsResponse,
    ProfileImageResponse,
    ResetPasswordResponse as UserResetPasswordResponse
)

# Organization Service DTOs
from .cores.organizations.dto import (
    # Organization Requests
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
    CreateRoleRequest,
    UpdateRoleRequest,
    CreateMemberRequest,
    UpdateMemberRequest,
    BulkAssignRolesRequest,
    ExportMembersRequest,
    ImportMembersRequest,
    OrganizationFiltersRequest,

    # Organization Responses
    OrganizationResponse,
    OrganizationRoleResponse,
    OrganizationMemberResponse,
    OrganizationMembersListResponse,
    OrganizationStructureResponse,
    OrganizationStatsResponse,
    BulkAssignRolesResponse,
    ExportMembersResponse,
    ImportMembersResponse,
    ValidationPermissionResponse,
    ResendInvitationResponse
)

# Auth Service DTOs
from .auth.dto import (
    # Auth Requests
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    ResetPasswordRequest as AuthResetPasswordRequest,
    ChangePasswordRequest,
    VerifyTokenRequest,
    LogoutRequest,
    SocialLoginRequest,

    # Auth Responses
    LoginResponse,
    RegisterResponse,
    RefreshTokenResponse,
    ResetPasswordResponse as AuthResetPasswordResponse,
    ChangePasswordResponse,
    VerifyTokenResponse,
    LogoutResponse,
    UserProfileResponse,
    TokenValidationResponse
)

# Business Service DTOs
from .business.dto import (
    # Business Requests
    BusinessProfileRequest,
    BusinessSettingsRequest,
    BusinessMetricsRequest,
    BusinessReportRequest,

    # Business Responses
    BusinessProfileResponse,
    BusinessSettingsResponse,
    BusinessMetricsResponse,
    BusinessReportResponse
)

# EPR Service DTOs
from .epr.dto import (
    # EPR Requests
    EPRReportRequest,
    EPRComplianceRequest,
    EPRSubmissionRequest,
    EPRCertificateRequest,

    # EPR Responses
    EPRReportResponse,
    EPRComplianceResponse,
    EPRSubmissionResponse,
    EPRCertificateResponse,
    EPRStatusResponse
)

# G360 Service DTOs
from .g360.dto import (
    # G360 Requests
    G360SyncRequest,
    G360DataRequest,
    G360IntegrationRequest,
    G360WebhookRequest,

    # G360 Responses
    G360SyncResponse,
    G360DataResponse,
    G360IntegrationResponse,
    G360WebhookResponse,
    G360StatusResponse
)

# Export all DTOs for easy import
__all__ = [
    # Base classes
    'BaseDTO',
    'ApiResponseDTO',
    'PaginationMeta',
    'ErrorDTO',
    'DTOValidationMixin',
    'DTOFactory',

    # User Service
    'CreateUserRequest',
    'UpdateUserRequest',
    'BulkOperationRequest',
    'InvitationRequest',
    'QuickCreateRequest',
    'UserFiltersRequest',
    'AcceptInvitationRequest',
    'ResetPasswordRequest',
    'UploadProfileImageRequest',
    'UserResponse',
    'UserDetailsResponse',
    'UsersListResponse',
    'BulkOperationResponse',
    'InvitationResponse',
    'ActivityResponse',
    'ValidationResponse',
    'PermissionsResponse',
    'ProfileImageResponse',
    'UserResetPasswordResponse',

    # Organization Service
    'CreateOrganizationRequest',
    'UpdateOrganizationRequest',
    'CreateRoleRequest',
    'UpdateRoleRequest',
    'CreateMemberRequest',
    'UpdateMemberRequest',
    'BulkAssignRolesRequest',
    'ExportMembersRequest',
    'ImportMembersRequest',
    'OrganizationFiltersRequest',
    'OrganizationResponse',
    'OrganizationRoleResponse',
    'OrganizationMemberResponse',
    'OrganizationMembersListResponse',
    'OrganizationStructureResponse',
    'OrganizationStatsResponse',
    'BulkAssignRolesResponse',
    'ExportMembersResponse',
    'ImportMembersResponse',
    'ValidationPermissionResponse',
    'ResendInvitationResponse',

    # Auth Service
    'LoginRequest',
    'RegisterRequest',
    'RefreshTokenRequest',
    'AuthResetPasswordRequest',
    'ChangePasswordRequest',
    'VerifyTokenRequest',
    'LogoutRequest',
    'SocialLoginRequest',
    'LoginResponse',
    'RegisterResponse',
    'RefreshTokenResponse',
    'AuthResetPasswordResponse',
    'ChangePasswordResponse',
    'VerifyTokenResponse',
    'LogoutResponse',
    'UserProfileResponse',
    'TokenValidationResponse',

    # Business Service
    'BusinessProfileRequest',
    'BusinessSettingsRequest',
    'BusinessMetricsRequest',
    'BusinessReportRequest',
    'BusinessProfileResponse',
    'BusinessSettingsResponse',
    'BusinessMetricsResponse',
    'BusinessReportResponse',

    # EPR Service
    'EPRReportRequest',
    'EPRComplianceRequest',
    'EPRSubmissionRequest',
    'EPRCertificateRequest',
    'EPRReportResponse',
    'EPRComplianceResponse',
    'EPRSubmissionResponse',
    'EPRCertificateResponse',
    'EPRStatusResponse',

    # G360 Service
    'G360SyncRequest',
    'G360DataRequest',
    'G360IntegrationRequest',
    'G360WebhookRequest',
    'G360SyncResponse',
    'G360DataResponse',
    'G360IntegrationResponse',
    'G360WebhookResponse',
    'G360StatusResponse'
]


# DTO Registry for dynamic access
DTO_REGISTRY = {
    'users': {
        'requests': [
            CreateUserRequest, UpdateUserRequest, BulkOperationRequest,
            InvitationRequest, QuickCreateRequest, UserFiltersRequest,
            AcceptInvitationRequest, ResetPasswordRequest, UploadProfileImageRequest
        ],
        'responses': [
            UserResponse, UserDetailsResponse, UsersListResponse,
            BulkOperationResponse, InvitationResponse, ActivityResponse,
            ValidationResponse, PermissionsResponse, ProfileImageResponse,
            UserResetPasswordResponse
        ]
    },
    'organizations': {
        'requests': [
            CreateOrganizationRequest, UpdateOrganizationRequest, CreateRoleRequest,
            UpdateRoleRequest, CreateMemberRequest, UpdateMemberRequest,
            BulkAssignRolesRequest, ExportMembersRequest, ImportMembersRequest,
            OrganizationFiltersRequest
        ],
        'responses': [
            OrganizationResponse, OrganizationRoleResponse, OrganizationMemberResponse,
            OrganizationMembersListResponse, OrganizationStructureResponse,
            OrganizationStatsResponse, BulkAssignRolesResponse, ExportMembersResponse,
            ImportMembersResponse, ValidationPermissionResponse, ResendInvitationResponse
        ]
    },
    'auth': {
        'requests': [
            LoginRequest, RegisterRequest, RefreshTokenRequest, AuthResetPasswordRequest,
            ChangePasswordRequest, VerifyTokenRequest, LogoutRequest, SocialLoginRequest
        ],
        'responses': [
            LoginResponse, RegisterResponse, RefreshTokenResponse, AuthResetPasswordResponse,
            ChangePasswordResponse, VerifyTokenResponse, LogoutResponse,
            UserProfileResponse, TokenValidationResponse
        ]
    },
    'business': {
        'requests': [
            BusinessProfileRequest, BusinessSettingsRequest, BusinessMetricsRequest,
            BusinessReportRequest
        ],
        'responses': [
            BusinessProfileResponse, BusinessSettingsResponse, BusinessMetricsResponse,
            BusinessReportResponse
        ]
    },
    'epr': {
        'requests': [
            EPRReportRequest, EPRComplianceRequest, EPRSubmissionRequest,
            EPRCertificateRequest
        ],
        'responses': [
            EPRReportResponse, EPRComplianceResponse, EPRSubmissionResponse,
            EPRCertificateResponse, EPRStatusResponse
        ]
    },
    'g360': {
        'requests': [
            G360SyncRequest, G360DataRequest, G360IntegrationRequest,
            G360WebhookRequest
        ],
        'responses': [
            G360SyncResponse, G360DataResponse, G360IntegrationResponse,
            G360WebhookResponse, G360StatusResponse
        ]
    }
}


def get_dto_class(service: str, category: str, name: str):
    """
    Dynamically get a DTO class by service, category (requests/responses), and name

    Args:
        service: Service name (e.g., 'users', 'organizations')
        category: 'requests' or 'responses'
        name: DTO class name

    Returns:
        DTO class or None if not found
    """
    if service not in DTO_REGISTRY:
        return None

    if category not in DTO_REGISTRY[service]:
        return None

    for dto_class in DTO_REGISTRY[service][category]:
        if dto_class.__name__ == name:
            return dto_class

    return None


def list_dtos(service: str = None, category: str = None) -> dict:
    """
    List available DTOs, optionally filtered by service and/or category

    Args:
        service: Optional service name filter
        category: Optional category filter ('requests' or 'responses')

    Returns:
        Dictionary of available DTOs
    """
    if service and service in DTO_REGISTRY:
        registry = {service: DTO_REGISTRY[service]}
    else:
        registry = DTO_REGISTRY

    result = {}
    for svc, categories in registry.items():
        result[svc] = {}
        for cat, dtos in categories.items():
            if not category or cat == category:
                result[svc][cat] = [dto.__name__ for dto in dtos]

    return result