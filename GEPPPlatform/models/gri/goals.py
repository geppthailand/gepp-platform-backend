"""
GRI Goals and Targets management
User-defined targets for GRI aspects with progress tracking
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel
from .standards import GriStandardType

class GoalStatus(enum.Enum):
    """Goal status types"""
    DRAFT = 'draft'
    ACTIVE = 'active'
    ON_TRACK = 'on_track'
    AT_RISK = 'at_risk'
    ACHIEVED = 'achieved'
    MISSED = 'missed'
    CANCELLED = 'cancelled'

class GoalPeriod(enum.Enum):
    """Goal period types"""
    MONTHLY = 'monthly'
    QUARTERLY = 'quarterly'
    ANNUAL = 'annual'
    MULTI_YEAR = 'multi_year'
    CUSTOM = 'custom'

class GriGoal(Base, BaseModel):
    """User-defined goals for GRI aspects"""
    __tablename__ = 'gri_goals'
    
    # Goal identification
    goal_name = Column(String(255), nullable=False)
    goal_code = Column(String(50), unique=True)
    gri_type = Column(SQLEnum(GriStandardType), nullable=False)
    
    # Organization and scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))  # Specific facility
    applies_to_all_locations = Column(Boolean, default=False)
    
    # Goal details
    description = Column(Text)
    business_case = Column(Text)  # Why this goal matters
    strategic_alignment = Column(Text)  # How it aligns with strategy
    
    # Target metric
    target_metric = Column(String(255), nullable=False)  # e.g., 'waste_generated_total'
    target_metric_unit = Column(String(50))  # tonnes, kg, percentage
    
    # Target values
    baseline_value = Column(DECIMAL(15, 2), nullable=False)
    baseline_year = Column(BigInteger, nullable=False)
    target_value = Column(DECIMAL(15, 2), nullable=False)
    target_reduction_percentage = Column(DECIMAL(5, 2))  # Calculated
    
    # Timeline
    goal_period = Column(SQLEnum(GoalPeriod), nullable=False)
    start_date = Column(DateTime, nullable=False)
    target_date = Column(DateTime, nullable=False)
    
    # Milestones
    milestones = Column(JSON)  # Array of {date, target_value, description}
    interim_targets = Column(JSON)  # Quarterly/monthly targets
    
    # Current progress
    current_value = Column(DECIMAL(15, 2))
    progress_percentage = Column(DECIMAL(5, 2))  # Calculated
    last_updated = Column(DateTime)
    
    # Status and tracking
    status = Column(SQLEnum(GoalStatus), default=GoalStatus.DRAFT)
    status_updated_date = Column(DateTime)
    risk_level = Column(String(50))  # low, medium, high
    risk_notes = Column(Text)
    
    # Action plans
    action_plans = Column(JSON)  # Array of action items
    responsible_parties = Column(JSON)  # Array of responsible user IDs
    
    # Success criteria
    success_criteria = Column(JSON)  # Detailed success metrics
    measurement_frequency = Column(String(50))  # How often to measure
    
    # Budget and resources
    allocated_budget = Column(DECIMAL(15, 2))
    actual_spend = Column(DECIMAL(15, 2))
    resource_requirements = Column(JSON)
    
    # Approval workflow
    requires_approval = Column(Boolean, default=True)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Review and adjustment
    last_review_date = Column(DateTime)
    next_review_date = Column(DateTime)
    adjustment_history = Column(JSON)  # History of target adjustments
    
    # Notification settings
    alert_threshold = Column(DECIMAL(5, 2))  # % deviation to trigger alert
    notification_recipients = Column(JSON)  # User IDs to notify
    
    # Related goals
    parent_goal_id = Column(BigInteger, ForeignKey('gri_goals.id'))
    
    # Priority and importance
    priority = Column(String(50), default='medium')  # low, medium, high, critical
    is_public = Column(Boolean, default=False)  # Public commitment
    
    # Additional metadata
    tags = Column(JSON)
    custom_fields = Column(JSON)
    
    # Relationships
    organization = relationship("Organization")
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    parent_goal = relationship("GriGoal", remote_side="GriGoal.id")
    
    # Progress tracking
    progress_records = relationship("GriGoalProgress", back_populates="goal")
    
    def calculate_progress(self):
        """Calculate progress towards goal"""
        if self.baseline_value and self.target_value and self.current_value:
            total_change_needed = self.target_value - self.baseline_value
            current_change = self.current_value - self.baseline_value
            
            if total_change_needed != 0:
                self.progress_percentage = (current_change / total_change_needed) * 100
            
            # Update status based on progress
            if self.progress_percentage >= 100:
                self.status = GoalStatus.ACHIEVED
            elif self.progress_percentage >= 80:
                self.status = GoalStatus.ON_TRACK
            elif self.progress_percentage >= 50:
                self.status = GoalStatus.AT_RISK
            else:
                self.status = GoalStatus.AT_RISK

class GriGoalProgress(Base, BaseModel):
    """Progress tracking for GRI goals"""
    __tablename__ = 'gri_goal_progress'
    
    goal_id = Column(BigInteger, ForeignKey('gri_goals.id'), nullable=False)
    
    # Progress measurement
    measurement_date = Column(DateTime, nullable=False)
    measured_value = Column(DECIMAL(15, 2), nullable=False)
    
    # Progress calculation
    progress_percentage = Column(DECIMAL(5, 2))
    deviation_from_target = Column(DECIMAL(15, 2))
    is_on_track = Column(Boolean)
    
    # Contributing factors
    contributing_factors = Column(JSON)  # Factors affecting progress
    improvement_actions = Column(JSON)  # Actions taken or planned
    
    # Data source
    data_source = Column(String(255))
    confidence_level = Column(String(50))  # high, medium, low
    
    # Notes and analysis
    notes = Column(Text)
    analysis = Column(Text)
    
    # Review
    reviewed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    review_date = Column(DateTime)
    review_comments = Column(Text)
    
    # Supporting evidence
    evidence_files = Column(JSON)
    
    # Relationships
    goal = relationship("GriGoal", back_populates="progress_records")
    reviewed_by = relationship("UserLocation")

class GriGoalTemplate(Base, BaseModel):
    """Templates for common GRI goals"""
    __tablename__ = 'gri_goal_templates'
    
    # Template identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    gri_type = Column(SQLEnum(GriStandardType), nullable=False)
    
    # Template details
    description = Column(Text)
    industry = Column(String(255))  # Industry-specific template
    organization_size = Column(String(50))  # small, medium, large
    
    # Standard targets
    suggested_metrics = Column(JSON)  # Array of metric definitions
    typical_targets = Column(JSON)  # Industry typical targets
    best_practice_targets = Column(JSON)  # Best-in-class targets
    
    # Timeline suggestions
    recommended_timeline = Column(String(100))  # e.g., "3 years"
    milestone_template = Column(JSON)  # Standard milestone structure
    
    # Action plan template
    action_plan_template = Column(JSON)  # Standard action items
    resource_estimates = Column(JSON)  # Resource requirements
    
    # Success factors
    critical_success_factors = Column(JSON)
    common_challenges = Column(JSON)
    mitigation_strategies = Column(JSON)
    
    # Measurement guidance
    measurement_methodology = Column(Text)
    data_collection_guidance = Column(Text)
    
    # Examples
    case_studies = Column(JSON)  # Real-world examples
    
    # Usage tracking
    times_used = Column(BigInteger, default=0)
    average_success_rate = Column(DECIMAL(5, 2))
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # Verified by experts
    
    # Version
    version = Column(String(20), default='1.0')
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    created_by = relationship("UserLocation")

class GriGoalBenchmark(Base, BaseModel):
    """Industry benchmarks for GRI goals"""
    __tablename__ = 'gri_goal_benchmarks'
    
    # Benchmark identification
    gri_type = Column(SQLEnum(GriStandardType), nullable=False)
    metric_name = Column(String(255), nullable=False)
    
    # Industry and region
    industry = Column(String(255), nullable=False)
    region = Column(String(100))  # Geographic region
    organization_size = Column(String(50))  # small, medium, large
    
    # Benchmark values
    percentile_25 = Column(DECIMAL(15, 2))  # Bottom quartile
    percentile_50 = Column(DECIMAL(15, 2))  # Median
    percentile_75 = Column(DECIMAL(15, 2))  # Top quartile
    percentile_90 = Column(DECIMAL(15, 2))  # Top 10%
    best_in_class = Column(DECIMAL(15, 2))  # Best performer
    
    # Additional statistics
    average_value = Column(DECIMAL(15, 2))
    standard_deviation = Column(DECIMAL(15, 2))
    sample_size = Column(BigInteger)  # Number of organizations
    
    # Trend data
    year_over_year_improvement = Column(DECIMAL(5, 2))  # Average % improvement
    typical_target_reduction = Column(DECIMAL(5, 2))  # Typical target %
    
    # Data details
    data_year = Column(BigInteger, nullable=False)
    data_source = Column(String(255))
    last_updated = Column(DateTime)
    
    # Validity
    is_verified = Column(Boolean, default=False)
    verification_source = Column(String(255))
    
    # Notes
    notes = Column(Text)
    limitations = Column(Text)
    
    # Status
    is_active = Column(Boolean, default=True)