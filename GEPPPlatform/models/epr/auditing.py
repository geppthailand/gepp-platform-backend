"""
EPR Auditing and Logistics models
Auditor assignments, recycler auditing, logistics management
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel

class EprAuditorTransactionAssignment(Base, BaseModel):
    """Assignment of auditors to transactions for verification"""
    __tablename__ = 'epr_auditor_transaction_assignment'
    
    # Assignment details
    transaction_id = Column(BigInteger, ForeignKey('transactions.id'), nullable=False)
    auditor_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    assigned_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Assignment metadata
    assignment_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime)
    completion_date = Column(DateTime)
    
    # Audit scope
    audit_type = Column(String(100))  # weight_verification, quality_check, compliance
    audit_priority = Column(String(50), default='normal')  # low, normal, high, urgent
    audit_scope = Column(Text)  # Description of what needs to be audited
    
    # Status tracking
    status = Column(String(50), default='assigned')  # assigned, in_progress, completed, cancelled
    progress_percentage = Column(DECIMAL(5, 2), default=0)
    
    # Results
    audit_result = Column(String(50))  # passed, failed, conditional, pending
    findings = Column(Text)
    recommendations = Column(Text)
    
    # Documentation
    audit_report_url = Column(Text)
    evidence_files = Column(JSON)  # Array of file URLs
    
    # Follow-up
    requires_followup = Column(Boolean, default=False)
    followup_date = Column(DateTime)
    followup_notes = Column(Text)
    
    # Additional data
    extra_metadata = Column(JSON)
    
    # Relationships
    transaction = relationship("Transaction")
    auditor = relationship("UserLocation", foreign_keys=[auditor_id])
    assigned_by = relationship("UserLocation", foreign_keys=[assigned_by_id])
    logs = relationship("EprAuditorTransactionAssignInfoLog", back_populates="assignment")

class EprAuditorTransactionAssignInfoLog(Base, BaseModel):
    """Log of changes to auditor transaction assignments"""
    __tablename__ = 'epr_auditor_transaction_assign_info_log'
    
    assignment_id = Column(BigInteger, ForeignKey('epr_auditor_transaction_assignment.id'), nullable=False)
    
    # Change details
    action = Column(String(100), nullable=False)  # assigned, status_changed, completed, etc.
    field_name = Column(String(100))
    old_value = Column(Text)
    new_value = Column(Text)
    
    # Log metadata
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    changed_date = Column(DateTime, nullable=False)
    
    # Additional context
    reason = Column(Text)
    notes = Column(Text)
    ip_address = Column(String(45))
    
    # Relationships
    assignment = relationship("EprAuditorTransactionAssignment", back_populates="logs")
    changed_by = relationship("UserLocation")

class EprRecyclerAuditDoc(Base, BaseModel):
    """Documents for recycler auditing process"""
    __tablename__ = 'epr_recycler_audit_doc'
    
    # Recycler information
    recycler_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    audit_cycle = Column(String(50))  # annual, quarterly, monthly
    audit_year = Column(BigInteger)
    
    # Document details
    document_type = Column(String(100))  # license, certification, process_doc, etc.
    document_name = Column(String(255), nullable=False)
    document_path = Column(Text, nullable=False)
    
    # Document metadata
    version = Column(String(20))
    issue_date = Column(DateTime)
    expiry_date = Column(DateTime)
    
    # Submission details
    submitted_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    submitted_date = Column(DateTime, nullable=False)
    submission_status = Column(String(50), default='pending')
    
    # Review details
    reviewed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    reviewed_date = Column(DateTime)
    review_status = Column(String(50))  # approved, rejected, needs_revision
    review_notes = Column(Text)
    
    # Compliance
    is_compliant = Column(Boolean)
    compliance_notes = Column(Text)
    next_review_date = Column(DateTime)
    
    # File properties
    file_size = Column(BigInteger)
    file_type = Column(String(50))
    checksum = Column(String(255))  # For integrity verification
    
    # Relationships
    recycler = relationship("UserLocation", foreign_keys=[recycler_id])
    submitted_by = relationship("UserLocation", foreign_keys=[submitted_by_id])
    reviewed_by = relationship("UserLocation", foreign_keys=[reviewed_by_id])

class EprRecyclerAuditPreset(Base, BaseModel):
    """Preset configurations for recycler audits"""
    __tablename__ = 'epr_recycler_audit_preset'
    
    # Preset identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Applicability
    material_types = Column(JSON)  # Array of material type IDs
    recycler_categories = Column(JSON)  # Array of recycler categories
    facility_types = Column(JSON)  # Array of facility types
    
    # Audit requirements
    required_documents = Column(JSON)  # Array of required document types
    inspection_checklist = Column(JSON)  # Checklist items
    performance_metrics = Column(JSON)  # KPIs to measure
    
    # Frequency and timing
    audit_frequency = Column(String(50))  # annual, semi_annual, quarterly
    notice_period_days = Column(BigInteger, default=30)
    completion_deadline_days = Column(BigInteger, default=14)
    
    # Scoring and evaluation
    scoring_method = Column(String(100))  # weighted, simple, pass_fail
    pass_threshold = Column(DECIMAL(5, 2))  # Minimum score to pass
    weight_factors = Column(JSON)  # Weights for different criteria
    
    # Template settings
    report_template = Column(Text)  # Template for audit reports
    certificate_template = Column(Text)  # Template for compliance certificates
    
    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    
    # Version control
    version = Column(String(20), default='1.0')
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    last_modified_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    last_modified_by = relationship("UserLocation", foreign_keys=[last_modified_by_id])

class EprLogisticAssistantFeeSettings(Base, BaseModel):
    """Fee settings for logistic assistant services"""
    __tablename__ = 'epr_logistic_assistant_fee_settings'
    
    # Service identification
    service_name = Column(String(255), nullable=False)
    service_code = Column(String(50), unique=True)
    service_category = Column(String(100))  # collection, transport, processing
    
    # Geographic scope
    coverage_areas = Column(JSON)  # Array of province/district IDs
    service_zones = Column(JSON)  # Custom zone definitions
    
    # Fee structure
    base_fee = Column(DECIMAL(10, 2))
    currency = Column(String(3), default='THB')
    fee_type = Column(String(50))  # fixed, per_kg, per_km, per_hour
    
    # Variable pricing
    weight_tiers = Column(JSON)  # Different rates for weight ranges
    distance_tiers = Column(JSON)  # Different rates for distance ranges
    volume_discounts = Column(JSON)  # Bulk discounts
    
    # Service parameters
    minimum_order = Column(DECIMAL(10, 2))  # Minimum weight/volume
    maximum_order = Column(DECIMAL(10, 2))  # Maximum capacity
    service_time_hours = Column(DECIMAL(4, 2))  # Standard service time
    
    # Effective period
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime)
    
    # Additional charges
    fuel_surcharge_rate = Column(DECIMAL(5, 2))  # Percentage
    rush_order_multiplier = Column(DECIMAL(3, 2))  # Multiplier for urgent orders
    weekend_multiplier = Column(DECIMAL(3, 2))  # Weekend surcharge
    
    # Terms and conditions
    payment_terms = Column(String(100))  # net_30, cod, prepaid
    cancellation_policy = Column(Text)
    service_level_agreement = Column(Text)
    
    # Status
    is_active = Column(Boolean, default=True)
    requires_approval = Column(Boolean, default=False)
    
    # Audit trail
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    
    # Relationships
    created_by = relationship("UserLocation", foreign_keys=[created_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])

class EprProvinceDistance(Base, BaseModel):
    """Distance matrix between provinces for logistics calculations"""
    __tablename__ = 'epr_province_distance'
    
    # Province pair
    origin_province_id = Column(BigInteger, ForeignKey('location_provinces.id'), nullable=False)
    destination_province_id = Column(BigInteger, ForeignKey('location_provinces.id'), nullable=False)
    
    # Distance measurements
    road_distance_km = Column(DECIMAL(8, 2))  # Actual road distance
    straight_line_distance_km = Column(DECIMAL(8, 2))  # Direct distance
    
    # Travel information
    estimated_travel_time_hours = Column(DECIMAL(4, 2))
    fuel_cost_estimate = Column(DECIMAL(8, 2))
    toll_cost_estimate = Column(DECIMAL(8, 2))
    
    # Route details
    major_highways = Column(JSON)  # List of highways used
    border_crossings = Column(JSON)  # International borders if any
    difficult_terrain = Column(Boolean, default=False)
    
    # Logistics factors
    truck_restrictions = Column(JSON)  # Weight/size restrictions
    seasonal_restrictions = Column(JSON)  # Monsoon, flooding impacts
    preferred_routes = Column(JSON)  # Recommended route waypoints
    
    # Data sources
    data_source = Column(String(100))  # google_maps, government_data, survey
    last_updated = Column(DateTime)
    accuracy_rating = Column(DECIMAL(3, 2))  # 1-5 accuracy score
    
    # Additional costs
    driver_accommodation_cost = Column(DECIMAL(8, 2))
    parking_fees = Column(DECIMAL(8, 2))
    permit_costs = Column(DECIMAL(8, 2))
    
    # Relationships
    origin_province = relationship("LocationProvince", foreign_keys=[origin_province_id])
    destination_province = relationship("LocationProvince", foreign_keys=[destination_province_id])

class EprSorterType(Base, BaseModel):
    """Types of waste sorters in the EPR system"""
    __tablename__ = 'epr_sorter_types'
    
    # Sorter type identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    description = Column(Text)
    
    # Capabilities
    material_types = Column(JSON)  # Types of materials this sorter can handle
    capacity_tons_per_day = Column(DECIMAL(8, 2))
    accuracy_percentage = Column(DECIMAL(5, 2))
    
    # Technology requirements
    technology_type = Column(String(100))  # manual, optical, magnetic, etc.
    equipment_required = Column(JSON)  # List of required equipment
    skill_requirements = Column(JSON)  # Required operator skills
    
    # Economic factors
    setup_cost = Column(DECIMAL(12, 2))
    operational_cost_per_day = Column(DECIMAL(8, 2))
    maintenance_cost_per_month = Column(DECIMAL(8, 2))
    
    # Performance metrics
    throughput_rate = Column(DECIMAL(8, 2))  # Kg per hour
    contamination_reduction = Column(DECIMAL(5, 2))  # Percentage
    quality_improvement = Column(DECIMAL(5, 2))  # Grade improvement
    
    # Environmental impact
    energy_consumption_kwh = Column(DECIMAL(8, 2))  # Per tonne processed
    water_usage_liters = Column(DECIMAL(8, 2))  # Per tonne processed
    waste_generation = Column(DECIMAL(5, 2))  # Percentage of waste generated
    
    # Certification and standards
    certification_required = Column(Boolean, default=False)
    standard_compliance = Column(JSON)  # Array of standards to comply with
    
    # Status
    is_active = Column(Boolean, default=True)
    is_recommended = Column(Boolean, default=False)

class EprSelfRegistrationUrl(Base, BaseModel):
    """Self-registration URLs for different EPR stakeholders"""
    __tablename__ = 'epr_self_registration_urls'
    
    # URL identification
    name = Column(String(255), nullable=False)
    url_code = Column(String(50), unique=True)
    registration_url = Column(Text, nullable=False)
    
    # Target audience
    target_user_type = Column(String(100))  # producer, recycler, collector, etc.
    organization_types = Column(JSON)  # Array of applicable organization types
    
    # Geographic restrictions
    allowed_countries = Column(JSON)  # Array of country IDs
    allowed_provinces = Column(JSON)  # Array of province IDs
    
    # Registration parameters
    required_fields = Column(JSON)  # Fields required for registration
    optional_fields = Column(JSON)  # Optional fields
    default_values = Column(JSON)  # Pre-populated values
    
    # Validation and approval
    auto_approval = Column(Boolean, default=False)
    approval_workflow_id = Column(BigInteger)
    verification_required = Column(Boolean, default=True)
    
    # Access control
    is_public = Column(Boolean, default=True)
    access_code_required = Column(Boolean, default=False)
    allowed_domains = Column(JSON)  # Email domain restrictions
    
    # Branding and customization
    page_title = Column(String(255))
    welcome_message = Column(Text)
    logo_url = Column(Text)
    theme_settings = Column(JSON)
    
    # Tracking and analytics
    total_registrations = Column(BigInteger, default=0)
    successful_registrations = Column(BigInteger, default=0)
    last_registration_date = Column(DateTime)
    
    # Validity period
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime)
    max_registrations = Column(BigInteger)  # Registration limit
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Audit
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    created_date = Column(DateTime, nullable=False)
    
    # Relationships
    created_by = relationship("UserLocation")

class EprUserLafInfo(Base, BaseModel):
    """LAF (Logistics Assistant Fee) information for EPR users"""
    __tablename__ = 'epr_user_laf_info'
    
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # LAF registration
    laf_registration_number = Column(String(100), unique=True)
    registration_date = Column(DateTime)
    registration_status = Column(String(50), default='pending')
    
    # Service provider details
    provider_name = Column(String(255))
    provider_type = Column(String(100))  # individual, company, cooperative
    service_areas = Column(JSON)  # Geographic service coverage
    
    # Capacity and capabilities
    vehicle_capacity_kg = Column(DECIMAL(8, 2))
    daily_capacity_kg = Column(DECIMAL(8, 2))
    storage_capacity_kg = Column(DECIMAL(8, 2))
    
    # Service offerings
    collection_services = Column(JSON)  # Types of collection services
    transport_services = Column(JSON)  # Types of transport services
    processing_services = Column(JSON)  # Types of processing services
    
    # Pricing structure
    base_rate_per_kg = Column(DECIMAL(6, 4))
    distance_rate_per_km = Column(DECIMAL(6, 4))
    minimum_order_kg = Column(DECIMAL(8, 2))
    volume_discounts = Column(JSON)
    
    # Operating schedule
    operating_hours = Column(JSON)  # Daily operating hours
    operating_days = Column(JSON)  # Days of the week
    holiday_schedule = Column(JSON)  # Holiday availability
    
    # Equipment and resources
    vehicle_details = Column(JSON)  # Vehicle specifications
    equipment_list = Column(JSON)  # Processing equipment
    staff_count = Column(BigInteger)
    
    # Performance metrics
    service_rating = Column(DECIMAL(3, 2))  # 1-5 rating
    total_orders_completed = Column(BigInteger, default=0)
    total_volume_processed = Column(DECIMAL(15, 2), default=0)
    
    # Financial information
    monthly_revenue = Column(DECIMAL(12, 2))
    fee_payment_status = Column(String(50), default='current')
    last_payment_date = Column(DateTime)
    
    # Compliance and certification
    certifications = Column(JSON)  # Array of certifications
    insurance_details = Column(JSON)  # Insurance information
    license_numbers = Column(JSON)  # Various license numbers
    
    # Status and availability
    is_available = Column(Boolean, default=True)
    availability_notes = Column(Text)
    temporary_unavailable_until = Column(DateTime)
    
    # Additional information
    specializations = Column(JSON)  # Special capabilities or focus areas
    preferred_materials = Column(JSON)  # Preferred material types
    exclusions = Column(JSON)  # Materials or services not provided
    
    # Contact preferences
    preferred_contact_method = Column(String(50))  # phone, email, sms
    contact_hours = Column(JSON)  # Preferred contact hours
    
    # Relationships
    user_location = relationship("UserLocation")