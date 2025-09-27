"""
Rewards management and analytics models
Administrative tools, analytics, and performance tracking
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel

class CampaignType(enum.Enum):
    """Campaign types"""
    SEASONAL = 'seasonal'           # Holiday/seasonal campaigns
    ONBOARDING = 'onboarding'      # New user onboarding
    RETENTION = 'retention'        # User retention campaigns
    ENGAGEMENT = 'engagement'      # Increase engagement
    LOYALTY = 'loyalty'            # Loyalty building
    PROMOTION = 'promotion'        # Product/service promotion
    MILESTONE = 'milestone'        # Milestone celebrations

class CampaignStatus(enum.Enum):
    """Campaign status"""
    DRAFT = 'draft'
    SCHEDULED = 'scheduled'
    ACTIVE = 'active'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'

class NotificationType(enum.Enum):
    """Notification types"""
    POINTS_EARNED = 'points_earned'
    POINTS_EXPIRING = 'points_expiring'
    REWARD_AVAILABLE = 'reward_available'
    REDEMPTION_APPROVED = 'redemption_approved'
    REDEMPTION_SHIPPED = 'redemption_shipped'
    REDEMPTION_DELIVERED = 'redemption_delivered'
    TIER_UPGRADED = 'tier_upgraded'
    GOAL_ACHIEVED = 'goal_achieved'

class RewardCampaign(Base, BaseModel):
    """Reward campaigns and marketing initiatives"""
    __tablename__ = 'reward_campaigns'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Campaign details
    campaign_name = Column(String(255), nullable=False)
    campaign_code = Column(String(50), unique=True)
    campaign_type = Column(SQLEnum(CampaignType), nullable=False)
    
    # Description and messaging
    description = Column(Text)
    short_description = Column(String(500))
    marketing_message = Column(Text)
    
    # Timeline
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # Target audience
    target_user_segments = Column(JSON)  # User segments to target
    target_user_tiers = Column(JSON)     # User tiers
    target_locations = Column(JSON)      # Geographic targeting
    
    # Campaign goals
    target_participation = Column(BigInteger)      # Target number of participants
    target_redemptions = Column(BigInteger)        # Target redemptions
    target_points_distributed = Column(DECIMAL(15, 2))
    
    # Incentives
    bonus_point_multiplier = Column(DECIMAL(3, 2))  # Points multiplier during campaign
    special_rewards = Column(JSON)                  # Special campaign rewards
    exclusive_offers = Column(JSON)                 # Exclusive offers
    
    # Budget
    allocated_budget = Column(DECIMAL(15, 2))
    spent_budget = Column(DECIMAL(15, 2), default=0)
    cost_per_participation = Column(DECIMAL(10, 2))
    
    # Performance tracking
    total_participants = Column(BigInteger, default=0)
    total_redemptions = Column(BigInteger, default=0)
    total_points_awarded = Column(DECIMAL(15, 2), default=0)
    conversion_rate = Column(DECIMAL(5, 2))
    
    # Status
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)
    
    # Creative assets
    banner_image_url = Column(String(500))
    featured_image_url = Column(String(500))
    email_template = Column(Text)
    
    # A/B Testing
    is_ab_test = Column(Boolean, default=False)
    test_variant = Column(String(50))  # A, B, etc.
    test_traffic_split = Column(DECIMAL(5, 2))  # % of traffic for this variant
    
    # Automation rules
    auto_enrollment_rules = Column(JSON)    # Rules for auto-enrolling users
    trigger_conditions = Column(JSON)       # Trigger conditions
    
    # Analysis
    performance_analysis = Column(JSON)     # Campaign performance analysis
    lessons_learned = Column(Text)
    
    # Relationships
    organization = relationship("Organization")
    
    # Campaign participants
    participants = relationship("CampaignParticipant", back_populates="campaign")

class CampaignParticipant(Base, BaseModel):
    """Users participating in reward campaigns"""
    __tablename__ = 'campaign_participants'
    
    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Participation details
    enrollment_date = Column(DateTime, nullable=False)
    enrollment_method = Column(String(50))  # auto, manual, invited
    
    # Progress tracking
    points_earned_in_campaign = Column(DECIMAL(10, 2), default=0)
    redemptions_in_campaign = Column(BigInteger, default=0)
    goals_achieved = Column(JSON)  # Campaign-specific goals achieved
    
    # Engagement metrics
    campaign_interactions = Column(BigInteger, default=0)  # Email opens, clicks, etc.
    last_interaction_date = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    completion_status = Column(String(50))  # incomplete, completed, exceeded
    completion_date = Column(DateTime)
    
    # Rewards received
    bonus_points_received = Column(DECIMAL(10, 2), default=0)
    special_rewards_received = Column(JSON)
    
    # Relationships
    campaign = relationship("RewardCampaign", back_populates="participants")
    user_location = relationship("UserLocation")

class RewardAnalytics(Base, BaseModel):
    """Analytics and insights for reward program"""
    __tablename__ = 'reward_analytics'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Analysis period
    analysis_date = Column(DateTime, nullable=False)
    period_type = Column(String(50))  # daily, weekly, monthly, quarterly, yearly
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # User engagement metrics
    active_users = Column(BigInteger)
    new_users = Column(BigInteger)
    returning_users = Column(BigInteger)
    churned_users = Column(BigInteger)
    
    # Points metrics
    total_points_earned = Column(DECIMAL(15, 2))
    total_points_redeemed = Column(DECIMAL(15, 2))
    total_points_expired = Column(DECIMAL(15, 2))
    average_points_per_user = Column(DECIMAL(10, 2))
    
    # Transaction metrics
    total_transactions = Column(BigInteger)
    transactions_with_points = Column(BigInteger)
    average_points_per_transaction = Column(DECIMAL(10, 2))
    
    # Redemption metrics
    total_redemptions = Column(BigInteger)
    redemption_rate = Column(DECIMAL(5, 2))  # % of users who redeemed
    average_redemption_value = Column(DECIMAL(10, 2))
    fulfillment_success_rate = Column(DECIMAL(5, 2))
    
    # Popular items
    top_rewards = Column(JSON)      # Most redeemed rewards
    top_categories = Column(JSON)   # Most popular categories
    trending_rewards = Column(JSON) # Trending rewards
    
    # User behavior
    user_segments = Column(JSON)    # User segmentation analysis
    tier_distribution = Column(JSON) # Distribution across tiers
    engagement_patterns = Column(JSON) # Usage patterns
    
    # Financial metrics
    total_reward_cost = Column(DECIMAL(15, 2))
    cost_per_user = Column(DECIMAL(10, 2))
    roi_percentage = Column(DECIMAL(5, 2))
    
    # Performance indicators
    program_health_score = Column(DECIMAL(5, 2))  # Overall health score
    user_satisfaction_score = Column(DECIMAL(3, 2))
    nps_score = Column(DECIMAL(5, 2))  # Net Promoter Score
    
    # Predictions
    predicted_next_period = Column(JSON)  # Predictions for next period
    recommendations = Column(JSON)        # System recommendations
    
    # Comparison data
    vs_previous_period = Column(JSON)     # Comparison with previous period
    vs_industry_benchmark = Column(JSON)  # Industry comparison
    
    # Relationships
    organization = relationship("Organization")

class RewardNotification(Base, BaseModel):
    """Notification system for reward program"""
    __tablename__ = 'reward_notifications'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Notification details
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Related entities
    reward_id = Column(BigInteger, ForeignKey('rewards.id'))
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'))
    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'))
    
    # Delivery channels
    send_email = Column(Boolean, default=True)
    send_sms = Column(Boolean, default=False)
    send_push = Column(Boolean, default=True)
    send_in_app = Column(Boolean, default=True)
    
    # Delivery status
    email_sent = Column(Boolean, default=False)
    email_opened = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    push_sent = Column(Boolean, default=False)
    in_app_read = Column(Boolean, default=False)
    
    # Timing
    scheduled_send_date = Column(DateTime)
    actual_send_date = Column(DateTime)
    
    # Engagement
    clicked = Column(Boolean, default=False)
    click_date = Column(DateTime)
    action_taken = Column(String(100))  # Action user took after notification
    
    # Priority
    priority = Column(String(50), default='normal')  # low, normal, high, urgent
    
    # Personalization
    personalization_data = Column(JSON)  # Data used for personalization
    
    # Template
    template_id = Column(String(100))
    template_variables = Column(JSON)
    
    # Status
    status = Column(String(50), default='pending')  # pending, sent, failed, cancelled
    error_message = Column(Text)
    
    # Relationships
    organization = relationship("Organization")
    user_location = relationship("UserLocation")
    reward = relationship("Reward")

class RewardConfiguration(Base, BaseModel):
    """Configuration settings for reward program"""
    __tablename__ = 'reward_configurations'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # General settings
    program_name = Column(String(255), default='Rewards Program')
    program_description = Column(Text)
    currency_name = Column(String(50), default='Points')  # What to call points
    currency_symbol = Column(String(10), default='pts')
    
    # Points settings
    points_decimal_places = Column(BigInteger, default=0)
    minimum_redemption_points = Column(DECIMAL(10, 2), default=100)
    points_expiry_months = Column(BigInteger, default=12)
    
    # Tier system
    enable_tiers = Column(Boolean, default=True)
    tier_reset_frequency = Column(String(50), default='annual')  # annual, never
    
    # Approval settings
    auto_approve_under_points = Column(DECIMAL(10, 2), default=1000)
    require_approval_over_points = Column(DECIMAL(10, 2), default=5000)
    
    # Notification settings
    enable_email_notifications = Column(Boolean, default=True)
    enable_sms_notifications = Column(Boolean, default=False)
    enable_push_notifications = Column(Boolean, default=True)
    
    # Expiry reminders
    expiry_reminder_days = Column(JSON, default=[30, 14, 7, 1])  # Days before expiry
    
    # Redemption settings
    allow_partial_redemption = Column(Boolean, default=True)
    redemption_cooldown_hours = Column(BigInteger, default=0)
    max_pending_redemptions = Column(BigInteger, default=5)
    
    # Security settings
    fraud_detection_enabled = Column(Boolean, default=True)
    max_daily_redemptions = Column(BigInteger, default=10)
    velocity_check_enabled = Column(Boolean, default=True)
    
    # Integration settings
    api_webhooks = Column(JSON)  # Webhook URLs for events
    external_integrations = Column(JSON)  # External system configurations
    
    # Customization
    theme_colors = Column(JSON)      # UI theme colors
    logo_url = Column(String(500))   # Program logo
    custom_css = Column(Text)        # Custom styling
    
    # Terms and conditions
    terms_url = Column(String(500))
    privacy_policy_url = Column(String(500))
    terms_last_updated = Column(DateTime)
    
    # Analytics
    analytics_enabled = Column(Boolean, default=True)
    data_retention_months = Column(BigInteger, default=36)
    
    # Relationships
    organization = relationship("Organization")

class RewardAuditLog(Base, BaseModel):
    """Audit log for reward system activities"""
    __tablename__ = 'reward_audit_logs'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Event details
    event_type = Column(String(100), nullable=False)  # points_earned, redemption_created, etc.
    event_description = Column(String(500))
    
    # Actor
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    system_actor = Column(String(100))  # For system-generated events
    
    # Target entities
    target_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    reward_id = Column(BigInteger, ForeignKey('rewards.id'))
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'))
    
    # Event data
    event_data = Column(JSON)  # Detailed event data
    
    # Context
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    session_id = Column(String(255))
    
    # Values involved
    points_before = Column(DECIMAL(15, 2))
    points_after = Column(DECIMAL(15, 2))
    points_changed = Column(DECIMAL(15, 2))
    
    # Risk assessment
    risk_score = Column(DECIMAL(5, 2))  # 0-100 risk score
    fraud_flags = Column(JSON)          # Fraud detection flags
    
    # Status
    is_suspicious = Column(Boolean, default=False)
    requires_review = Column(Boolean, default=False)
    reviewed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    review_date = Column(DateTime)
    review_notes = Column(Text)
    
    # Relationships
    organization = relationship("Organization")
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    target_user = relationship("UserLocation", foreign_keys=[target_user_id])
    reviewed_by = relationship("UserLocation", foreign_keys=[reviewed_by_id])

class RewardIntegration(Base, BaseModel):
    """External system integrations for rewards"""
    __tablename__ = 'reward_integrations'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Integration details
    integration_name = Column(String(255), nullable=False)
    integration_type = Column(String(100))  # fulfillment, payment, crm, email
    provider_name = Column(String(255))
    
    # Configuration
    api_endpoint = Column(String(500))
    api_key = Column(String(500))  # Encrypted
    api_secret = Column(String(500))  # Encrypted
    configuration = Column(JSON)  # Provider-specific configuration
    
    # Authentication
    auth_method = Column(String(50))  # api_key, oauth, basic
    oauth_tokens = Column(JSON)  # OAuth tokens if applicable
    
    # Sync settings
    sync_enabled = Column(Boolean, default=True)
    sync_frequency = Column(String(50), default='real_time')
    last_sync = Column(DateTime)
    next_sync = Column(DateTime)
    
    # Error handling
    error_count = Column(BigInteger, default=0)
    last_error = Column(Text)
    max_retries = Column(BigInteger, default=3)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)
    
    # Usage tracking
    total_requests = Column(BigInteger, default=0)
    successful_requests = Column(BigInteger, default=0)
    failed_requests = Column(BigInteger, default=0)
    
    # Relationships
    organization = relationship("Organization")