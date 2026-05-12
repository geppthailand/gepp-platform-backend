"""CRM / Marketing module models — event tracking, segmentation, campaigns, email delivery."""

from .events import CrmEvent
from .profiles import CrmUserProfile, CrmOrgProfile
from .segments import CrmSegment, CrmSegmentMember
from .templates import CrmEmailTemplate
from .campaigns import CrmCampaign, CrmCampaignDelivery
from .lists import CrmEmailList, CrmUnsubscribe
from .brand_assets import CrmBrandAsset
from .leads import CrmLead, CrmLeadActivity
from .drip import CrmDripSequence, CrmDripStep, CrmDripEnrollment
from .conversations import CrmConversation, CrmConversationMessage

__all__ = [
    "CrmEvent",
    "CrmUserProfile",
    "CrmOrgProfile",
    "CrmSegment",
    "CrmSegmentMember",
    "CrmEmailTemplate",
    "CrmCampaign",
    "CrmCampaignDelivery",
    "CrmEmailList",
    "CrmUnsubscribe",
    "CrmBrandAsset",
    "CrmLead",
    "CrmLeadActivity",
    "CrmDripSequence",
    "CrmDripStep",
    "CrmDripEnrollment",
    "CrmConversation",
    "CrmConversationMessage",
]
