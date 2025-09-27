"""
Platform-specific logging for GEPP system configuration and settings
Tracks changes to platform settings, feature flags, and system configurations
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class PlatformType(enum.Enum):
    """GEPP Platform types"""
    GEPP_360 = 'GEPP_360'           # Comprehensive waste management platform
    GEPP_BUSINESS = 'GEPP_BUSINESS' # Business management and analytics
    GEPP_EPR = 'GEPP_EPR'          # Extended Producer Responsibility
    GEPP_ADMIN = 'GEPP_ADMIN'      # Administrative platform

class ConfigurationType(enum.Enum):
    """Types of platform configurations"""
    SYSTEM_SETTING = 'system_setting'       # Core system settings
    FEATURE_FLAG = 'feature_flag'           # Feature toggles
    BUSINESS_RULE = 'business_rule'         # Business logic configuration
    INTEGRATION_CONFIG = 'integration_config' # Third-party integrations
    UI_CONFIGURATION = 'ui_configuration'   # User interface settings
    SECURITY_POLICY = 'security_policy'     # Security configurations
    NOTIFICATION_RULE = 'notification_rule' # Notification settings
    WORKFLOW_CONFIG = 'workflow_config'     # Workflow configurations
    REPORTING_CONFIG = 'reporting_config'   # Reporting settings
    API_CONFIGURATION = 'api_configuration' # API settings

class ChangeImpact(enum.Enum):
    """Impact level of configuration changes"""
    MINIMAL = 'minimal'         # No user impact
    LOW = 'low'                # Minor user experience changes
    MEDIUM = 'medium'          # Noticeable functionality changes
    HIGH = 'high'             # Significant feature changes
    CRITICAL = 'critical'     # System-wide critical changes

class ApprovalStatus(enum.Enum):
    """Approval status for configuration changes"""
    PENDING = 'pending'         # Awaiting approval
    APPROVED = 'approved'       # Approved for deployment
    REJECTED = 'rejected'       # Rejected
    CANCELLED = 'cancelled'     # Cancelled by requester
    DEPLOYED = 'deployed'       # Successfully deployed
    ROLLED_BACK = 'rolled_back' # Rolled back due to issues

class PlatformConfigurationLog(Base, BaseModel):
    """Logging for platform configuration changes"""
    __tablename__ = 'platform_configuration_logs'
    
    # Configuration identification
    config_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    
    # Platform and configuration details
    platform = Column(SQLEnum(PlatformType), nullable=False)
    configuration_type = Column(SQLEnum(ConfigurationType), nullable=False)
    configuration_name = Column(String(255), nullable=False)
    configuration_path = Column(String(500))  # Hierarchical path to setting
    
    # Change details
    action = Column(String(50), nullable=False)  # create, update, delete, enable, disable
    previous_value = Column(JSON)  # Previous configuration value
    new_value = Column(JSON)      # New configuration value
    change_description = Column(Text, nullable=False)
    
    # Actor information
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    change_reason = Column(Text)  # Justification for change
    ticket_reference = Column(String(100))  # JIRA/ticket reference
    
    # Impact assessment
    impact_level = Column(SQLEnum(ChangeImpact), default=ChangeImpact.LOW)
    affected_features = Column(JSON)  # List of features affected
    affected_users_estimate = Column(Integer, default=0)
    downtime_required = Column(Boolean, default=False)
    estimated_downtime_minutes = Column(Integer)
    
    # Approval workflow
    approval_required = Column(Boolean, default=False)
    approval_status = Column(SQLEnum(ApprovalStatus), default=ApprovalStatus.PENDING)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Deployment tracking
    deployment_scheduled = Column(DateTime)
    deployment_executed = Column(DateTime)
    deployment_method = Column(String(100))  # manual, automated, ci_cd
    deployment_version = Column(String(50))
    
    # Rollback information
    rollback_available = Column(Boolean, default=True)
    rollback_plan = Column(Text)
    rollback_executed = Column(Boolean, default=False)
    rollback_date = Column(DateTime)
    rollback_reason = Column(Text)
    rollback_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Validation and testing
    pre_deployment_testing = Column(Boolean, default=False)
    test_results = Column(JSON)
    post_deployment_validation = Column(Boolean, default=False)
    validation_results = Column(JSON)
    
    # Environment tracking
    environment = Column(String(50), default='production')  # dev, staging, production
    server_instances = Column(JSON)  # Server instances affected
    
    # Success and error tracking
    deployment_successful = Column(Boolean, default=True)
    error_message = Column(Text)
    error_details = Column(JSON)
    
    # Relationships
    changed_by = relationship("UserLocation", foreign_keys=[changed_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    rollback_by = relationship("UserLocation", foreign_keys=[rollback_by_id])

class FeatureFlagLog(Base, BaseModel):
    """Detailed logging for feature flag changes"""
    __tablename__ = 'feature_flag_logs'
    
    # Feature flag identification
    flag_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    flag_name = Column(String(255), nullable=False)
    flag_key = Column(String(255), nullable=False)  # Technical key for the flag
    
    # Platform and environment
    platform = Column(SQLEnum(PlatformType), nullable=False)
    environment = Column(String(50), nullable=False)
    
    # Flag configuration
    flag_type = Column(String(50))  # boolean, string, number, json
    previous_state = Column(JSON)   # Previous flag state
    new_state = Column(JSON)        # New flag state
    default_value = Column(JSON)    # Default value for new users
    
    # Targeting and rollout
    targeting_rules = Column(JSON)  # User/org targeting rules
    rollout_percentage = Column(DECIMAL(5, 2))  # Percentage rollout
    user_segments = Column(JSON)    # Specific user segments
    organization_filters = Column(JSON)  # Organization-based filters
    
    # Change tracking
    action = Column(String(50), nullable=False)  # create, update, enable, disable, delete
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    change_reason = Column(Text, nullable=False)
    
    # Impact and monitoring
    estimated_affected_users = Column(Integer, default=0)
    actual_affected_users = Column(Integer)
    performance_impact = Column(JSON)  # Performance metrics
    error_rate_change = Column(DECIMAL(5, 2))
    
    # A/B Testing integration
    experiment_id = Column(String(255))
    variant_name = Column(String(100))
    control_group_size = Column(Integer)
    treatment_group_size = Column(Integer)
    
    # Success metrics
    success_metrics = Column(JSON)  # Metrics to track
    baseline_metrics = Column(JSON) # Pre-change metrics
    post_change_metrics = Column(JSON) # Post-change metrics
    
    # Relationships
    changed_by = relationship("UserLocation")

class SystemSettingLog(Base, BaseModel):
    """Logging for system-level settings changes"""
    __tablename__ = 'system_setting_logs'
    
    # Setting identification
    setting_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    setting_category = Column(String(100), nullable=False)  # database, cache, security, etc.
    setting_name = Column(String(255), nullable=False)
    setting_path = Column(String(500))  # Full path to setting
    
    # Change details
    action = Column(String(50), nullable=False)
    previous_value = Column(Text)
    new_value = Column(Text)
    value_type = Column(String(50))  # string, number, boolean, json
    is_sensitive = Column(Boolean, default=False)  # Contains sensitive data
    
    # Context
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    change_context = Column(String(255))  # maintenance, incident, feature_release
    urgency = Column(String(50), default='normal')  # low, normal, high, emergency
    
    # System impact
    requires_restart = Column(Boolean, default=False)
    restart_performed = Column(Boolean, default=False)
    restart_timestamp = Column(DateTime)
    
    # Performance impact
    cpu_impact = Column(String(50))     # none, low, medium, high
    memory_impact = Column(String(50))  # none, low, medium, high
    disk_impact = Column(String(50))    # none, low, medium, high
    network_impact = Column(String(50)) # none, low, medium, high
    
    # Validation
    setting_validated = Column(Boolean, default=False)
    validation_method = Column(String(100))
    validation_results = Column(JSON)
    
    # Backup and recovery
    backup_created = Column(Boolean, default=False)
    backup_location = Column(String(500))
    recovery_tested = Column(Boolean, default=False)
    
    # Relationships
    changed_by = relationship("UserLocation")

class IntegrationConfigLog(Base, BaseModel):
    """Logging for third-party integration configurations"""
    __tablename__ = 'integration_config_logs'
    
    # Integration identification
    integration_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    integration_name = Column(String(255), nullable=False)
    integration_type = Column(String(100))  # payment, notification, analytics, etc.
    provider_name = Column(String(255))     # Stripe, SendGrid, Google Analytics
    
    # Configuration change
    config_section = Column(String(255))    # API keys, webhooks, settings
    action = Column(String(50), nullable=False)
    previous_config = Column(JSON)
    new_config = Column(JSON)
    sensitive_data_changed = Column(Boolean, default=False)
    
    # Change context
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    change_reason = Column(Text, nullable=False)
    maintenance_window = Column(Boolean, default=False)
    
    # Service details
    service_version = Column(String(50))
    api_version = Column(String(50))
    endpoint_urls = Column(JSON)
    authentication_method = Column(String(100))
    
    # Testing and validation
    connection_tested = Column(Boolean, default=False)
    test_timestamp = Column(DateTime)
    test_results = Column(JSON)
    webhook_validation = Column(Boolean, default=False)
    
    # Monitoring
    health_check_enabled = Column(Boolean, default=True)
    monitoring_alerts = Column(JSON)
    sla_requirements = Column(JSON)
    
    # Security
    encryption_enabled = Column(Boolean, default=True)
    certificate_updated = Column(Boolean, default=False)
    security_scan_passed = Column(Boolean, default=False)
    
    # Relationships
    changed_by = relationship("UserLocation")

class BusinessRuleLog(Base, BaseModel):
    """Logging for business rule and logic changes"""
    __tablename__ = 'business_rule_logs'
    
    # Rule identification
    rule_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    rule_name = Column(String(255), nullable=False)
    rule_category = Column(String(100))  # pricing, validation, workflow, approval
    business_domain = Column(String(100)) # epr, gri, rewards, transactions
    
    # Rule definition
    rule_type = Column(String(50))       # calculation, validation, routing, approval
    rule_expression = Column(Text)       # Rule logic/expression
    rule_priority = Column(Integer, default=1)
    rule_active = Column(Boolean, default=True)
    
    # Change tracking
    action = Column(String(50), nullable=False)
    previous_rule = Column(JSON)
    new_rule = Column(JSON)
    version = Column(String(50))
    
    # Change context
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    business_justification = Column(Text, nullable=False)
    stakeholder_approval = Column(JSON)  # List of approving stakeholders
    
    # Impact analysis
    affected_processes = Column(JSON)
    affected_calculations = Column(JSON)
    financial_impact = Column(DECIMAL(15, 4))
    compliance_impact = Column(Text)
    
    # Testing
    test_scenarios = Column(JSON)
    test_results = Column(JSON)
    regression_testing = Column(Boolean, default=False)
    user_acceptance_testing = Column(Boolean, default=False)
    
    # Deployment
    effective_date = Column(DateTime)
    grandfathering_rules = Column(JSON)  # Rules for existing data
    transition_period = Column(Integer)  # Days
    
    # Monitoring
    performance_monitoring = Column(Boolean, default=True)
    error_monitoring = Column(Boolean, default=True)
    business_metrics = Column(JSON)
    
    # Relationships
    changed_by = relationship("UserLocation")

class PlatformMetricsLog(Base, BaseModel):
    """System performance and health metrics logging"""
    __tablename__ = 'platform_metrics_logs'
    
    # Metrics identification
    metrics_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    platform = Column(SQLEnum(PlatformType), nullable=False)
    environment = Column(String(50), nullable=False)
    
    # Performance metrics
    response_time_avg = Column(DECIMAL(8, 3))   # Average response time
    response_time_p95 = Column(DECIMAL(8, 3))   # 95th percentile response time
    response_time_p99 = Column(DECIMAL(8, 3))   # 99th percentile response time
    throughput_rpm = Column(Integer)            # Requests per minute
    error_rate = Column(DECIMAL(5, 2))          # Error rate percentage
    
    # System resources
    cpu_usage_avg = Column(DECIMAL(5, 2))       # Average CPU usage
    cpu_usage_peak = Column(DECIMAL(5, 2))      # Peak CPU usage
    memory_usage_avg = Column(DECIMAL(5, 2))    # Average memory usage
    memory_usage_peak = Column(DECIMAL(5, 2))   # Peak memory usage
    disk_usage = Column(DECIMAL(5, 2))          # Disk usage percentage
    disk_io_rate = Column(Integer)              # Disk I/O operations per second
    
    # Database performance
    db_connection_count = Column(Integer)
    db_query_time_avg = Column(DECIMAL(8, 3))
    db_slow_queries = Column(Integer)
    db_deadlocks = Column(Integer)
    db_cache_hit_rate = Column(DECIMAL(5, 2))
    
    # Application metrics
    active_users = Column(Integer)
    concurrent_sessions = Column(Integer)
    api_calls_count = Column(Integer)
    failed_jobs = Column(Integer)
    cache_hit_rate = Column(DECIMAL(5, 2))
    
    # Business metrics
    daily_transactions = Column(Integer)
    total_epr_payments = Column(DECIMAL(15, 4))
    active_chats = Column(Integer)
    documents_processed = Column(Integer)
    km_searches = Column(Integer)
    
    # Alerts and incidents
    alerts_triggered = Column(Integer)
    incidents_created = Column(Integer)
    sla_breaches = Column(Integer)
    uptime_percentage = Column(DECIMAL(5, 4))
    
    # External dependencies
    third_party_response_times = Column(JSON)
    third_party_error_rates = Column(JSON)
    cdn_cache_hit_rate = Column(DECIMAL(5, 2))
    
    # Collection metadata
    collection_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    collection_duration = Column(Integer)  # Seconds to collect metrics
    data_completeness = Column(DECIMAL(5, 2))  # Percentage of expected data collected