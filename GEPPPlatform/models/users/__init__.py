"""
Users models package - User, location, and organizational hierarchy
"""

from .user_location import UserLocation, user_subusers
from .user_related import UserBank, UserSubscription, UserInputChannel, UserRole, UserRoleEnum, UserLocationTag, UserTenant
from .integration_tokens import IntegrationToken
from .user_location_materials import UserLocationMaterial
from .user_reset_password_log import UserResetPasswordLog

__all__ = [
    # Main user-location model
    'UserLocation', 'user_subusers',

    # User-related tables
    'UserBank', 'UserSubscription', 'UserInputChannel', 'UserRole', 'UserRoleEnum',

    # Location tags
    'UserLocationTag',

    # Tenants (same pattern as location tags)
    'UserTenant',

    # Integration tokens
    'IntegrationToken',

    # Password reset logs
    'UserResetPasswordLog',

    # Associations
    'UserLocationMaterial'
]