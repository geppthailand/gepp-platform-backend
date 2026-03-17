"""
Rewards management models
Campaign setup, activity materials, claim rules, and campaign linking
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class RewardSetup(Base, BaseModel):
    """Organization-level reward program configuration"""
    __tablename__ = 'reward_setup'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    program_name = Column(String(255), nullable=True)
    program_name_local = Column(String(255), nullable=True)
    points_rounding_method = Column(String(20), default='round')  # floor / ceil / round
    timezone = Column(String(100), default='Asia/Bangkok')
    cost_per_point = Column(DECIMAL(10, 4), default=0.25)
    qr_code_size = Column(Integer, default=200)
    qr_error_correction = Column(String(1), default='M')  # L / M / Q / H
    receipt_template = Column(String(255), nullable=True)
    hash = Column(String(64), unique=True, nullable=False)
    welcome_message = Column(Text, nullable=True)


class RewardCampaign(Base, BaseModel):
    """Time-bound campaigns for earning and redeeming rewards"""
    __tablename__ = 'reward_campaigns'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image_id = Column(BigInteger, nullable=True)  # FK files.id
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)  # null = no expiry
    status = Column(String(20), default='active')  # active / inactive
    points_per_transaction_limit = Column(Integer, nullable=True)  # null = no limit
    points_per_day_limit = Column(Integer, nullable=True)  # null = no limit


class RewardActivityMaterial(Base, BaseModel):
    """Materials or activities that can earn points"""
    __tablename__ = 'reward_activity_materials'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(20), nullable=False)  # material / activity
    material_id = Column(BigInteger, nullable=True)  # FK materials.id when type=material
    image_id = Column(BigInteger, nullable=True)  # FK files.id


class RewardCampaignClaim(Base, BaseModel):
    """Links activity materials to campaigns with point rules"""
    __tablename__ = 'reward_campaign_claims'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    activity_material_id = Column(BigInteger, ForeignKey('reward_activity_materials.id'), nullable=False)
    points = Column(DECIMAL(10, 2), nullable=False)  # points per unit
    max_claims_total = Column(Integer, nullable=True)  # null = unlimited
    max_claims_per_user = Column(Integer, nullable=True)  # null = unlimited


class RewardCampaignCatalog(Base, BaseModel):
    """Links catalog items to campaigns with redeem rules"""
    __tablename__ = 'reward_campaign_catalog'

    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    catalog_id = Column(BigInteger, ForeignKey('reward_catalog.id'), nullable=False)
    points_cost = Column(Integer, nullable=False)  # points to redeem 1 unit
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default='active')  # active / inactive


class RewardCampaignDroppoint(Base, BaseModel):
    """Links droppoints to campaigns"""
    __tablename__ = 'reward_campaign_droppoints'

    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    droppoint_id = Column(BigInteger, ForeignKey('droppoints.id'), nullable=False)
    tag_id = Column(BigInteger, nullable=True)  # override tag for this campaign+droppoint
