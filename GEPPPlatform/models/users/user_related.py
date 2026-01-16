"""
User-related models for comprehensive user management
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Enum, Integer, JSON, DECIMAL, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.types import Date
from ..base import Base, BaseModel, PlatformEnum
import enum

class UserRoleEnum(enum.Enum):
    """Platform-level roles"""
    SUPER_ADMIN = 'super-admin'      # Platform super administrator
    GEPP_ADMIN = 'gepp-admin'        # GEPP company administrator
    BUSINESS = 'business'            # Business user
    REWARDS = 'rewards'              # Rewards program user
    EPR = 'epr'                      # EPR compliance user


class UserRole(Base, BaseModel):
    """
    Platform-specific user roles and permissions
    Maps to user_roles table referenced by UserLocation.role_id
    """
    __tablename__ = 'user_roles'

    # Organization linkage (nullable for platform-wide roles)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    permissions = Column(Text)  # JSONB column for permissions

    # Relationships
    organization = relationship("Organization")

    def __repr__(self):
        return f"<UserRole(id={self.id}, name='{self.name}', organization_id={self.organization_id})>"

class UserInputChannel(Base, BaseModel):
    """
    User Input Channel for QR code-based transaction input
    Channels are organization-level, subusers are validated against organization members
    """
    __tablename__ = 'user_input_channels'

    # user_location_id is optional - channels are now organization-level
    user_location_id = Column(ForeignKey('user_locations.id'), nullable=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)

    # Channel name for identification
    channel_name = Column(String(255), nullable=True)

    # QR Code hash for unique identification
    hash = Column(String(255), unique=True, index=True)

    # Channel configuration
    channel_type = Column(String(100), default='qr')  # qr, api, etc.
    form_type = Column(String(50), default='daily')  # form, daily, monthly

    # Material configuration (JSON arrays) - kept for legacy but not used in new flow
    sub_material_ids = Column(JSON, default=list)  # List of material IDs
    sub_material_destination_ids = Column(JSON, default=list)  # List of destination location IDs

    # Sub-user configuration - kept for legacy but validation now uses organization membership
    subuser_names = Column(JSON, default=list)  # List of sub-user names for login (legacy)
    subuser_material_preferences = Column(JSON, default=dict)  # Per-subuser material preferences

    # Feature flags
    enable_upload_image = Column(Boolean, default=False)
    required_tag = Column(Boolean, default=False)
    is_drop_off_point = Column(Boolean, default=False)

    # Relationships
    user_location = relationship("UserLocation", back_populates="input_channels")
    organization = relationship("Organization")

class UserBank(Base, BaseModel):
    """
    Enhanced user banking information for payments and rewards
    """
    __tablename__ = 'user_bank'

    user_location_id = Column(ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    bank_id = Column(ForeignKey('banks.id'))

    # Enhanced bank details
    account_number = Column(String(50))
    account_name = Column(String(255))
    account_type = Column(String(50))  # savings, checking, etc.

    # Branch information
    branch_name = Column(String(255))
    branch_code = Column(String(20))

    # Status and verification
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime)
    is_primary = Column(Boolean, default=False)

    # Additional info
    note = Column(Text)

    # Relationships
    user_location = relationship("UserLocation")
    bank = relationship("Bank")
    organization = relationship("Organization")

class UserSubscription(Base, BaseModel):
    """
    User's subscription to specific packages
    Links to organization subscription but tracks individual user access
    """
    __tablename__ = 'user_subscriptions'

    user_location_id = Column(ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    subscription_package_id = Column(ForeignKey('subscription_packages.id'), nullable=False)

    # Subscription details
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    status = Column(String(50), default='active')  # active, suspended, expired, cancelled

    # Billing
    billing_cycle = Column(String(20))  # monthly, yearly
    next_billing_date = Column(Date)
    auto_renew = Column(Boolean, default=True)

    # Usage tracking
    usage_data = Column(JSON)  # Track usage against subscription limits

    # Relationships
    user_location = relationship("UserLocation")
    subscription_package = relationship("SubscriptionPackage")
    organization = relationship("Organization")

class UserActivity(Base, BaseModel):
    """
    Track user activities for audit and analytics
    """
    __tablename__ = 'user_activities'

    user_location_id = Column(ForeignKey('user_locations.id'), nullable=False)
    actor_id = Column(ForeignKey('user_locations.id'))  # Who performed the action

    # Activity details
    activity_type = Column(String(100), nullable=False)  # login, logout, create_user, etc.
    resource = Column(String(100))  # What was affected
    action = Column(String(100))    # What action was taken

    # Activity data
    details = Column(JSON)  # Additional activity details
    ip_address = Column(String(45))
    user_agent = Column(Text)

    # Context
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    session_id = Column(String(255))

    # Relationships
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    actor = relationship("UserLocation", foreign_keys=[actor_id])

class UserDevice(Base, BaseModel):
    """
    Track user devices for security and analytics
    """
    __tablename__ = 'user_devices'

    user_location_id = Column(ForeignKey('user_locations.id'), nullable=False)

    # Device identification
    device_id = Column(String(255), nullable=False)  # Unique device identifier
    device_name = Column(String(255))
    device_type = Column(String(50))  # mobile, tablet, desktop
    platform = Column(String(50))    # ios, android, web, windows, mac

    # Device details
    browser = Column(String(100))
    browser_version = Column(String(50))
    os_version = Column(String(50))
    app_version = Column(String(50))

    # Security
    is_trusted = Column(Boolean, default=False)
    push_token = Column(Text)  # For push notifications

    # Activity
    last_active = Column(DateTime)
    first_seen = Column(DateTime)

    # Relationships
    user_location = relationship("UserLocation")

class UserPreference(Base, BaseModel):
    """
    User preferences and settings
    """
    __tablename__ = 'user_preferences'

    user_location_id = Column(ForeignKey('user_locations.id'), nullable=False)

    # Notification preferences
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=False)

    # Display preferences
    language = Column(String(10), default='th')
    timezone = Column(String(50), default='Asia/Bangkok')
    theme = Column(String(20), default='light')  # light, dark, auto
    currency = Column(String(10), default='THB')

    # Feature preferences
    show_tutorials = Column(Boolean, default=True)
    compact_view = Column(Boolean, default=False)
    auto_save = Column(Boolean, default=True)

    # Privacy preferences
    profile_visibility = Column(String(20), default='organization')  # public, organization, private
    share_analytics = Column(Boolean, default=True)

    # Custom preferences
    custom_settings = Column(JSON)

    # Relationships
    user_location = relationship("UserLocation")

class UserInvitation(Base, BaseModel):
    """
    Track user invitations
    """
    __tablename__ = 'user_invitations'

    # Invitation details
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    invited_by_id = Column(ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)

    # Intended user setup
    intended_role = Column(Enum(UserRoleEnum))
    intended_organization_role = Column(BigInteger, ForeignKey('organization_roles.id'))
    intended_platform = Column(Enum(PlatformEnum))

    # Invitation status
    status = Column(String(50), default='pending')  # pending, accepted, expired, cancelled
    invitation_token = Column(String(255), unique=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)

    # User creation result
    created_user_id = Column(ForeignKey('user_locations.id'))

    # Additional data
    custom_message = Column(Text)
    invitation_data = Column(JSON)  # Store additional invitation context

    # Relationships
    invited_by = relationship("UserLocation", foreign_keys=[invited_by_id])
    created_user = relationship("UserLocation", foreign_keys=[created_user_id])


class UserLocationTag(Base, BaseModel):
    """
    Location tags for categorizing and grouping waste origin points within locations.
    Tags can be used to organize collection points, events, or specific areas within a location.
    Tags are organization-level and can be mapped to multiple locations (many-to-many).
    """
    __tablename__ = 'user_location_tags'

    # Basic info
    name = Column(String(255), nullable=False)
    note = Column(Text)

    # Organization ownership (tags belong to organization, can be mapped to any location in that org)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    created_by_id = Column(ForeignKey('user_locations.id'))

    # Legacy single location reference (nullable - use user_locations JSONB array instead)
    # Kept for backward compatibility until migration is complete
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)

    # Many-to-many: JSONB array of user_location IDs this tag is associated with
    user_locations = Column(JSON, default=list)

    # Members (JSONB array of user_location IDs assigned to this tag - users who can use this tag)
    members = Column(JSON, default=list)

    # Event date range (optional - for time-based tags/events)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))

    # Relationships
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])  # Legacy relationship
    organization = relationship("Organization")