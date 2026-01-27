"""
Organization models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Numeric, Integer, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSON
from ..base import Base, BaseModel

class Organization(Base, BaseModel):
    __tablename__ = 'organizations'

    name = Column(String(255))
    description = Column(Text)
    organization_info_id = Column(BigInteger, ForeignKey('organization_info.id'))
    owner_id = Column(BigInteger, ForeignKey('user_locations.id'))  # Organization owner
    subscription_id = Column(BigInteger, ForeignKey('subscriptions.id'))  # Current subscription
    system_role_id = Column(BigInteger, ForeignKey('system_roles.id'))  # System permissions role
    allow_ai_audit = Column(Boolean, default=False)  # Permission to use AI for transaction auditing

    # AI Audit Configuration
    ai_audit_rule_set_id = Column(BigInteger, ForeignKey('ai_audit_rule_sets.id'), default=1)
    enable_ai_audit_response_setting = Column(Boolean, default=False)
    enable_ai_audit_api = Column(Boolean, default=False)

    # Custom API Configuration
    api_path = Column(String(100), unique=True, nullable=True)  # Unique path for /api/userapi/{api_path}/

    # Relationships
    organization_info = relationship("OrganizationInfo", back_populates="organization")
    owner = relationship("UserLocation", foreign_keys=[owner_id])
    subscriptions = relationship("Subscription", foreign_keys="Subscription.organization_id")  # All subscriptions
    system_role = relationship("SystemRole")
    ai_audit_rule_set = relationship("AiAuditRuleSet", back_populates="organizations", foreign_keys=[ai_audit_rule_set_id])
    ai_audit_response_patterns = relationship("AiAuditResponsePattern", back_populates="organization", cascade="all, delete-orphan")
    custom_apis = relationship("OrganizationCustomApi", back_populates="organization", cascade="all, delete-orphan")
    
    @property
    def current_subscription(self):
        """Get the current subscription by subscription_id"""
        if self.subscription_id:
            return next((sub for sub in self.subscriptions if sub.id == self.subscription_id), None)
        return None

class OrganizationInfo(Base, BaseModel):
    __tablename__ = 'organization_info'
    
    # Basic company information
    company_name = Column(String(255))
    company_name_th = Column(String(255))
    company_name_en = Column(String(255))
    display_name = Column(String(255))
    
    # Business details
    business_type = Column(Text)
    business_industry = Column(Text)
    business_sub_industry = Column(Text)
    account_type = Column(Text)
    
    # Legal and registration
    tax_id = Column(String(50))
    national_id = Column(String(50))
    business_registration_certificate = Column(Text)
    
    # Contact information
    phone_number = Column(String(50))
    company_phone = Column(String(50))
    company_email = Column(String(255))
    
    # Address information
    address = Column(Text)
    country_id = Column(BigInteger, ForeignKey('location_countries.id'))
    province_id = Column(BigInteger, ForeignKey('location_provinces.id'))
    district_id = Column(BigInteger, ForeignKey('location_districts.id'))
    subdistrict_id = Column(BigInteger, ForeignKey('location_subdistricts.id'))
    
    # Images and documents
    profile_image_url = Column(Text)
    company_logo_url = Column(Text)
    
    # Financial information
    footprint = Column(Numeric(10, 2))
    
    # Project and operational details
    project_id = Column(String(100))
    use_purpose = Column(Text)
    
    # Additional metadata
    application_date = Column(Text)  # When organization applied/registered
    
    # Relationships
    country = relationship("LocationCountry")
    province = relationship("LocationProvince")
    district = relationship("LocationDistrict")
    subdistrict = relationship("LocationSubdistrict")
    organization = relationship("Organization", back_populates="organization_info")


class OrganizationSetup(Base, BaseModel):
    """
    Versioned organization structure setup table
    Stores the hierarchical structure configuration for each organization
    Each update creates a new version rather than updating existing records
    """
    __tablename__ = 'organization_setup'

    # Organization reference
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)

    # Version management
    version = Column(String(20), nullable=False, default="1.0")

    # Simplified tree structure - rootNodes
    root_nodes = Column('root_nodes', JSON, nullable=True)

    # Hub structure
    hub_node = Column('hub_node', JSON, nullable=True)

    # Setup metadata
    setup_metadata = Column('metadata', JSON, nullable=True)

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])