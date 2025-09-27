"""
Reward redemption and transaction models
Manage reward redemption history and transaction processing
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel

class RedemptionStatus(enum.Enum):
    """Redemption processing status"""
    PENDING = 'pending'           # Pending approval/processing
    PROCESSING = 'processing'     # Being processed
    APPROVED = 'approved'         # Approved for fulfillment
    FULFILLED = 'fulfilled'       # Delivered/completed
    CANCELLED = 'cancelled'       # Cancelled by user/admin
    REJECTED = 'rejected'         # Rejected by admin
    EXPIRED = 'expired'          # Expired before fulfillment
    REFUNDED = 'refunded'        # Points refunded

class FulfillmentStatus(enum.Enum):
    """Fulfillment tracking status"""
    NOT_STARTED = 'not_started'
    PREPARING = 'preparing'       # Preparing for shipment/delivery
    SHIPPED = 'shipped'          # Shipped/in transit
    OUT_FOR_DELIVERY = 'out_for_delivery'
    DELIVERED = 'delivered'      # Successfully delivered
    PICKUP_READY = 'pickup_ready' # Ready for pickup
    PICKED_UP = 'picked_up'      # Picked up by user
    DELIVERY_FAILED = 'delivery_failed'
    RETURNED = 'returned'        # Returned to sender

class RewardRedemption(Base, BaseModel):
    """Reward redemption transactions"""
    __tablename__ = 'reward_redemptions'
    
    # User and reward
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    reward_id = Column(BigInteger, ForeignKey('rewards.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Redemption details
    redemption_code = Column(String(50), unique=True, nullable=False)  # Unique redemption code
    quantity = Column(BigInteger, default=1, nullable=False)
    
    # Points transaction
    points_cost = Column(DECIMAL(10, 2), nullable=False)  # Points deducted
    points_refunded = Column(DECIMAL(10, 2), default=0)   # Points refunded if cancelled
    
    # Pricing at time of redemption
    unit_points_cost = Column(DECIMAL(10, 2), nullable=False)
    discount_applied = Column(DECIMAL(10, 2), default=0)  # Points discount
    promotion_code = Column(String(50))                   # Applied promotion
    
    # Status tracking
    status = Column(SQLEnum(RedemptionStatus), default=RedemptionStatus.PENDING)
    status_updated_date = Column(DateTime)
    status_notes = Column(Text)
    
    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Fulfillment tracking
    fulfillment_status = Column(SQLEnum(FulfillmentStatus), default=FulfillmentStatus.NOT_STARTED)
    fulfillment_method = Column(String(50))  # From reward's delivery_method
    
    # Delivery information
    shipping_address = Column(JSON)  # Full address details
    delivery_instructions = Column(Text)
    estimated_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)
    
    # Tracking information
    tracking_number = Column(String(255))
    carrier = Column(String(100))
    tracking_url = Column(String(500))
    
    # Digital delivery
    digital_code = Column(String(255))      # Voucher/coupon code
    digital_content = Column(JSON)          # Digital content details
    digital_delivered_date = Column(DateTime)
    
    # Expiration
    expires_on = Column(DateTime)
    expiry_notified = Column(Boolean, default=False)
    
    # User feedback
    user_rating = Column(BigInteger)        # 1-5 stars
    user_review = Column(Text)
    feedback_date = Column(DateTime)
    
    # Additional form data
    custom_form_data = Column(JSON)         # Additional form fields filled by user
    
    # Processing metadata
    processing_started_date = Column(DateTime)
    processing_completed_date = Column(DateTime)
    processing_duration = Column(BigInteger)  # Seconds
    
    # External system integration
    external_order_id = Column(String(255)) # ID in external fulfillment system
    external_status = Column(String(100))   # Status from external system
    external_tracking = Column(JSON)        # External tracking info
    
    # Cost tracking
    fulfillment_cost = Column(DECIMAL(10, 2))  # Actual cost to fulfill
    shipping_cost = Column(DECIMAL(10, 2))     # Shipping cost charged to user
    
    # Support and issues
    has_issues = Column(Boolean, default=False)
    issue_description = Column(Text)
    issue_resolved = Column(Boolean, default=False)
    support_ticket_id = Column(String(100))
    
    # Cancellation
    cancelled_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    cancellation_date = Column(DateTime)
    cancellation_reason = Column(Text)
    refund_processed = Column(Boolean, default=False)
    
    # Relationships
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    reward = relationship("Reward", back_populates="redemptions")
    organization = relationship("Organization")
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    cancelled_by = relationship("UserLocation", foreign_keys=[cancelled_by_id])
    
    # Status history
    status_history = relationship("RedemptionStatusHistory", back_populates="redemption")
    
    def generate_redemption_code(self):
        """Generate unique redemption code"""
        import secrets
        import string
        while True:
            code = ''.join(secrets.choices(string.ascii_uppercase + string.digits, k=12))
            # Check if code already exists
            existing = self.__class__.query.filter_by(redemption_code=code).first()
            if not existing:
                self.redemption_code = code
                break

class RedemptionStatusHistory(Base, BaseModel):
    """History of status changes for redemptions"""
    __tablename__ = 'redemption_status_history'
    
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'), nullable=False)
    
    # Status change
    from_status = Column(String(50))
    to_status = Column(String(50), nullable=False)
    change_date = Column(DateTime, nullable=False)
    
    # Who made the change
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    change_reason = Column(Text)
    
    # Additional context
    notes = Column(Text)
    system_generated = Column(Boolean, default=False)
    
    # Relationships
    redemption = relationship("RewardRedemption", back_populates="status_history")
    changed_by = relationship("UserLocation")

class RedemptionDocument(Base, BaseModel):
    """Documents associated with redemptions"""
    __tablename__ = 'redemption_documents'
    
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'), nullable=False)
    
    # Document details
    document_type = Column(String(100))  # receipt, shipping_label, warranty, manual
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(BigInteger)  # bytes
    mime_type = Column(String(100))
    
    # Metadata
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    is_user_visible = Column(Boolean, default=True)
    
    # Relationships
    redemption = relationship("RewardRedemption")
    uploaded_by = relationship("UserLocation")

class RedemptionBatch(Base, BaseModel):
    """Batch processing for multiple redemptions"""
    __tablename__ = 'redemption_batches'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Batch details
    batch_name = Column(String(255))
    batch_code = Column(String(50), unique=True)
    batch_type = Column(String(50))  # fulfillment, approval, refund
    
    # Processing
    total_redemptions = Column(BigInteger, default=0)
    processed_redemptions = Column(BigInteger, default=0)
    failed_redemptions = Column(BigInteger, default=0)
    
    # Status
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    
    # Timing
    started_date = Column(DateTime)
    completed_date = Column(DateTime)
    
    # Configuration
    batch_config = Column(JSON)  # Batch processing configuration
    
    # Results
    processing_log = Column(JSON)  # Processing results and errors
    
    # Created by
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Relationships
    organization = relationship("Organization")
    created_by = relationship("UserLocation")
    redemption_batch_items = relationship("RedemptionBatchItem", back_populates="batch")

class RedemptionBatchItem(Base, BaseModel):
    """Individual items in redemption batch"""
    __tablename__ = 'redemption_batch_items'
    
    batch_id = Column(BigInteger, ForeignKey('redemption_batches.id'), nullable=False)
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'), nullable=False)
    
    # Processing status for this item
    status = Column(String(50), default='pending')  # pending, processing, success, failed
    error_message = Column(Text)
    
    # Processing timestamps
    processing_started = Column(DateTime)
    processing_completed = Column(DateTime)
    
    # Results
    processing_result = Column(JSON)
    
    # Relationships
    batch = relationship("RedemptionBatch", back_populates="redemption_batch_items")
    redemption = relationship("RewardRedemption")

class RedemptionReport(Base, BaseModel):
    """Redemption analytics and reports"""
    __tablename__ = 'redemption_reports'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Report details
    report_name = Column(String(255), nullable=False)
    report_type = Column(String(100))  # summary, detailed, financial, fulfillment
    
    # Time period
    period_from = Column(DateTime, nullable=False)
    period_to = Column(DateTime, nullable=False)
    
    # Filters applied
    filters = Column(JSON)  # Report filters
    
    # Calculated metrics
    total_redemptions = Column(BigInteger)
    total_points_redeemed = Column(DECIMAL(15, 2))
    total_rewards_value = Column(DECIMAL(15, 2))
    
    # Status breakdown
    pending_redemptions = Column(BigInteger)
    fulfilled_redemptions = Column(BigInteger)
    cancelled_redemptions = Column(BigInteger)
    
    # Top performers
    top_rewards = Column(JSON)      # Most redeemed rewards
    top_users = Column(JSON)        # Most active users
    top_categories = Column(JSON)   # Most popular categories
    
    # Trends
    daily_trends = Column(JSON)
    monthly_trends = Column(JSON)
    
    # Performance metrics
    average_fulfillment_time = Column(DECIMAL(10, 2))  # Hours
    fulfillment_success_rate = Column(DECIMAL(5, 2))   # Percentage
    user_satisfaction_score = Column(DECIMAL(3, 2))    # Average rating
    
    # Generated metadata
    generated_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    generation_time = Column(DateTime, nullable=False)
    
    # File export
    export_file_path = Column(Text)
    
    # Relationships
    organization = relationship("Organization")
    generated_by = relationship("UserLocation")

class RedemptionAlert(Base, BaseModel):
    """Alerts and notifications for redemption management"""
    __tablename__ = 'redemption_alerts'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Alert details
    alert_type = Column(String(100))  # low_stock, pending_approval, delivery_delay, expiration
    alert_title = Column(String(255), nullable=False)
    alert_message = Column(Text)
    
    # Severity
    severity = Column(String(50), default='medium')  # low, medium, high, critical
    
    # Related entities
    reward_id = Column(BigInteger, ForeignKey('rewards.id'))
    redemption_id = Column(BigInteger, ForeignKey('reward_redemptions.id'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Status
    status = Column(String(50), default='active')  # active, acknowledged, resolved, dismissed
    acknowledged_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    acknowledged_date = Column(DateTime)
    
    # Auto-resolution
    auto_resolve_date = Column(DateTime)
    resolution_notes = Column(Text)
    
    # Notification settings
    email_sent = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    
    # Relationships
    organization = relationship("Organization")
    reward = relationship("Reward")
    redemption = relationship("RewardRedemption")
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    acknowledged_by = relationship("UserLocation", foreign_keys=[acknowledged_by_id])