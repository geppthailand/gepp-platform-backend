"""
Rewards Module — 15 focused models for B2B2C reward system
"""

from .management import (
    RewardSetup, RewardCampaign, RewardActivityMaterial,
    RewardCampaignClaim, RewardCampaignCatalog, RewardCampaignDroppoint,
    RewardCampaignTarget, RewardActivityType,
)
from .catalog import RewardCatalog, RewardStock, RewardCatalogCategory
from .points import RewardPointTransaction, RewardPointTransactionComponent
from .claim_requests import RewardClaimRequest, register_claim_request_sync
from .redemptions import (
    RewardRedemption, RewardStaffInvite, RewardUser, OrganizationRewardUser,
    Droppoint, DroppointType
)

__all__ = [
    # Management
    'RewardSetup', 'RewardCampaign', 'RewardActivityMaterial',
    'RewardCampaignClaim', 'RewardCampaignCatalog', 'RewardCampaignDroppoint',
    'RewardCampaignTarget', 'RewardActivityType',
    # Catalog
    'RewardCatalog', 'RewardStock', 'RewardCatalogCategory',
    # Points
    'RewardPointTransaction', 'RewardClaimRequest',
    # Redemptions & Users
    'RewardRedemption', 'RewardStaffInvite', 'RewardUser', 'OrganizationRewardUser',
    'Droppoint', 'DroppointType',
]

# Keep self-submitted claim requests in step with waste transaction status changes.
register_claim_request_sync()
