"""
EPR (Extended Producer Responsibility) module
Comprehensive EPR program management, auditing, and compliance
"""

# Core EPR models
from .core import (
    EprOrganization, EprOrganizationMaterialGroup, EprOrganizationUser,
    EprBrand, EprProduct, EprProject, EprProjectFile, EprProjectUser, 
    EprProjectUsersLog, EprProjectLog
)

# EPR PRO models  
from .pro import (
    EprPro, EprProInfo, EprProFile, EprProMaterialGroup, EprProMaterialGroupUser,
    EprProMaterialTagGroup, EprProMaterialTag, EprProMaterial, EprProUser
)

# Auditing and logistics models
from .auditing import (
    EprAuditorTransactionAssignment, EprAuditorTransactionAssignInfoLog,
    EprRecyclerAuditDoc, EprRecyclerAuditPreset, EprLogisticAssistantFeeSettings,
    EprProvinceDistance, EprSorterType, EprSelfRegistrationUrl, EprUserLafInfo
)

# Notifications
from .notifications import EprNotification, EprNotificationActionType

__all__ = [
    # Core EPR
    'EprOrganization', 'EprOrganizationMaterialGroup', 'EprOrganizationUser',
    'EprBrand', 'EprProduct', 'EprProject', 'EprProjectFile', 'EprProjectUser',
    'EprProjectUsersLog', 'EprProjectLog',
    
    # EPR PRO
    'EprPro', 'EprProInfo', 'EprProFile', 'EprProMaterialGroup', 'EprProMaterialGroupUser',
    'EprProMaterialTagGroup', 'EprProMaterialTag', 'EprProMaterial', 'EprProUser',
    
    # Auditing and Logistics
    'EprAuditorTransactionAssignment', 'EprAuditorTransactionAssignInfoLog',
    'EprRecyclerAuditDoc', 'EprRecyclerAuditPreset', 'EprLogisticAssistantFeeSettings',
    'EprProvinceDistance', 'EprSorterType', 'EprSelfRegistrationUrl', 'EprUserLafInfo',
    
    # Notifications
    'EprNotification', 'EprNotificationActionType'
]