"""
GRI Standards and Aspects definitions
Defines GRI 306 waste management standards structure
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from ..base import Base, BaseModel

class GriStandardType(enum.Enum):
    """GRI 306 Standard Types"""
    GRI_306_1 = 'GRI_306_1'  # Waste generation and significant waste-related impacts
    GRI_306_2 = 'GRI_306_2'  # Management of significant waste-related impacts
    GRI_306_3 = 'GRI_306_3'  # Waste generated
    GRI_306_4 = 'GRI_306_4'  # Waste diverted from disposal
    GRI_306_5 = 'GRI_306_5'  # Waste directed to disposal

class GriStandard(Base, BaseModel):
    """GRI Standards definition and configuration"""
    __tablename__ = 'gri_standards'
    
    # Standard identification
    standard_code = Column(String(20), unique=True, nullable=False)  # e.g., "306-1"
    standard_type = Column(SQLEnum(GriStandardType), nullable=False)
    version = Column(String(20), default='2020')
    
    # Standard details
    title = Column(String(500), nullable=False)
    description = Column(Text)
    requirements = Column(Text)  # Reporting requirements
    
    # Category and scope
    category = Column(String(100))  # Environmental, Social, Governance
    subcategory = Column(String(100))  # Waste, Emissions, Water, etc.
    
    # Applicability
    is_mandatory = Column(Boolean, default=False)
    applies_to_industries = Column(JSON)  # List of applicable industries
    geographic_scope = Column(String(100))  # Global, Regional, National
    
    # Measurement guidelines
    measurement_unit = Column(String(50))  # tonnes, kg, percentage, etc.
    calculation_methodology = Column(Text)
    data_sources = Column(JSON)  # Recommended data sources
    
    # Reporting frequency
    reporting_frequency = Column(String(50))  # Annual, Quarterly, Monthly
    
    # Status
    is_active = Column(Boolean, default=True)
    effective_from = Column(DateTime)
    effective_to = Column(DateTime)
    
    # Documentation
    guidance_document_url = Column(Text)
    template_url = Column(Text)
    
    # Relationships
    aspects = relationship("GriAspect", back_populates="standard")

class GriAspect(Base, BaseModel):
    """Specific aspects within GRI standards"""
    __tablename__ = 'gri_aspects'
    
    standard_id = Column(BigInteger, ForeignKey('gri_standards.id'), nullable=False)
    
    # Aspect identification
    aspect_code = Column(String(50), unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Measurement details
    metric_name = Column(String(255))
    metric_type = Column(String(50))  # quantitative, qualitative, binary
    unit_of_measure = Column(String(50))
    
    # Data collection
    data_points = Column(JSON)  # Required data points for this aspect
    calculation_formula = Column(Text)
    
    # Validation rules
    validation_rules = Column(JSON)
    minimum_value = Column(String(50))
    maximum_value = Column(String(50))
    
    # Reporting requirements
    is_required = Column(Boolean, default=True)
    requires_third_party_verification = Column(Boolean, default=False)
    
    # Examples and guidance
    examples = Column(JSON)
    best_practices = Column(Text)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    standard = relationship("GriStandard", back_populates="aspects")

class GriIndicator(Base, BaseModel):
    """Key Performance Indicators for GRI standards"""
    __tablename__ = 'gri_indicators'
    
    aspect_id = Column(BigInteger, ForeignKey('gri_aspects.id'), nullable=False)
    
    # Indicator details
    indicator_code = Column(String(50), unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Calculation
    calculation_method = Column(String(100))  # sum, average, percentage, ratio
    aggregation_method = Column(String(100))  # by_period, by_location, by_material
    
    # Thresholds and benchmarks
    industry_benchmark = Column(JSON)  # Industry standard values
    threshold_good = Column(String(50))  # Good performance threshold
    threshold_acceptable = Column(String(50))  # Acceptable threshold
    threshold_poor = Column(String(50))  # Poor performance threshold
    
    # Trending
    trend_direction_positive = Column(String(20))  # increase, decrease, stable
    year_over_year_target = Column(String(50))  # % change target
    
    # Display settings
    display_format = Column(String(50))  # number, percentage, currency
    decimal_places = Column(BigInteger, default=2)
    chart_type = Column(String(50))  # bar, line, pie, gauge
    
    # Status
    is_primary = Column(Boolean, default=False)  # Primary KPI for the aspect
    is_active = Column(Boolean, default=True)
    
    # Relationships
    aspect = relationship("GriAspect")

class GriMaterialCategory(Base, BaseModel):
    """Material categories for GRI waste reporting"""
    __tablename__ = 'gri_material_categories'
    
    # Category identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    
    # GRI classification
    is_hazardous = Column(Boolean, default=False)
    disposal_method = Column(String(100))  # recycling, landfill, incineration, etc.
    recovery_potential = Column(String(50))  # high, medium, low, none
    
    # Mapping to core materials
    material_ids = Column(JSON)  # Array of material IDs from materials table
    
    # Environmental impact
    environmental_impact_score = Column(String(50))  # 1-10 scale
    carbon_footprint_factor = Column(String(50))  # kg CO2 per tonne
    
    # Reporting configuration
    include_in_306_3 = Column(Boolean, default=True)  # Include in waste generated
    include_in_306_4 = Column(Boolean, default=False)  # Include in diverted
    include_in_306_5 = Column(Boolean, default=False)  # Include in disposal
    
    # Additional properties
    description = Column(Text)
    examples = Column(JSON)
    
    # Status
    is_active = Column(Boolean, default=True)

class GriReportingTemplate(Base, BaseModel):
    """Templates for GRI reporting"""
    __tablename__ = 'gri_reporting_templates'
    
    # Template identification
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True)
    standard_type = Column(SQLEnum(GriStandardType), nullable=False)
    
    # Template configuration
    template_structure = Column(JSON)  # JSON structure of the template
    required_fields = Column(JSON)  # Required fields for this template
    optional_fields = Column(JSON)  # Optional fields
    
    # Calculations
    calculation_rules = Column(JSON)  # Rules for automatic calculations
    aggregation_rules = Column(JSON)  # How to aggregate data
    
    # Validation
    validation_schema = Column(JSON)  # JSON schema for validation
    compliance_checks = Column(JSON)  # Compliance verification rules
    
    # Export configuration
    export_formats = Column(JSON)  # Supported export formats
    export_template_files = Column(JSON)  # Template file references
    
    # Usage
    industry_specific = Column(String(255))  # Specific industry if applicable
    organization_size = Column(String(50))  # small, medium, large, enterprise
    
    # Version control
    version = Column(String(20), default='1.0')
    is_default = Column(Boolean, default=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    created_by = relationship("UserLocation")