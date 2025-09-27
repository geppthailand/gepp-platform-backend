"""
EPR Project fee calculation and management models
Assistant fees, spending tracking, and fee calculation methods
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel

class EprProjectAssistantFeeCalculationMethodType(Base, BaseModel):
    """Methods for calculating assistant fees in EPR projects"""
    __tablename__ = 'epr_project_assistant_fee_calculation_method_types'
    
    # Method identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Calculation approach
    calculation_basis = Column(String(100))  # volume, weight, time, performance, hybrid
    formula = Column(Text)  # Mathematical formula for calculation
    
    # Parameters
    base_parameters = Column(JSON)  # Base parameters for calculation
    variable_parameters = Column(JSON)  # Variable parameters that can be adjusted
    
    # Constraints
    minimum_fee = Column(DECIMAL(10, 2))
    maximum_fee = Column(DECIMAL(10, 2))
    fee_cap_percentage = Column(DECIMAL(5, 2))  # Cap as percentage of project budget
    
    # Performance factors
    performance_multipliers = Column(JSON)  # Multipliers based on performance metrics
    quality_adjustments = Column(JSON)  # Adjustments for quality scores
    timeliness_factors = Column(JSON)  # Factors for on-time delivery
    
    # Applicable contexts
    project_types = Column(JSON)  # Types of projects this method applies to
    material_types = Column(JSON)  # Material types this method is suitable for
    organization_types = Column(JSON)  # Organization types that can use this method
    
    # Frequency and timing
    calculation_frequency = Column(String(50))  # monthly, quarterly, per_milestone, final
    payment_schedule = Column(String(50))  # immediate, monthly, quarterly, final
    
    # Approval requirements
    requires_approval = Column(Boolean, default=False)
    approval_threshold = Column(DECIMAL(15, 2))
    auto_approve_below = Column(DECIMAL(15, 2))
    
    # Documentation requirements
    required_documentation = Column(JSON)  # Required documents for fee calculation
    evidence_requirements = Column(JSON)  # Evidence needed to support calculation
    
    # Status and versioning
    is_active = Column(Boolean, default=True)
    version = Column(String(20), default='1.0')
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)
    
    # Audit trail
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    last_modified_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Usage tracking
    usage_count = Column(BigInteger, default=0)
    last_used_date = Column(DateTime)
    
    # Relationships
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    last_modified_by = relationship("UserLocation", foreign_keys=[last_modified_by_id])

class EprProjectUserAssistantFeeSetting(Base, BaseModel):
    """Fee settings for users providing assistant services in EPR projects"""
    __tablename__ = 'epr_project_user_assistant_fee_settings'
    
    # Project and user
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Fee calculation method
    calculation_method_id = Column(BigInteger, ForeignKey('epr_project_assistant_fee_calculation_method_types.id'))
    
    # Custom rates and settings
    base_rate = Column(DECIMAL(10, 2))  # Base rate per unit
    hourly_rate = Column(DECIMAL(10, 2))  # If time-based
    per_kg_rate = Column(DECIMAL(8, 4))  # If weight-based
    per_volume_rate = Column(DECIMAL(8, 4))  # If volume-based
    
    # Performance bonuses
    quality_bonus_percentage = Column(DECIMAL(5, 2))
    timeliness_bonus_percentage = Column(DECIMAL(5, 2))
    volume_bonus_tiers = Column(JSON)  # Bonus tiers for volume achievements
    
    # Penalties and deductions
    late_delivery_penalty = Column(DECIMAL(5, 2))  # Percentage penalty
    quality_deduction = Column(DECIMAL(5, 2))  # Deduction for poor quality
    
    # Limits and caps
    monthly_fee_cap = Column(DECIMAL(15, 2))
    project_fee_cap = Column(DECIMAL(15, 2))
    minimum_monthly_guarantee = Column(DECIMAL(10, 2))
    
    # Service scope
    service_types = Column(JSON)  # Types of services covered
    material_types = Column(JSON)  # Material types this setting applies to
    geographic_scope = Column(JSON)  # Geographic areas covered
    
    # Effective period
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime)
    
    # Terms and conditions
    payment_terms = Column(String(100))  # net_30, bi_weekly, monthly
    invoicing_requirements = Column(JSON)  # Required invoice details
    documentation_requirements = Column(JSON)  # Required supporting documents
    
    # Approval and authorization
    is_approved = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Contract details
    contract_reference = Column(String(255))
    contract_start_date = Column(DateTime)
    contract_end_date = Column(DateTime)
    auto_renewal = Column(Boolean, default=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    suspension_reason = Column(Text)
    suspension_date = Column(DateTime)
    
    # Performance tracking
    total_fees_paid = Column(DECIMAL(15, 2), default=0)
    average_performance_score = Column(DECIMAL(5, 2))
    last_performance_review = Column(DateTime)
    
    # Additional terms
    special_conditions = Column(Text)
    extra_metadata = Column(JSON)
    
    # Relationships
    project = relationship("EprProject")
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    calculation_method = relationship("EprProjectAssistantFeeCalculationMethodType")
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    
    fees = relationship("EprProjectUserAssistantFee", back_populates="fee_setting")

class EprProjectUserAssistantFee(Base, BaseModel):
    """Actual calculated and paid assistant fees"""
    __tablename__ = 'epr_project_user_assistant_fees'
    
    # Reference to fee setting
    fee_setting_id = Column(BigInteger, ForeignKey('epr_project_user_assistant_fee_settings.id'), nullable=False)
    
    # Calculation period
    calculation_period = Column(String(50))  # monthly, quarterly, milestone, final
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Performance data
    total_volume_kg = Column(DECIMAL(15, 2))
    total_hours_worked = Column(DECIMAL(8, 2))
    quality_score = Column(DECIMAL(5, 2))  # 0-100 score
    timeliness_score = Column(DECIMAL(5, 2))  # 0-100 score
    
    # Fee calculation breakdown
    base_fee = Column(DECIMAL(15, 2))
    volume_bonus = Column(DECIMAL(15, 2), default=0)
    quality_bonus = Column(DECIMAL(15, 2), default=0)
    timeliness_bonus = Column(DECIMAL(15, 2), default=0)
    penalties = Column(DECIMAL(15, 2), default=0)
    adjustments = Column(DECIMAL(15, 2), default=0)
    
    # Totals
    gross_fee = Column(DECIMAL(15, 2), nullable=False)
    tax_amount = Column(DECIMAL(15, 2), default=0)
    net_fee = Column(DECIMAL(15, 2), nullable=False)
    
    # Calculation details
    calculation_data = Column(JSON)  # Detailed calculation breakdown
    evidence_data = Column(JSON)  # Supporting evidence and metrics
    
    # Processing status
    status = Column(String(50), default='calculated')  # calculated, approved, paid, disputed
    calculated_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    calculated_date = Column(DateTime, nullable=False)
    
    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Payment processing
    payment_transaction_id = Column(BigInteger, ForeignKey('epr_payment_transactions.id'))
    payment_date = Column(DateTime)
    payment_reference = Column(String(255))
    
    # Quality assurance
    is_audited = Column(Boolean, default=False)
    audited_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    audited_date = Column(DateTime)
    audit_findings = Column(Text)
    
    # Disputes and corrections
    is_disputed = Column(Boolean, default=False)
    dispute_reason = Column(Text)
    dispute_date = Column(DateTime)
    dispute_resolution = Column(Text)
    
    # Corrections
    is_corrected = Column(Boolean, default=False)
    correction_reason = Column(Text)
    corrected_amount = Column(DECIMAL(15, 2))
    corrected_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    corrected_date = Column(DateTime)
    
    # Additional information
    notes = Column(Text)
    extra_metadata = Column(JSON)
    
    # Relationships
    fee_setting = relationship("EprProjectUserAssistantFeeSetting", back_populates="fees")
    calculated_by = relationship("UserLocation", foreign_keys=[calculated_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    payment_transaction = relationship("EprPaymentTransaction")
    audited_by = relationship("UserLocation", foreign_keys=[audited_by_id])
    corrected_by = relationship("UserLocation", foreign_keys=[corrected_by_id])

class EprProjectMonthlyActualSpending(Base, BaseModel):
    """Monthly actual spending tracking for EPR projects"""
    __tablename__ = 'epr_project_monthly_actual_spending'
    
    # Project and period
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    year = Column(BigInteger, nullable=False)
    month = Column(BigInteger, nullable=False)  # 1-12
    
    # Budget categories
    personnel_costs = Column(DECIMAL(15, 2), default=0)
    equipment_costs = Column(DECIMAL(15, 2), default=0)
    operational_costs = Column(DECIMAL(15, 2), default=0)
    transportation_costs = Column(DECIMAL(15, 2), default=0)
    facility_costs = Column(DECIMAL(15, 2), default=0)
    
    # EPR specific costs
    collection_fees = Column(DECIMAL(15, 2), default=0)
    processing_fees = Column(DECIMAL(15, 2), default=0)
    disposal_fees = Column(DECIMAL(15, 2), default=0)
    auditing_fees = Column(DECIMAL(15, 2), default=0)
    compliance_costs = Column(DECIMAL(15, 2), default=0)
    
    # Assistant and consultant fees
    assistant_fees = Column(DECIMAL(15, 2), default=0)
    consultant_fees = Column(DECIMAL(15, 2), default=0)
    contractor_fees = Column(DECIMAL(15, 2), default=0)
    
    # Administrative costs
    administrative_costs = Column(DECIMAL(15, 2), default=0)
    reporting_costs = Column(DECIMAL(15, 2), default=0)
    certification_costs = Column(DECIMAL(15, 2), default=0)
    
    # Other categories
    marketing_costs = Column(DECIMAL(15, 2), default=0)
    training_costs = Column(DECIMAL(15, 2), default=0)
    technology_costs = Column(DECIMAL(15, 2), default=0)
    other_costs = Column(DECIMAL(15, 2), default=0)
    
    # Totals
    total_planned = Column(DECIMAL(15, 2), default=0)  # Budgeted amount
    total_actual = Column(DECIMAL(15, 2), nullable=False)  # Actual spending
    total_variance = Column(DECIMAL(15, 2))  # Difference (actual - planned)
    variance_percentage = Column(DECIMAL(5, 2))  # Variance as percentage
    
    # Cost breakdown by material type
    cost_by_material = Column(JSON)  # Detailed cost breakdown
    
    # Volume and efficiency metrics
    total_volume_processed = Column(DECIMAL(15, 2))  # kg or tonnes
    cost_per_kg = Column(DECIMAL(8, 4))  # Cost efficiency
    
    # Payment tracking
    total_payments_made = Column(DECIMAL(15, 2), default=0)
    outstanding_payments = Column(DECIMAL(15, 2), default=0)
    
    # Reporting and validation
    is_finalized = Column(Boolean, default=False)
    finalized_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    finalized_date = Column(DateTime)
    
    # Audit and verification
    is_audited = Column(Boolean, default=False)
    audited_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    audited_date = Column(DateTime)
    audit_notes = Column(Text)
    
    # Supporting documentation
    supporting_documents = Column(JSON)  # Array of document references
    receipt_count = Column(BigInteger, default=0)
    invoice_count = Column(BigInteger, default=0)
    
    # Forecast and projections
    next_month_forecast = Column(DECIMAL(15, 2))
    year_end_projection = Column(DECIMAL(15, 2))
    
    # Additional information
    notes = Column(Text)
    assumptions = Column(Text)  # Assumptions made in calculations
    risks = Column(Text)  # Financial risks identified
    
    # Metadata
    data_sources = Column(JSON)  # Sources of spending data
    calculation_methods = Column(JSON)  # Methods used for calculations
    extra_metadata = Column(JSON)
    
    # Relationships
    project = relationship("EprProject")
    finalized_by = relationship("UserLocation", foreign_keys=[finalized_by_id])
    audited_by = relationship("UserLocation", foreign_keys=[audited_by_id])