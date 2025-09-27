"""
Logs Module
Comprehensive audit trail and logging system for GEPP platform
Tracks admin actions, user activities, and platform changes
"""

# Audit logging models
from .audit_logs import (
    ActionType, ActorType, ResourceType, Severity,
    AuditLog, AdminActionLog, UserActivityLog, SystemLog,
    ComplianceLog, SecurityLog
)

# Platform logging models  
from .platform_logs import (
    PlatformType, ConfigurationType, ChangeImpact, ApprovalStatus,
    PlatformConfigurationLog, FeatureFlagLog, SystemSettingLog,
    IntegrationConfigLog, BusinessRuleLog, PlatformMetricsLog
)

__all__ = [
    # Audit logging enums
    'ActionType', 'ActorType', 'ResourceType', 'Severity',
    
    # Platform logging enums
    'PlatformType', 'ConfigurationType', 'ChangeImpact', 'ApprovalStatus',
    
    # Audit logging models
    'AuditLog', 'AdminActionLog', 'UserActivityLog', 'SystemLog',
    'ComplianceLog', 'SecurityLog',
    
    # Platform logging models
    'PlatformConfigurationLog', 'FeatureFlagLog', 'SystemSettingLog',
    'IntegrationConfigLog', 'BusinessRuleLog', 'PlatformMetricsLog'
]