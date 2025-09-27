"""
Points and claim rules models
Manage user points, claim rules mapping transaction records to points
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel

class ClaimRuleType(enum.Enum):
    """Types of claim rules"""
    MATERIAL_QUANTITY = 'material_quantity'  # Points per kg/unit of material
    TRANSACTION_COUNT = 'transaction_count'   # Points per transaction
    QUALITY_BONUS = 'quality_bonus'          # Bonus based on material quality
    VOLUME_TIER = 'volume_tier'              # Tiered rewards by volume
    FREQUENCY_BONUS = 'frequency_bonus'      # Bonus for regular participation
    MILESTONE_REWARD = 'milestone_reward'    # One-time milestone achievements

class PointsStatus(enum.Enum):
    """Status of points"""
    PENDING = 'pending'        # Awaiting approval/verification
    EARNED = 'earned'          # Confirmed and available
    REDEEMED = 'redeemed'      # Used for redemption
    EXPIRED = 'expired'        # Past expiration date
    CANCELLED = 'cancelled'    # Cancelled due to issues

class UserPoints(Base, BaseModel):
    """User points balance and history per organization"""
    __tablename__ = 'user_points'
    
    # User and organization
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Points balance
    total_points_earned = Column(DECIMAL(15, 2), default=0, nullable=False)
    total_points_redeemed = Column(DECIMAL(15, 2), default=0, nullable=False)
    current_balance = Column(DECIMAL(15, 2), default=0, nullable=False)
    pending_points = Column(DECIMAL(15, 2), default=0, nullable=False)
    
    # Expiration tracking
    points_expiring_30_days = Column(DECIMAL(15, 2), default=0)
    points_expiring_60_days = Column(DECIMAL(15, 2), default=0)
    points_expiring_90_days = Column(DECIMAL(15, 2), default=0)
    
    # Tier information
    current_tier = Column(String(50))
    tier_progress = Column(DECIMAL(5, 2))  # Progress to next tier %
    next_tier = Column(String(50))
    
    # Activity tracking
    last_earning_date = Column(DateTime)
    last_redemption_date = Column(DateTime)
    total_transactions = Column(BigInteger, default=0)
    
    # Performance metrics
    average_points_per_transaction = Column(DECIMAL(10, 2))
    best_month_points = Column(DECIMAL(15, 2))
    best_month_date = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    account_locked = Column(Boolean, default=False)
    lock_reason = Column(Text)
    
    # Relationships
    user_location = relationship("UserLocation")
    organization = relationship("Organization")
    point_transactions = relationship("UserPointTransaction", back_populates="user_points")
    
    def update_balance(self):
        """Update current balance from transactions"""
        earned = sum(pt.points_amount for pt in self.point_transactions 
                    if pt.status == PointsStatus.EARNED and pt.transaction_type == 'earn')
        redeemed = sum(pt.points_amount for pt in self.point_transactions 
                      if pt.status == PointsStatus.REDEEMED and pt.transaction_type == 'redeem')
        self.current_balance = earned - redeemed

class ClaimRule(Base, BaseModel):
    """Rules for claiming points based on transaction records"""
    __tablename__ = 'claim_rules'
    
    # Rule identification
    rule_name = Column(String(255), nullable=False)
    rule_code = Column(String(50), unique=True)
    rule_type = Column(SQLEnum(ClaimRuleType), nullable=False)
    
    # Organization scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Applicability
    material_ids = Column(JSON)  # Array of material IDs this rule applies to
    material_categories = Column(JSON)  # Material categories
    location_ids = Column(JSON)  # Specific locations
    user_tiers = Column(JSON)  # User tiers eligible
    
    # Rule conditions
    minimum_quantity = Column(DECIMAL(15, 2))  # Minimum quantity to earn points
    maximum_quantity = Column(DECIMAL(15, 2))  # Maximum quantity per transaction
    quality_requirements = Column(JSON)  # Quality conditions
    
    # Points calculation
    points_per_unit = Column(DECIMAL(10, 4))  # Points per kg/unit
    base_points = Column(DECIMAL(10, 2))     # Base points for transaction
    multiplier = Column(DECIMAL(5, 2), default=1.0)  # Multiplier factor
    
    # Tiered rewards
    quantity_tiers = Column(JSON)  # {min_qty: points_per_unit} tiers
    
    # Bonuses
    quality_bonus = Column(JSON)   # Quality grade bonuses
    frequency_bonus = Column(JSON) # Regular participation bonuses
    volume_bonus = Column(JSON)    # Volume-based bonuses
    
    # Time restrictions
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime)
    
    # Daily/monthly limits
    daily_points_limit = Column(DECIMAL(10, 2))
    monthly_points_limit = Column(DECIMAL(10, 2))
    max_transactions_per_day = Column(BigInteger)
    
    # Approval requirements
    requires_approval = Column(Boolean, default=False)
    auto_approve_threshold = Column(DECIMAL(10, 2))
    
    # Status
    is_active = Column(Boolean, default=True)
    priority = Column(BigInteger, default=0)  # Higher number = higher priority
    
    # Usage tracking
    total_claims = Column(BigInteger, default=0)
    total_points_awarded = Column(DECIMAL(15, 2), default=0)
    
    # Additional configuration
    calculation_formula = Column(Text)  # Custom formula if needed
    exclusion_rules = Column(JSON)      # Exclusion conditions
    
    # Relationships
    organization = relationship("Organization")
    point_transactions = relationship("UserPointTransaction", back_populates="claim_rule")

class UserPointTransaction(Base, BaseModel):
    """Individual point transactions (earning and redemption)"""
    __tablename__ = 'user_point_transactions'
    
    # User and organization
    user_points_id = Column(BigInteger, ForeignKey('user_points.id'), nullable=False)
    
    # Transaction details
    transaction_type = Column(String(20), nullable=False)  # 'earn', 'redeem', 'adjust', 'expire'
    points_amount = Column(DECIMAL(15, 2), nullable=False)
    
    # Source transaction (for earning points)
    source_transaction_record_id = Column(BigInteger, ForeignKey('transaction_records.id'))
    claim_rule_id = Column(BigInteger, ForeignKey('claim_rules.id'))
    
    # Redemption details (for redeeming points)
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'))
    
    # Calculation details
    material_quantity = Column(DECIMAL(15, 2))
    material_unit = Column(String(20))
    points_per_unit = Column(DECIMAL(10, 4))
    base_points = Column(DECIMAL(10, 2))
    bonus_points = Column(DECIMAL(10, 2))
    multiplier_applied = Column(DECIMAL(5, 2))
    
    # Quality and conditions
    material_quality = Column(String(50))
    quality_bonus = Column(DECIMAL(10, 2))
    tier_bonus = Column(DECIMAL(10, 2))
    
    # Status and approval
    status = Column(SQLEnum(PointsStatus), default=PointsStatus.PENDING)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Expiration
    expires_on = Column(DateTime)
    expiry_notified = Column(Boolean, default=False)
    
    # Calculation metadata
    calculation_data = Column(JSON)  # Detailed calculation breakdown
    
    # Reference information
    reference_number = Column(String(100))
    description = Column(String(500))
    notes = Column(Text)
    
    # Audit trail
    processed_date = Column(DateTime)
    processed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    user_points = relationship("UserPoints", back_populates="point_transactions")
    source_transaction_record = relationship("TransactionRecord")
    claim_rule = relationship("ClaimRule", back_populates="point_transactions")
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    processed_by = relationship("UserLocation", foreign_keys=[processed_by_id])

class PointsTier(Base, BaseModel):
    """User tier system for rewards program"""
    __tablename__ = 'points_tiers'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Tier definition
    tier_name = Column(String(100), nullable=False)
    tier_code = Column(String(50))
    tier_level = Column(BigInteger, nullable=False)  # 1, 2, 3, etc.
    
    # Requirements
    points_threshold = Column(DECIMAL(15, 2), nullable=False)  # Points needed to reach
    transactions_required = Column(BigInteger)  # Minimum transactions
    time_period_days = Column(BigInteger, default=365)  # Period to maintain tier
    
    # Benefits
    points_multiplier = Column(DECIMAL(3, 2), default=1.0)
    exclusive_rewards = Column(JSON)  # Array of reward IDs
    special_privileges = Column(JSON)  # Array of privileges
    
    # Display
    tier_color = Column(String(7))  # Hex color code
    tier_icon = Column(String(255))  # Icon URL
    description = Column(Text)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    organization = relationship("Organization")

class PointsPromotion(Base, BaseModel):
    """Promotional campaigns for points"""
    __tablename__ = 'points_promotions'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Promotion details
    promotion_name = Column(String(255), nullable=False)
    promotion_code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Timing
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # Promotion type
    promotion_type = Column(String(100))  # bonus_multiplier, bonus_points, double_points
    
    # Rules
    bonus_multiplier = Column(DECIMAL(3, 2))  # e.g., 2.0 for double points
    bonus_points = Column(DECIMAL(10, 2))     # Fixed bonus points
    
    # Conditions
    minimum_transaction_value = Column(DECIMAL(15, 2))
    eligible_materials = Column(JSON)  # Material IDs
    eligible_locations = Column(JSON)  # Location IDs
    eligible_users = Column(JSON)      # User IDs or tiers
    
    # Limits
    max_uses_per_user = Column(BigInteger)
    max_total_uses = Column(BigInteger)
    max_points_per_user = Column(DECIMAL(15, 2))
    
    # Usage tracking
    total_uses = Column(BigInteger, default=0)
    total_points_awarded = Column(DECIMAL(15, 2), default=0)
    unique_users = Column(BigInteger, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    requires_code = Column(Boolean, default=False)
    
    # Relationships
    organization = relationship("Organization")

class PointsAdjustment(Base, BaseModel):
    """Manual adjustments to user points"""
    __tablename__ = 'points_adjustments'
    
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Adjustment details
    adjustment_type = Column(String(50))  # add, subtract, correction
    points_amount = Column(DECIMAL(15, 2), nullable=False)
    
    # Reason and approval
    reason = Column(Text, nullable=False)
    admin_notes = Column(Text)
    
    # Processing
    processed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    
    # Status
    status = Column(String(50), default='pending')  # pending, approved, rejected
    
    # Reference
    reference_transaction_id = Column(BigInteger)
    reference_number = Column(String(100))
    
    # Relationships
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    organization = relationship("Organization")
    processed_by = relationship("UserLocation", foreign_keys=[processed_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])