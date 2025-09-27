"""
EPR Pro models - Producer responsibility organization models
Material groups, tags, and user management for EPR programs
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel

class EprPro(Base, BaseModel):
    """EPR PRO (Producer Responsibility Organization) - Main PRO entities"""
    __tablename__ = 'epr_pro'
    
    # PRO identification
    name = Column(String(255), nullable=False)
    name_th = Column(String(255))
    name_en = Column(String(255))
    pro_code = Column(String(100), unique=True)
    
    # Registration and legal
    registration_number = Column(String(100))
    license_number = Column(String(100))
    tax_id = Column(String(50))
    
    # Contact information
    contact_person = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    website = Column(String(255))
    address = Column(Text)
    
    # Location
    country_id = Column(BigInteger, ForeignKey('location_countries.id'))
    province_id = Column(BigInteger, ForeignKey('location_provinces.id'))
    
    # PRO details
    establishment_date = Column(DateTime)
    member_count = Column(BigInteger, default=0)
    total_volume_managed = Column(DECIMAL(15, 2))  # tonnes per year
    
    # Certification and compliance
    certification_level = Column(String(50))
    certification_date = Column(DateTime)
    certification_expiry = Column(DateTime)
    compliance_status = Column(String(50), default='pending')
    
    # Financial
    annual_revenue = Column(DECIMAL(15, 2))
    management_fee_percentage = Column(DECIMAL(5, 2))
    
    # Status
    is_active = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=False)
    approval_date = Column(DateTime)
    
    # Additional data
    description = Column(Text)
    objectives = Column(Text)
    extra_metadata = Column(JSON)
    
    # Relationships
    country = relationship("LocationCountry")
    province = relationship("LocationProvince")
    info = relationship("EprProInfo", back_populates="epr_pro", uselist=False)
    files = relationship("EprProFile", back_populates="epr_pro")
    material_groups = relationship("EprProMaterialGroup", back_populates="epr_pro")
    users = relationship("EprProUser", back_populates="epr_pro")

class EprProInfo(Base, BaseModel):
    """Detailed information for EPR PRO organizations"""
    __tablename__ = 'epr_pro_info'
    
    epr_pro_id = Column(BigInteger, ForeignKey('epr_pro.id'), nullable=False, unique=True)
    
    # Operational details
    operating_model = Column(String(100))  # collective, individual, hybrid
    service_areas = Column(JSON)  # Array of province/region IDs
    collection_methods = Column(JSON)  # Array of collection method codes
    
    # Performance metrics
    collection_rate = Column(DECIMAL(5, 2))  # percentage
    recycling_rate = Column(DECIMAL(5, 2))  # percentage
    recovery_rate = Column(DECIMAL(5, 2))  # percentage
    
    # Infrastructure
    collection_points = Column(BigInteger, default=0)
    processing_facilities = Column(BigInteger, default=0)
    partner_count = Column(BigInteger, default=0)
    
    # Reporting
    annual_report_url = Column(Text)
    sustainability_report_url = Column(Text)
    last_audit_date = Column(DateTime)
    next_audit_date = Column(DateTime)
    
    # Additional information
    special_programs = Column(JSON)
    certifications = Column(JSON)
    awards = Column(JSON)
    
    # Relationships
    epr_pro = relationship("EprPro", back_populates="info")

class EprProFile(Base, BaseModel):
    """Files associated with EPR PRO organizations"""
    __tablename__ = 'epr_pro_files'
    
    epr_pro_id = Column(BigInteger, ForeignKey('epr_pro.id'), nullable=False)
    
    # File details
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(50))
    file_size = Column(BigInteger)  # bytes
    
    # File metadata
    title = Column(String(255))
    description = Column(Text)
    category = Column(String(100))  # certificate, report, contract, etc.
    version = Column(String(20))
    
    # Upload details
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    uploaded_date = Column(DateTime, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=False)
    
    # Relationships
    epr_pro = relationship("EprPro", back_populates="files")
    uploaded_by = relationship("UserLocation")

class EprProMaterialGroup(Base, BaseModel):
    """Material groups managed by EPR PRO organizations"""
    __tablename__ = 'epr_pro_material_groups'
    
    epr_pro_id = Column(BigInteger, ForeignKey('epr_pro.id'), nullable=False)
    material_main_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=False)
    
    # Management details
    management_start_date = Column(DateTime)
    management_end_date = Column(DateTime)
    
    # Targets and performance
    annual_target_volume = Column(DECIMAL(15, 2))  # tonnes
    collection_target = Column(DECIMAL(5, 2))  # percentage
    recycling_target = Column(DECIMAL(5, 2))  # percentage
    
    # Current performance
    current_volume = Column(DECIMAL(15, 2))
    current_collection_rate = Column(DECIMAL(5, 2))
    current_recycling_rate = Column(DECIMAL(5, 2))
    
    # Financial
    fee_structure = Column(JSON)  # Complex fee structure
    total_fees_collected = Column(DECIMAL(15, 2))
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    epr_pro = relationship("EprPro", back_populates="material_groups")
    material_main = relationship("MainMaterial")
    users = relationship("EprProMaterialGroupUser", back_populates="material_group")
    tag_groups = relationship("EprProMaterialTagGroup", back_populates="material_group")

class EprProMaterialGroupUser(Base, BaseModel):
    """Users assigned to specific material groups"""
    __tablename__ = 'epr_pro_material_group_users'
    
    material_group_id = Column(BigInteger, ForeignKey('epr_pro_material_groups.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Role and responsibilities
    role = Column(String(100))  # manager, analyst, coordinator
    responsibilities = Column(Text)
    
    # Assignment details
    assignment_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Performance tracking
    target_volume = Column(DECIMAL(15, 2))
    achieved_volume = Column(DECIMAL(15, 2))
    performance_score = Column(DECIMAL(5, 2))
    
    # Relationships
    material_group = relationship("EprProMaterialGroup", back_populates="users")
    user_location = relationship("UserLocation")

class EprProMaterialTagGroup(Base, BaseModel):
    """Tag groups for categorizing materials within material groups"""
    __tablename__ = 'epr_pro_material_tag_groups'
    
    material_group_id = Column(BigInteger, ForeignKey('epr_pro_material_groups.id'), nullable=False)
    
    # Tag group details
    name = Column(String(255), nullable=False)
    description = Column(Text)
    color_code = Column(String(7))  # Hex color code
    
    # Categorization
    category = Column(String(100))  # packaging_type, product_category, etc.
    sort_order = Column(BigInteger, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    material_group = relationship("EprProMaterialGroup", back_populates="tag_groups")
    tags = relationship("EprProMaterialTag", back_populates="tag_group")

class EprProMaterialTag(Base, BaseModel):
    """Individual tags for materials"""
    __tablename__ = 'epr_pro_material_tags'
    
    tag_group_id = Column(BigInteger, ForeignKey('epr_pro_material_tag_groups.id'), nullable=False)
    
    # Tag details
    name = Column(String(255), nullable=False)
    code = Column(String(50))
    description = Column(Text)
    
    # Visual properties
    icon = Column(String(100))  # Icon name or URL
    color_code = Column(String(7))  # Hex color code
    
    # Tag properties
    is_mandatory = Column(Boolean, default=False)
    is_exclusive = Column(Boolean, default=False)  # Can't be combined with other tags
    weight_factor = Column(DECIMAL(5, 2), default=1.0)  # Multiplier for calculations
    
    # Status and ordering
    is_active = Column(Boolean, default=True)
    sort_order = Column(BigInteger, default=0)
    
    # Usage tracking
    usage_count = Column(BigInteger, default=0)
    last_used_date = Column(DateTime)
    
    # Relationships
    tag_group = relationship("EprProMaterialTagGroup", back_populates="tags")
    materials = relationship("EprProMaterial", back_populates="tag")

class EprProMaterial(Base, BaseModel):
    """Materials managed under EPR PRO programs"""
    __tablename__ = 'epr_pro_materials'
    
    epr_pro_id = Column(BigInteger, ForeignKey('epr_pro.id'), nullable=False)
    material_id = Column(BigInteger, ForeignKey('materials.id'), nullable=False)
    tag_id = Column(BigInteger, ForeignKey('epr_pro_material_tags.id'))
    
    # Material classification
    classification_code = Column(String(50))
    sub_category = Column(String(100))
    
    # Processing requirements
    processing_method = Column(String(100))
    quality_requirements = Column(Text)
    contamination_limits = Column(JSON)
    
    # Economic factors
    collection_cost_per_kg = Column(DECIMAL(8, 4))
    processing_cost_per_kg = Column(DECIMAL(8, 4))
    market_value_per_kg = Column(DECIMAL(8, 4))
    
    # Environmental impact
    carbon_footprint_per_kg = Column(DECIMAL(8, 4))  # kg CO2 equivalent
    recycling_efficiency = Column(DECIMAL(5, 2))  # percentage
    
    # Status
    is_priority = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Additional data
    extra_metadata = Column(JSON)
    notes = Column(Text)
    
    # Relationships
    epr_pro = relationship("EprPro")
    material = relationship("Material")
    tag = relationship("EprProMaterialTag", back_populates="materials")

class EprProUser(Base, BaseModel):
    """Users associated with EPR PRO organizations"""
    __tablename__ = 'epr_pro_users'
    
    epr_pro_id = Column(BigInteger, ForeignKey('epr_pro.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Role and access
    role = Column(String(100))  # admin, manager, analyst, reporter
    permissions = Column(JSON)  # Array of permission codes
    access_level = Column(String(50), default='standard')  # standard, elevated, restricted
    
    # Employment details
    position = Column(String(255))
    department = Column(String(100))
    hire_date = Column(DateTime)
    employment_type = Column(String(50))  # full_time, part_time, contract
    
    # Contact and location
    work_phone = Column(String(50))
    work_email = Column(String(255))
    office_location = Column(String(255))
    
    # Performance and targets
    annual_target = Column(DECIMAL(15, 2))  # Individual target in tonnes
    current_achievement = Column(DECIMAL(15, 2))
    performance_rating = Column(DECIMAL(3, 2))  # 1-5 scale
    
    # Status
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    activation_date = Column(DateTime)
    deactivation_date = Column(DateTime)
    
    # Additional information
    bio = Column(Text)
    specializations = Column(JSON)  # Areas of expertise
    certifications = Column(JSON)  # Professional certifications
    
    # Relationships
    epr_pro = relationship("EprPro", back_populates="users")
    user_location = relationship("UserLocation")