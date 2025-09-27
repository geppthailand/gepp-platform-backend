"""
Rewards catalog models
Manage redeemable rewards and their points costs
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel

class RewardType(enum.Enum):
    """Types of rewards"""
    PHYSICAL_ITEM = 'physical_item'      # Physical goods to be delivered
    DIGITAL_VOUCHER = 'digital_voucher'   # Digital vouchers/coupons
    CASH_EQUIVALENT = 'cash_equivalent'   # Cash or cash-like rewards
    EXPERIENCE = 'experience'             # Event tickets, experiences
    DONATION = 'donation'                 # Charitable donations
    SERVICE = 'service'                   # Service credits
    DISCOUNT = 'discount'                 # Discount codes
    SUBSCRIPTION = 'subscription'         # Subscription benefits

class RewardStatus(enum.Enum):
    """Reward availability status"""
    ACTIVE = 'active'           # Available for redemption
    INACTIVE = 'inactive'       # Not available
    OUT_OF_STOCK = 'out_of_stock'  # Temporarily unavailable
    DISCONTINUED = 'discontinued'   # Permanently discontinued
    COMING_SOON = 'coming_soon'    # Not yet available

class DeliveryMethod(enum.Enum):
    """How rewards are delivered"""
    PICKUP = 'pickup'           # Physical pickup
    SHIPPING = 'shipping'       # Shipped to address
    EMAIL = 'email'            # Email delivery
    SMS = 'sms'               # SMS delivery
    IN_APP = 'in_app'         # Delivered within app
    THIRD_PARTY = 'third_party' # Delivered by partner
    INSTANT = 'instant'        # Instant digital delivery

class Reward(Base, BaseModel):
    """Redeemable rewards catalog"""
    __tablename__ = 'rewards'
    
    # Organization scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Reward identification
    reward_name = Column(String(255), nullable=False)
    reward_code = Column(String(50), unique=True)
    reward_type = Column(SQLEnum(RewardType), nullable=False)
    
    # Description and details
    description = Column(Text)
    terms_conditions = Column(Text)
    usage_instructions = Column(Text)
    
    # Points and pricing
    points_cost = Column(DECIMAL(10, 2), nullable=False)
    cash_value = Column(DECIMAL(10, 2))  # Equivalent cash value
    discount_percentage = Column(DECIMAL(5, 2))  # If discount type
    
    # Availability
    status = Column(SQLEnum(RewardStatus), default=RewardStatus.ACTIVE)
    total_quantity = Column(BigInteger)  # Total available quantity
    reserved_quantity = Column(BigInteger, default=0)  # Reserved for pending redemptions
    redeemed_quantity = Column(BigInteger, default=0)  # Already redeemed
    available_quantity = Column(BigInteger)  # Calculated: total - reserved - redeemed
    
    # Limits and restrictions
    max_redemptions_per_user = Column(BigInteger)  # Per user limit
    max_redemptions_per_day = Column(BigInteger)   # Daily limit
    max_redemptions_per_month = Column(BigInteger) # Monthly limit
    
    # User tier restrictions
    eligible_user_tiers = Column(JSON)  # Array of tier names
    minimum_user_level = Column(BigInteger)
    
    # Timing restrictions
    available_from = Column(DateTime)
    available_to = Column(DateTime)
    redemption_deadline = Column(DateTime)  # Deadline to use after redemption
    
    # Delivery configuration
    delivery_method = Column(SQLEnum(DeliveryMethod), nullable=False)
    estimated_delivery_days = Column(BigInteger)
    shipping_cost = Column(DECIMAL(10, 2), default=0)
    requires_shipping_address = Column(Boolean, default=False)
    
    # Partner information
    partner_name = Column(String(255))
    partner_contact = Column(JSON)  # Contact details
    partner_terms = Column(Text)
    
    # Media and presentation
    image_url = Column(String(500))
    thumbnail_url = Column(String(500))
    gallery_images = Column(JSON)  # Array of image URLs
    
    # Category and tags
    category = Column(String(100))
    subcategory = Column(String(100))
    tags = Column(JSON)  # Array of tags for search/filtering
    
    # Featured and promotion
    is_featured = Column(Boolean, default=False)
    featured_order = Column(BigInteger)
    promotion_text = Column(String(255))
    
    # Requirements and conditions
    minimum_transaction_count = Column(BigInteger)  # User must have X transactions
    minimum_points_balance = Column(DECIMAL(10, 2))  # User must maintain X points after redemption
    location_restrictions = Column(JSON)  # Available only in certain locations
    
    # Expiration settings
    expires_after_days = Column(BigInteger)  # Days after redemption
    expiry_reminder_days = Column(BigInteger)  # Days before expiry to remind
    
    # Analytics tracking
    view_count = Column(BigInteger, default=0)
    redemption_count = Column(BigInteger, default=0)
    average_rating = Column(DECIMAL(3, 2))
    total_ratings = Column(BigInteger, default=0)
    
    # External integration
    external_id = Column(String(255))  # ID in external system
    external_url = Column(String(500))  # External redemption URL
    api_config = Column(JSON)  # API configuration for external delivery
    
    # Administrative
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    
    # Sort order
    display_order = Column(BigInteger, default=0)
    
    # Additional configuration
    custom_fields = Column(JSON)  # Organization-specific fields
    redemption_form_fields = Column(JSON)  # Additional form fields for redemption
    
    # Relationships
    organization = relationship("Organization")
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    redemptions = relationship("RewardRedemption", back_populates="reward")
    
    def update_availability(self):
        """Update available quantity"""
        if self.total_quantity:
            self.available_quantity = self.total_quantity - (self.reserved_quantity or 0) - (self.redeemed_quantity or 0)
            
            if self.available_quantity <= 0 and self.status == RewardStatus.ACTIVE:
                self.status = RewardStatus.OUT_OF_STOCK
    
    def is_available_for_user(self, user_location):
        """Check if reward is available for specific user"""
        # Check basic availability
        if self.status != RewardStatus.ACTIVE:
            return False
            
        # Check quantity
        if self.available_quantity is not None and self.available_quantity <= 0:
            return False
            
        # Check date restrictions
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        if self.available_from and now < self.available_from:
            return False
            
        if self.available_to and now > self.available_to:
            return False
        
        return True

class RewardCategory(Base, BaseModel):
    """Reward categories for organization"""
    __tablename__ = 'reward_categories'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Category details
    name = Column(String(255), nullable=False)
    code = Column(String(50))
    description = Column(Text)
    
    # Hierarchy
    parent_category_id = Column(BigInteger, ForeignKey('reward_categories.id'))
    
    # Display
    icon = Column(String(255))
    color = Column(String(7))  # Hex color
    display_order = Column(BigInteger, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    organization = relationship("Organization")
    parent_category = relationship("RewardCategory", remote_side="RewardCategory.id")

class RewardRating(Base, BaseModel):
    """User ratings and reviews for rewards"""
    __tablename__ = 'reward_ratings'
    
    reward_id = Column(BigInteger, ForeignKey('rewards.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Rating details
    rating = Column(BigInteger, nullable=False)  # 1-5 stars
    review_text = Column(Text)
    
    # Verification
    is_verified_purchase = Column(Boolean, default=False)
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'))
    
    # Moderation
    is_approved = Column(Boolean, default=True)
    moderation_notes = Column(Text)
    
    # Helpfulness
    helpful_votes = Column(BigInteger, default=0)
    total_votes = Column(BigInteger, default=0)
    
    # Relationships
    reward = relationship("Reward")
    user_location = relationship("UserLocation")

class RewardPromotion(Base, BaseModel):
    """Promotional campaigns for rewards"""
    __tablename__ = 'reward_promotions'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Promotion details
    promotion_name = Column(String(255), nullable=False)
    promotion_code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Timing
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    
    # Promotion type
    promotion_type = Column(String(100))  # discount_points, bonus_points, free_shipping
    
    # Discount configuration
    points_discount_percentage = Column(DECIMAL(5, 2))  # % off points cost
    points_discount_fixed = Column(DECIMAL(10, 2))      # Fixed points off
    free_shipping = Column(Boolean, default=False)
    
    # Eligibility
    eligible_rewards = Column(JSON)    # Reward IDs
    eligible_categories = Column(JSON) # Category IDs
    eligible_users = Column(JSON)      # User IDs or tiers
    minimum_points_balance = Column(DECIMAL(10, 2))
    
    # Usage limits
    max_uses_per_user = Column(BigInteger)
    max_total_uses = Column(BigInteger)
    
    # Usage tracking
    total_uses = Column(BigInteger, default=0)
    unique_users = Column(BigInteger, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    requires_code = Column(Boolean, default=False)
    
    # Relationships
    organization = relationship("Organization")

class RewardInventoryLog(Base, BaseModel):
    """Inventory tracking for physical rewards"""
    __tablename__ = 'reward_inventory_logs'
    
    reward_id = Column(BigInteger, ForeignKey('rewards.id'), nullable=False)
    
    # Log details
    log_type = Column(String(50))  # stock_in, stock_out, reservation, release, adjustment
    quantity_change = Column(BigInteger, nullable=False)  # Positive or negative
    
    # References
    reference_id = Column(BigInteger)  # Redemption ID or purchase order
    reference_type = Column(String(50))  # redemption, purchase, adjustment
    
    # Details
    notes = Column(Text)
    performed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Balances after change
    quantity_after = Column(BigInteger)
    
    # Relationships
    reward = relationship("Reward")
    performed_by = relationship("UserLocation")

class RewardWishlist(Base, BaseModel):
    """User wishlist for rewards"""
    __tablename__ = 'reward_wishlists'
    
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    reward_id = Column(BigInteger, ForeignKey('rewards.id'), nullable=False)
    
    # Wishlist details
    added_date = Column(DateTime, nullable=False)
    priority = Column(BigInteger, default=0)  # User-defined priority
    notes = Column(Text)
    
    # Notifications
    notify_when_available = Column(Boolean, default=True)
    notify_when_on_sale = Column(Boolean, default=True)
    
    # Relationships
    user_location = relationship("UserLocation")
    reward = relationship("Reward")