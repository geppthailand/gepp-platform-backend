"""
Comprehensive audit logging system for GEPP platform
Tracks admin actions, user activities, and system changes across all modules
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class ActionType(enum.Enum):
    """Types of actions being logged"""
    # CRUD Operations
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'
    RESTORE = 'restore'
    
    # Authentication & Authorization
    LOGIN = 'login'
    LOGOUT = 'logout'
    LOGIN_FAILED = 'login_failed'
    PASSWORD_CHANGE = 'password_change'
    PERMISSION_CHANGE = 'permission_change'
    
    # Administrative
    APPROVE = 'approve'
    REJECT = 'reject'
    ACTIVATE = 'activate'
    DEACTIVATE = 'deactivate'
    SUSPEND = 'suspend'
    ARCHIVE = 'archive'
    
    # System
    EXPORT = 'export'
    IMPORT = 'import'
    BACKUP = 'backup'
    CONFIGURATION_CHANGE = 'configuration_change'
    BULK_UPDATE = 'bulk_update'
    
    # Payment & Financial
    PAYMENT_CREATED = 'payment_created'
    PAYMENT_PROCESSED = 'payment_processed'
    PAYMENT_FAILED = 'payment_failed'
    REFUND = 'refund'
    
    # Chat & Communication
    CHAT_STARTED = 'chat_started'
    CHAT_ENDED = 'chat_ended'
    MESSAGE_SENT = 'message_sent'
    MEETING_CREATED = 'meeting_created'

class ActorType(enum.Enum):
    """Type of entity performing the action"""
    USER = 'user'                    # Regular user
    ADMIN = 'admin'                  # Platform administrator
    SYSTEM = 'system'                # Automated system process
    API_CLIENT = 'api_client'        # External API client
    SCHEDULED_JOB = 'scheduled_job'  # Scheduled system job
    AI_AGENT = 'ai_agent'           # AI agent/chatbot

class ResourceType(enum.Enum):
    """Types of resources being acted upon"""
    # User Management
    USER = 'user'
    USER_LOCATION = 'user_location'
    ORGANIZATION = 'organization'
    
    # EPR System
    EPR = 'epr'
    EPR_PAYMENT = 'epr_payment'
    EPR_TARGET = 'epr_target'
    EPR_REPORT = 'epr_report'
    
    # GRI Reporting
    GRI_REPORT = 'gri_report'
    GRI_INDICATOR = 'gri_indicator'
    GRI_DATA = 'gri_data'
    
    # Rewards System
    REWARD = 'reward'
    REWARD_TRANSACTION = 'reward_transaction'
    POINT_BALANCE = 'point_balance'
    
    # Transactions
    TRANSACTION = 'transaction'
    TRANSACTION_ITEM = 'transaction_item'
    TRANSACTION_STATUS = 'transaction_status'
    
    # Subscriptions
    SUBSCRIPTION = 'subscription'
    SUBSCRIPTION_PLAN = 'subscription_plan'
    BILLING = 'billing'
    
    # Chat System
    CHAT = 'chat'
    CHAT_HISTORY = 'chat_history'
    CHAT_MEETING = 'chat_meeting'
    EXPERT = 'expert'
    
    # Knowledge Management
    KM_FILE = 'km_file'
    KM_CHUNK = 'km_chunk'
    KM_SEARCH = 'km_search'
    
    # Platform Settings
    PLATFORM_SETTING = 'platform_setting'
    FEATURE_FLAG = 'feature_flag'
    CONFIGURATION = 'configuration'

class Severity(enum.Enum):
    """Severity level of the logged action"""
    LOW = 'low'                 # Routine operations
    NORMAL = 'normal'           # Standard operations
    HIGH = 'high'              # Important operations
    CRITICAL = 'critical'      # Critical system changes
    EMERGENCY = 'emergency'    # Emergency actions

class AuditLog(Base, BaseModel):
    """Comprehensive audit logging for all platform actions"""
    __tablename__ = 'audit_logs'
    
    # Event identification
    event_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    correlation_id = Column(UUID(as_uuid=True))  # Group related events
    
    # Action details
    action_type = Column(SQLEnum(ActionType), nullable=False)
    resource_type = Column(SQLEnum(ResourceType), nullable=False)
    resource_id = Column(BigInteger)  # ID of the affected resource
    resource_name = Column(String(500))  # Human-readable resource name
    
    # Actor information
    actor_type = Column(SQLEnum(ActorType), nullable=False)
    actor_id = Column(BigInteger)  # User ID, system process ID, etc.
    actor_name = Column(String(255))  # Display name of actor
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Actor's organization
    
    # Context information
    platform = Column(String(50))  # GEPP_360, GEPP_BUSINESS, GEPP_EPR
    module = Column(String(50))     # Module where action occurred
    endpoint = Column(String(255))  # API endpoint or page URL
    method = Column(String(10))     # HTTP method (GET, POST, etc.)
    
    # Session and request context
    session_id = Column(String(255))
    request_id = Column(UUID(as_uuid=True))
    ip_address = Column(String(45))
    user_agent = Column(Text)
    referer = Column(String(500))
    
    # Action details and changes
    description = Column(Text, nullable=False)  # Human-readable description
    details = Column(JSON)  # Additional action details
    before_values = Column(JSON)  # State before change
    after_values = Column(JSON)   # State after change
    changed_fields = Column(JSON)  # List of changed field names
    
    # Result and status
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    error_code = Column(String(100))
    response_status = Column(Integer)  # HTTP status code
    
    # Performance and metrics
    execution_time = Column(Integer)  # Milliseconds
    database_queries = Column(Integer)  # Number of DB queries
    memory_usage = Column(BigInteger)  # Memory used (bytes)
    
    # Risk and security
    severity = Column(SQLEnum(Severity), default=Severity.NORMAL)
    risk_score = Column(Integer)  # Risk assessment score 1-100
    security_flags = Column(JSON)  # Security-related flags
    compliance_relevant = Column(Boolean, default=False)
    
    # Geographic and device info
    country_code = Column(String(2))
    region = Column(String(100))
    city = Column(String(100))
    device_type = Column(String(50))  # desktop, mobile, tablet
    browser = Column(String(100))
    os = Column(String(100))
    
    # Data retention and compliance
    retention_period = Column(Integer)  # Days to retain this log
    archived = Column(Boolean, default=False)
    archive_date = Column(DateTime)
    
    # Relationships
    organization = relationship("Organization")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_audit_logs_timestamp', 'created_date'),
        Index('idx_audit_logs_actor', 'actor_type', 'actor_id'),
        Index('idx_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_logs_organization', 'organization_id'),
        Index('idx_audit_logs_action', 'action_type'),
        Index('idx_audit_logs_platform', 'platform'),
        Index('idx_audit_logs_severity', 'severity'),
        Index('idx_audit_logs_success', 'success'),
        Index('idx_audit_logs_correlation', 'correlation_id'),
    )
    
    def __repr__(self):
        return f"<AuditLog {self.action_type.value} on {self.resource_type.value}:{self.resource_id} by {self.actor_type.value}:{self.actor_id}>"

class AdminActionLog(Base, BaseModel):
    """Specialized logging for administrative actions"""
    __tablename__ = 'admin_action_logs'
    
    # Reference to main audit log
    audit_log_id = Column(BigInteger, ForeignKey('audit_logs.id'), nullable=False)
    
    # Administrative context
    admin_user_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    admin_role = Column(String(100))  # super_admin, platform_admin, org_admin
    permission_level = Column(String(100))  # Permission used for this action
    
    # Action justification
    reason = Column(Text, nullable=False)  # Reason for administrative action
    approval_required = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Impact assessment
    impact_level = Column(String(20))  # low, medium, high, critical
    affected_users_count = Column(Integer, default=0)
    affected_organizations_count = Column(Integer, default=0)
    system_wide_impact = Column(Boolean, default=False)
    
    # Rollback information
    rollback_available = Column(Boolean, default=True)
    rollback_data = Column(JSON)  # Data needed for rollback
    rollback_executed = Column(Boolean, default=False)
    rollback_date = Column(DateTime)
    rollback_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Notifications
    notifications_sent = Column(JSON)  # Who was notified about this action
    escalation_required = Column(Boolean, default=False)
    escalated_to = Column(JSON)  # Who was escalated to
    
    # Relationships
    audit_log = relationship("AuditLog")
    admin_user = relationship("UserLocation", foreign_keys=[admin_user_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    rollback_by = relationship("UserLocation", foreign_keys=[rollback_by_id])

class UserActivityLog(Base, BaseModel):
    """User activity tracking for business operations"""
    __tablename__ = 'user_activity_logs'
    
    # Reference to main audit log
    audit_log_id = Column(BigInteger, ForeignKey('audit_logs.id'), nullable=False)
    
    # User context
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    user_role = Column(String(100))
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Activity classification
    activity_category = Column(String(100))  # epr_management, gri_reporting, transaction, etc.
    business_process = Column(String(100))   # specific business process
    
    # Business context
    financial_impact = Column(Boolean, default=False)
    compliance_related = Column(Boolean, default=False)
    external_reporting = Column(Boolean, default=False)
    
    # Data sensitivity
    contains_pii = Column(Boolean, default=False)
    contains_financial_data = Column(Boolean, default=False)
    data_classification = Column(String(50))  # public, internal, confidential, restricted
    
    # Performance tracking
    user_satisfaction = Column(Integer)  # 1-5 rating if available
    task_completion_time = Column(Integer)  # Seconds to complete task
    errors_encountered = Column(Integer, default=0)
    
    # Relationships
    audit_log = relationship("AuditLog")
    user_location = relationship("UserLocation")
    organization = relationship("Organization")

class SystemLog(Base, BaseModel):
    """System-level logging for automated processes"""
    __tablename__ = 'system_logs'
    
    # Reference to main audit log
    audit_log_id = Column(BigInteger, ForeignKey('audit_logs.id'), nullable=False)
    
    # System process details
    process_name = Column(String(255), nullable=False)
    process_version = Column(String(50))
    job_id = Column(String(255))  # Scheduled job or batch process ID
    
    # Execution context
    server_name = Column(String(100))
    environment = Column(String(50))  # production, staging, development
    deployment_version = Column(String(50))
    
    # Resource usage
    cpu_usage = Column(Integer)  # Percentage
    memory_usage_mb = Column(Integer)
    disk_io_mb = Column(Integer)
    network_io_kb = Column(Integer)
    
    # Batch processing info
    batch_size = Column(Integer)
    records_processed = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    
    # Error handling
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime)
    
    # Dependencies
    dependent_services = Column(JSON)  # External services called
    service_response_times = Column(JSON)  # Response times from dependencies
    
    # Relationships
    audit_log = relationship("AuditLog")

class ComplianceLog(Base, BaseModel):
    """Compliance-specific audit logging"""
    __tablename__ = 'compliance_logs'
    
    # Reference to main audit log
    audit_log_id = Column(BigInteger, ForeignKey('audit_logs.id'), nullable=False)
    
    # Compliance framework
    compliance_framework = Column(String(100))  # GDPR, EPR, GRI, SOX, etc.
    regulation = Column(String(255))  # Specific regulation or standard
    requirement_id = Column(String(100))  # Specific requirement being logged
    
    # Compliance event details
    compliance_action = Column(String(100))  # consent_given, data_deleted, report_submitted
    legal_basis = Column(String(255))  # Legal basis for action
    data_subject_rights = Column(JSON)  # Rights exercised (GDPR)
    
    # Evidence and documentation
    evidence_collected = Column(JSON)  # Evidence supporting compliance
    documentation_links = Column(JSON)  # Links to supporting documents
    
    # Risk and impact
    compliance_risk = Column(String(20))  # low, medium, high, critical
    potential_fine = Column(BigInteger)  # Potential regulatory fine
    breach_notification_required = Column(Boolean, default=False)
    
    # Review and approval
    reviewed_by_legal = Column(Boolean, default=False)
    legal_reviewer_id = Column(BigInteger, ForeignKey('user_locations.id'))
    legal_review_date = Column(DateTime)
    legal_notes = Column(Text)
    
    # Retention requirements
    legal_hold = Column(Boolean, default=False)
    minimum_retention_years = Column(Integer)
    destruction_date = Column(DateTime)
    
    # Relationships
    audit_log = relationship("AuditLog")
    legal_reviewer = relationship("UserLocation")

class SecurityLog(Base, BaseModel):
    """Security-focused audit logging"""
    __tablename__ = 'security_logs'
    
    # Reference to main audit log
    audit_log_id = Column(BigInteger, ForeignKey('audit_logs.id'), nullable=False)
    
    # Security classification
    security_event_type = Column(String(100))  # authentication, authorization, data_access
    threat_level = Column(String(20))  # low, medium, high, critical
    security_category = Column(String(100))  # access_control, data_protection, incident
    
    # Authentication details
    auth_method = Column(String(50))  # password, mfa, sso, api_key
    auth_provider = Column(String(100))  # internal, google, microsoft
    mfa_used = Column(Boolean, default=False)
    
    # Access patterns
    unusual_access = Column(Boolean, default=False)
    off_hours_access = Column(Boolean, default=False)
    geographic_anomaly = Column(Boolean, default=False)
    device_anomaly = Column(Boolean, default=False)
    
    # Data access
    sensitive_data_accessed = Column(Boolean, default=False)
    data_export = Column(Boolean, default=False)
    data_volume_bytes = Column(BigInteger)
    
    # Security controls
    permission_elevation = Column(Boolean, default=False)
    bypass_attempted = Column(Boolean, default=False)
    security_controls_applied = Column(JSON)
    
    # Incident response
    incident_created = Column(Boolean, default=False)
    incident_id = Column(String(100))
    response_team_notified = Column(Boolean, default=False)
    
    # Forensic data
    request_headers = Column(JSON)
    request_body_hash = Column(String(255))  # Hash of request body for forensics
    session_tokens = Column(JSON)  # Hashed session tokens
    
    # Relationships
    audit_log = relationship("AuditLog")