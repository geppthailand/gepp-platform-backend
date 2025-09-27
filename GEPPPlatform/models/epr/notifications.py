"""
EPR Notifications and communication models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

class EprNotificationActionType(Base, BaseModel):
    """Types of actions that can trigger EPR notifications"""
    __tablename__ = 'epr_notifications_action_type'
    
    # Action type identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Category and classification
    category = Column(String(100))  # system, user, transaction, compliance, etc.
    priority = Column(String(50), default='normal')  # low, normal, high, urgent
    
    # Trigger conditions
    trigger_events = Column(JSON)  # Events that trigger this action type
    trigger_conditions = Column(JSON)  # Conditions that must be met
    
    # Notification settings
    default_channels = Column(JSON)  # Default notification channels (email, sms, push)
    template_id = Column(String(100))  # Message template identifier
    
    # Timing and frequency
    immediate_notification = Column(Boolean, default=True)
    delay_minutes = Column(BigInteger, default=0)  # Delay before sending
    max_frequency_per_day = Column(BigInteger)  # Rate limiting
    
    # Audience targeting
    default_recipients = Column(JSON)  # Default recipient roles/groups
    escalation_rules = Column(JSON)  # Escalation rules for high priority
    
    # Content settings
    include_attachments = Column(Boolean, default=False)
    include_data_snapshot = Column(Boolean, default=False)
    personalization_fields = Column(JSON)  # Fields for message personalization
    
    # Compliance and audit
    requires_read_receipt = Column(Boolean, default=False)
    retention_days = Column(BigInteger, default=365)
    is_regulatory_required = Column(Boolean, default=False)
    
    # Status and configuration
    is_active = Column(Boolean, default=True)
    is_system_critical = Column(Boolean, default=False)
    
    # Localization
    supported_languages = Column(JSON)  # Languages supported for this action type
    
    # Usage tracking
    total_notifications = Column(BigInteger, default=0)
    last_used_date = Column(DateTime)
    
    # Configuration metadata
    extra_metadata = Column(JSON)

class EprNotification(Base, BaseModel):
    """Individual EPR notification instances"""
    __tablename__ = 'epr_notifications'
    
    # Notification identification
    notification_id = Column(String(100), unique=True, nullable=False)
    action_type_id = Column(BigInteger, ForeignKey('epr_notifications_action_type.id'), nullable=False)
    
    # Recipients
    recipient_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    recipient_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    recipient_email = Column(String(255))
    recipient_phone = Column(String(50))
    
    # Sender information
    sender_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    sender_system = Column(String(100))  # System component that sent notification
    
    # Content
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    html_content = Column(Text)  # Rich HTML content
    
    # Delivery channels
    delivery_channels = Column(JSON)  # Channels used (email, sms, push, in_app)
    preferred_channel = Column(String(50))
    
    # Priority and urgency
    priority = Column(String(50), default='normal')
    is_urgent = Column(Boolean, default=False)
    requires_acknowledgment = Column(Boolean, default=False)
    
    # Related entities
    related_project_id = Column(BigInteger, ForeignKey('epr_project.id'))
    related_transaction_id = Column(BigInteger, ForeignKey('transactions.id'))
    related_payment_id = Column(BigInteger, ForeignKey('epr_payment_transactions.id'))
    related_organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    
    # Timing
    scheduled_send_time = Column(DateTime)
    actual_send_time = Column(DateTime)
    expiry_time = Column(DateTime)
    
    # Delivery status
    status = Column(String(50), default='pending')  # pending, sent, delivered, failed, cancelled
    delivery_attempts = Column(BigInteger, default=0)
    last_delivery_attempt = Column(DateTime)
    delivery_error = Column(Text)
    
    # Channel-specific delivery status
    email_status = Column(String(50))  # sent, delivered, opened, bounced
    sms_status = Column(String(50))
    push_status = Column(String(50))
    in_app_status = Column(String(50))
    
    # Engagement tracking
    is_read = Column(Boolean, default=False)
    read_time = Column(DateTime)
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_time = Column(DateTime)
    acknowledged_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Response tracking
    has_response = Column(Boolean, default=False)
    response_time = Column(DateTime)
    response_content = Column(Text)
    
    # Links and actions
    action_links = Column(JSON)  # Links for user actions
    click_tracking = Column(JSON)  # Click tracking data
    
    # Personalization and context
    personalization_data = Column(JSON)  # Data used for personalization
    context_data = Column(JSON)  # Additional context information
    
    # Attachments
    attachments = Column(JSON)  # Array of attachment URLs/references
    
    # Language and localization
    language = Column(String(10), default='th')
    locale = Column(String(15), default='TH')
    
    # Retry and escalation
    max_retries = Column(BigInteger, default=3)
    retry_count = Column(BigInteger, default=0)
    next_retry_time = Column(DateTime)
    escalated = Column(Boolean, default=False)
    escalated_time = Column(DateTime)
    
    # Analytics and reporting
    tracking_data = Column(JSON)  # Analytics tracking information
    campaign_id = Column(String(100))  # For grouped notifications
    
    # Additional metadata
    extra_metadata = Column(JSON)
    
    # Relationships
    action_type = relationship("EprNotificationActionType")
    recipient_user = relationship("UserLocation", foreign_keys=[recipient_user_id])
    recipient_organization = relationship("EprOrganization", foreign_keys=[recipient_organization_id])
    sender_user = relationship("UserLocation", foreign_keys=[sender_user_id])
    related_project = relationship("EprProject")
    related_transaction = relationship("Transaction")
    related_payment = relationship("EprPaymentTransaction")
    related_organization = relationship("EprOrganization", foreign_keys=[related_organization_id])
    acknowledged_by = relationship("UserLocation", foreign_keys=[acknowledged_by_id])