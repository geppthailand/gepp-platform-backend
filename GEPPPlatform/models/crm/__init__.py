"""CRM / Marketing module models — event tracking, segmentation, campaigns, email delivery."""

from .events import CrmEvent
from .profiles import CrmUserProfile, CrmOrgProfile
from .segments import CrmSegment, CrmSegmentMember
from .templates import CrmEmailTemplate
from .campaigns import CrmCampaign, CrmCampaignDelivery
from .lists import CrmEmailList, CrmUnsubscribe

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
]
