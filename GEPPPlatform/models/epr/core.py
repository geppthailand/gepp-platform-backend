"""
EPR Core models - Organizations, brands, products, and projects
Extended Producer Responsibility core functionality
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from ..base import Base, BaseModel

class EprOrganization(Base, BaseModel):
    """EPR Organizations - Companies participating in EPR programs"""
    __tablename__ = 'epr_organizations'
    
    # Link to main organization
    main_organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Basic organization info
    name = Column(String(255), nullable=False)
    name_th = Column(String(255))
    name_en = Column(String(255))
    organization_type = Column(String(100))  # producer, importer, distributor, etc.
    
    # Registration details
    registration_number = Column(String(100), unique=True)
    license_number = Column(String(100))
    tax_id = Column(String(50))
    
    # Contact information
    contact_person = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    
    # Location
    country_id = Column(BigInteger, ForeignKey('location_countries.id'))
    province_id = Column(BigInteger, ForeignKey('location_provinces.id'))
    
    # EPR program details
    epr_program_start_date = Column(DateTime)
    epr_program_end_date = Column(DateTime)
    annual_production_volume = Column(DECIMAL(15, 2))  # tonnes per year
    
    # Status
    is_approved = Column(Boolean, default=False)
    approval_date = Column(DateTime)
    approval_notes = Column(Text)
    
    # Additional data
    extra_metadata = Column(JSON)
    notes = Column(Text)
    
    # Relationships
    main_organization = relationship("Organization")
    country = relationship("LocationCountry")
    province = relationship("LocationProvince")
    material_groups = relationship("EprOrganizationMaterialGroup", back_populates="organization")
    users = relationship("EprOrganizationUser", back_populates="organization")

class EprOrganizationMaterialGroup(Base, BaseModel):
    """Link between EPR organizations and material groups they handle"""
    __tablename__ = 'epr_organizations_material_groups'
    
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'), nullable=False)
    material_main_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=False)
    
    # Volume and targets
    annual_volume_target = Column(DECIMAL(15, 2))  # tonnes
    recycling_rate_target = Column(DECIMAL(5, 2))  # percentage
    
    # Fees and costs
    fee_per_tonne = Column(DECIMAL(10, 2))
    currency = Column(String(3), default='THB')
    
    # Status
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    
    # Relationships
    organization = relationship("EprOrganization", back_populates="material_groups")
    material_main = relationship("MainMaterial")

class EprOrganizationUser(Base, BaseModel):
    """Users associated with EPR organizations"""
    __tablename__ = 'epr_organizations_user'
    
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Role and permissions
    role = Column(String(100))  # admin, manager, reporter, viewer
    permissions = Column(JSON)  # Array of permission codes
    
    # Status
    is_active = Column(Boolean, default=True)
    joined_date = Column(DateTime)
    left_date = Column(DateTime)
    
    # Relationships
    organization = relationship("EprOrganization", back_populates="users")
    user_location = relationship("UserLocation")

class EprBrand(Base, BaseModel):
    """EPR Brands - Product brands under EPR programs"""
    __tablename__ = 'epr_brands'
    
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'), nullable=False)
    
    # Brand information
    name = Column(String(255), nullable=False)
    name_th = Column(String(255))
    name_en = Column(String(255))
    brand_code = Column(String(50))
    
    # Brand details
    logo_url = Column(Text)
    description = Column(Text)
    website = Column(String(255))
    
    # EPR specific
    is_local_brand = Column(Boolean, default=True)
    market_share = Column(DECIMAL(5, 2))  # percentage
    
    # Status
    is_active = Column(Boolean, default=True)
    launch_date = Column(DateTime)
    discontinue_date = Column(DateTime)
    
    # Relationships
    organization = relationship("EprOrganization")
    products = relationship("EprProduct", back_populates="brand")

class EprProduct(Base, BaseModel):
    """EPR Products - Individual products under EPR programs"""
    __tablename__ = 'epr_products'
    
    brand_id = Column(BigInteger, ForeignKey('epr_brands.id'), nullable=False)
    material_main_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=False)
    
    # Product information
    name = Column(String(255), nullable=False)
    product_code = Column(String(100))
    barcode = Column(String(50))
    
    # Product specifications
    weight_grams = Column(DECIMAL(8, 2))
    volume_ml = Column(DECIMAL(10, 2))
    packaging_type = Column(String(100))
    
    # EPR classification
    product_category = Column(String(100))
    recyclability_score = Column(DECIMAL(5, 2))  # 0-100 score
    recycled_content_percentage = Column(DECIMAL(5, 2))
    
    # Market data
    annual_volume = Column(DECIMAL(15, 2))  # units per year
    unit_price = Column(DECIMAL(10, 2))
    
    # Status
    is_active = Column(Boolean, default=True)
    launch_date = Column(DateTime)
    phase_out_date = Column(DateTime)
    
    # Additional data
    extra_metadata = Column(JSON)
    
    # Relationships
    brand = relationship("EprBrand", back_populates="products")
    material_main = relationship("MainMaterial")

class EprProject(Base, BaseModel):
    """EPR Projects - Specific EPR implementation projects"""
    __tablename__ = 'epr_project'
    
    # Project identification
    project_name = Column(String(255), nullable=False)
    project_code = Column(String(100), unique=True)
    project_type = Column(String(100))  # collection, recycling, education, etc.
    
    # Project scope
    organization_id = Column(BigInteger, ForeignKey('epr_organizations.id'))
    target_provinces = Column(JSON)  # Array of province IDs
    target_materials = Column(JSON)  # Array of material IDs
    
    # Project timeline
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    actual_start_date = Column(DateTime)
    actual_end_date = Column(DateTime)
    
    # Budget and targets
    total_budget = Column(DECIMAL(15, 2))
    target_volume = Column(DECIMAL(15, 2))  # tonnes
    target_recycling_rate = Column(DECIMAL(5, 2))  # percentage
    
    # Progress tracking
    current_volume = Column(DECIMAL(15, 2))
    current_recycling_rate = Column(DECIMAL(5, 2))
    completion_percentage = Column(DECIMAL(5, 2))
    
    # Project management
    project_manager_id = Column(BigInteger, ForeignKey('user_locations.id'))
    status = Column(String(50), default='planning')  # planning, active, paused, completed, cancelled
    
    # Location and logistics
    coordinate = Column(Geometry(geometry_type='POINT', srid=4326))
    coverage_area = Column(Geometry(geometry_type='POLYGON', srid=4326))
    
    # Documentation
    description = Column(Text)
    objectives = Column(Text)
    methodology = Column(Text)
    
    # Additional data
    extra_metadata = Column(JSON)
    
    # Relationships
    organization = relationship("EprOrganization")
    project_manager = relationship("UserLocation")
    files = relationship("EprProjectFile", back_populates="project")
    users = relationship("EprProjectUser", back_populates="project")
    logs = relationship("EprProjectLog", back_populates="project")

class EprProjectFile(Base, BaseModel):
    """Files associated with EPR projects"""
    __tablename__ = 'epr_project_files'
    
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    
    # File details
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(BigInteger)  # bytes
    file_type = Column(String(50))
    mime_type = Column(String(100))
    
    # File metadata
    title = Column(String(255))
    description = Column(Text)
    category = Column(String(100))  # proposal, report, data, contract, etc.
    version = Column(String(20))
    
    # Upload details
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    uploaded_date = Column(DateTime, nullable=False)
    
    # Access control
    is_public = Column(Boolean, default=False)
    access_level = Column(String(50), default='project_team')
    
    # Relationships
    project = relationship("EprProject", back_populates="files")
    uploaded_by = relationship("UserLocation")

class EprProjectUser(Base, BaseModel):
    """Users assigned to EPR projects"""
    __tablename__ = 'epr_project_users'
    
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Role and responsibilities
    role = Column(String(100))  # manager, coordinator, analyst, field_worker
    responsibilities = Column(Text)
    permissions = Column(JSON)
    
    # Assignment details
    assignment_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Workload
    allocation_percentage = Column(DECIMAL(5, 2))  # 0-100%
    hourly_rate = Column(DECIMAL(10, 2))
    
    # Relationships
    project = relationship("EprProject", back_populates="users")
    user_location = relationship("UserLocation")

class EprProjectUsersLog(Base, BaseModel):
    """Log of user assignments to projects"""
    __tablename__ = 'epr_project_users_log'
    
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Action details
    action = Column(String(50), nullable=False)  # assigned, role_changed, removed
    old_role = Column(String(100))
    new_role = Column(String(100))
    
    # Log details
    changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    changed_date = Column(DateTime, nullable=False)
    reason = Column(Text)
    
    # Relationships
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    changed_by = relationship("UserLocation", foreign_keys=[changed_by_id])

class EprProjectLog(Base, BaseModel):
    """Activity log for EPR projects"""
    __tablename__ = 'epr_project_log'
    
    project_id = Column(BigInteger, ForeignKey('epr_project.id'), nullable=False)
    
    # Log entry details
    activity_type = Column(String(100), nullable=False)
    activity_description = Column(Text, nullable=False)
    
    # Activity data
    old_value = Column(JSON)
    new_value = Column(JSON)
    
    # Log metadata
    logged_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    logged_date = Column(DateTime, nullable=False)
    ip_address = Column(String(45))
    
    # Additional context
    notes = Column(Text)
    extra_metadata = Column(JSON)
    
    # Relationships
    project = relationship("EprProject", back_populates="logs")
    logged_by = relationship("UserLocation")