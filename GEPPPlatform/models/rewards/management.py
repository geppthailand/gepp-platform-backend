"""
Rewards management models
Campaign setup, activity materials, claim rules, and campaign linking
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Integer, Boolean
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
    reward_budget_total = Column(DECIMAL(12, 2), nullable=True)  # org-level budget cap (THB)
    low_stock_threshold = Column(Integer, default=10)  # items below this count flagged as low
    point_to_baht_rate = Column(DECIMAL(10, 4), nullable=True)  # Phase 2: 1 point = X baht (Cost Report ROI)


class RewardCampaign(Base, BaseModel):
    """Time-bound campaigns for earning and redeeming rewards"""
    __tablename__ = 'reward_campaigns'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image_id = Column(BigInteger, nullable=True)  # FK files.id
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)  # null = no expiry
    status = Column(String(20), default='draft')  # draft / active / paused / archived; 'ended' is computed
    points_per_transaction_limit = Column(Integer, nullable=True)  # null = no limit
    points_per_day_limit = Column(Integer, nullable=True)  # null = no limit
    target_participants = Column(Integer, nullable=True)
    budget_baht = Column(DECIMAL(12, 2), nullable=True)
    metric_type = Column(String(20), nullable=False, default='material')  # Phase 2: 'material' | 'activity'


class RewardActivityMaterial(Base, BaseModel):
    """Materials or activities that can earn points"""
    __tablename__ = 'reward_activity_materials'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(20), nullable=False)  # material / activity
    material_id = Column(BigInteger, nullable=True)  # FK materials.id when type=material
    image_id = Column(BigInteger, nullable=True)  # FK files.id
    selling_price_per_kg = Column(DECIMAL(10, 2), nullable=True)  # waste resale value (THB/kg)
    ghg_factor = Column(DECIMAL(6, 3), nullable=True)  # kg CO2e saved per kg material


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
    """Links droppoints to campaigns — each pair gets a unique hash for QR check-in"""
    __tablename__ = 'reward_campaign_droppoints'

    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    droppoint_id = Column(BigInteger, ForeignKey('droppoints.id'), nullable=False)
    tag_id = Column(BigInteger, nullable=True)  # override tag for this campaign+droppoint
    hash = Column(String(64), unique=True, nullable=False)  # QR code hash for staff check-in


class RewardCampaignTarget(Base, BaseModel):
    """Per-material/activity goals for a campaign.

    A campaign can have many targets, each scoped to either:
      - a main_material (e.g. 'Plastic') — aggregates kg across all material-type ActivityMaterials
        whose linked Material has this main_material_id; unit is always 'kg'.
      - a single RewardActivityMaterial (org-scoped) — could be material-type (kg) or
        activity-type (count of claims, unit='times').

    Exactly one of `main_material_id` / `activity_material_id` must be set (CHECK constraint in DB).
    Some campaign materials/activities may have no target — that's fine, they're tracked without a goal.
    """
    __tablename__ = 'reward_campaign_targets'

    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    target_level = Column(String(20), nullable=False)  # 'main' | 'activity_material'
    main_material_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=True)
    activity_material_id = Column(BigInteger, ForeignKey('reward_activity_materials.id'), nullable=True)
    target_amount = Column(DECIMAL(12, 2), nullable=False)  # weight (kg) or count (times)
    target_unit = Column(String(10), nullable=False, default='kg')  # 'kg' | 'times'


class RewardActivityType(Base, BaseModel):
    """Activity types tracked by activity-based campaigns.

    organization_id NULL = system default (available to all orgs).
    organization_id NOT NULL = org-specific custom type (admin CRUD).

    Examples (system defaults seeded by migration 011):
      BYO Bag · BYO Cup · Refuse Plastic · Clean Beach · Recycle Workshop · Training · Plant Tree
    """
    __tablename__ = 'reward_activity_types'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)
    name = Column(String(100), nullable=False)
    name_local = Column(String(100), nullable=True)  # Thai display
    emoji = Column(String(10), nullable=True)
    color = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)


class RewardCampaignActivityType(Base, BaseModel):
    """Many-to-many: which activity types each activity-based campaign tracks."""
    __tablename__ = 'reward_campaign_activity_types'

    campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    activity_type_id = Column(BigInteger, ForeignKey('reward_activity_types.id'), nullable=False)
    points_per_event = Column(DECIMAL(10, 2), nullable=True)  # optional override
