"""
Main models package - Imports all models from cores, users, subscriptions, and transactions modules
"""

# Import base configuration
from .base import Base, BaseModel, PlatformEnum

# Import all core models
from .cores import *

# Import all user models  
from .users import *

# Import all subscription models
from .subscriptions import *

# Import all transaction models
from .transactions import *

# Import all EPR models
from .epr import *

# Import all EPR payment models
from .epr_payments import *

# Import all GRI models
from .gri import *

# Import all rewards models
from .rewards import *

# Import all KM models
from .km import *

# Import all chats models
from .chats import *

# Import all logs models
from .logs import *

# Import IoT models
from .iot import *

# Import audit rules model
from .audit_rules import AuditRule, RuleType

# Add input_channels relationship to UserLocation
from sqlalchemy.orm import relationship
from .users.user_location import UserLocation
from .users.user_related import UserInputChannel

UserLocation.input_channels = relationship("UserInputChannel", back_populates="user_location")

__all__ = [
    # Base
    'Base', 'BaseModel', 'PlatformEnum',
    
    # Core models
    'LocationCountry', 'LocationRegion', 'LocationProvince',
    'LocationDistrict', 'LocationSubdistrict',
    'Bank', 'Currency', 'Locale', 'Material', 'MainMaterial', 'MaterialCategory',
    'MaterialTag', 'MaterialTagGroup',
    'Nationality', 'PhoneNumberCountryCode',
    'Permission', 'PermissionType',
    'SystemRole', 'SystemPermission',
    'Translation',
    
    # Subscription models
    'Organization', 'OrganizationInfo', 'SubscriptionPackage', 'SubscriptionPermission',
    
    # User models
    'UserLocation', 'user_subusers',
    'UserBank', 'UserSubscription', 'UserInputChannel',
    
    # Transaction models
    'Transaction', 'TransactionStatus', 'TransactionPriority',
    'TransactionRecord',
    
    # EPR models
    'EprOrganization', 'EprOrganizationMaterialGroup', 'EprOrganizationUser',
    'EprBrand', 'EprProduct', 'EprProject', 'EprProjectFile', 'EprProjectUser',
    'EprProjectUsersLog', 'EprProjectLog',
    'EprPro', 'EprProInfo', 'EprProFile', 'EprProMaterialGroup', 'EprProMaterialGroupUser',
    'EprProMaterialTagGroup', 'EprProMaterialTag', 'EprProMaterial', 'EprProUser',
    'EprAuditorTransactionAssignment', 'EprAuditorTransactionAssignInfoLog',
    'EprRecyclerAuditDoc', 'EprRecyclerAuditPreset', 'EprLogisticAssistantFeeSettings',
    'EprProvinceDistance', 'EprSorterType', 'EprSelfRegistrationUrl', 'EprUserLafInfo',
    'EprNotification', 'EprNotificationActionType',
    
    # EPR Payment models  
    'EprPaymentTransaction', 'EprPaymentTransactionRecord',
    'EprPaymentTransactionImage', 'EprPaymentTransactionType',
    'EprProjectAssistantFeeCalculationMethodType', 'EprProjectUserAssistantFeeSetting',
    'EprProjectUserAssistantFee', 'EprProjectMonthlyActualSpending',
    
    # GRI models
    'GriStandardType', 'GriStandard', 'GriAspect', 'GriIndicator',
    'GriMaterialCategory', 'GriReportingTemplate',
    'ReportingPeriod', 'GriReport', 'GriReportData', 'GriReportSnapshot',
    'GoalStatus', 'GoalPeriod', 'GriGoal', 'GriGoalProgress',
    'GriGoalTemplate', 'GriGoalBenchmark',
    'ExportFormat', 'ChartType', 'GriAnalytics', 'GriDashboard',
    'GriDashboardWidget', 'GriExport', 'GriExportTemplate', 'GriDataConnector',
    
    # Rewards models
    'ClaimRuleType', 'PointsStatus', 'UserPoints', 'ClaimRule', 'UserPointTransaction',
    'PointsTier', 'PointsPromotion', 'PointsAdjustment',
    'RewardType', 'RewardStatus', 'DeliveryMethod', 'Reward', 'RewardCategory',
    'RewardRating', 'RewardPromotion', 'RewardInventoryLog', 'RewardWishlist',
    'RedemptionStatus', 'FulfillmentStatus', 'RewardRedemption', 'RedemptionStatusHistory',
    'RedemptionDocument', 'RedemptionBatch', 'RedemptionBatchItem', 'RedemptionReport',
    'RedemptionAlert', 'CampaignType', 'CampaignStatus', 'NotificationType', 'RewardCampaign',
    'CampaignParticipant', 'RewardAnalytics', 'RewardNotification',
    'RewardConfiguration', 'RewardAuditLog', 'RewardIntegration',
    
    # Knowledge Management models
    'OwnerType', 'FileType', 'FileCategory', 'ProcessingStatus',
    'KmFile', 'KmChunk', 'KmFileTag', 'KmChunkTag',
    'TempFileBatch', 'TempFile', 'TempChunk', 'BatchProcessingStatus',
    'KmAnalytics', 'KmSearch', 'KmSearchResult', 'KmUserAccess',
    'KmAuditLog', 'KmConfiguration', 'KmIndexing',

    # IoT models
    'IoTScale',
    
    # Audit Rules models
    'AuditRule', 'RuleType'
]