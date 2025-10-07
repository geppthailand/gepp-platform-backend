"""
Main user-location model with organizational tree structure
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Enum, Integer, Table
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.types import DECIMAL
from ..base import Base, BaseModel, PlatformEnum

# Association table for subusers (many-to-many relationship)
user_subusers = Table(
    'user_subusers',
    Base.metadata,
    Column('parent_user_id', ForeignKey('user_locations.id'), primary_key=True),
    Column('subuser_id', ForeignKey('user_locations.id'), primary_key=True),
    Column('created_date', DateTime(timezone=True), nullable=False, server_default='now()'),
    Column('is_active', Boolean, nullable=False, default=True)
)

class UserLocation(Base, BaseModel):
    """
    Merged User and Location table that can serve as both user and location
    Users can login (is_user=True) and/or serve as waste transaction nodes (is_location=True)
    """
    __tablename__ = 'user_locations'
    
    # User flags
    is_user = Column(Boolean, nullable=False, default=False)  # Can login
    is_location = Column(Boolean, nullable=False, default=False)  # Can be waste transaction node
    
    # Basic Info (applicable to both user and location)
    name_th = Column(String(255))
    name_en = Column(String(255))
    display_name = Column(String(255))
    
    # User-specific authentication fields
    email = Column(String(255))
    is_email_active = Column(Boolean, nullable=False, default=False)
    email_notification = Column(String(255))
    phone = Column(String(255))
    username = Column(String(255))
    password = Column(String(255))  # Only for users
    facebook_id = Column(String(255))
    apple_id = Column(String(255))
    google_id_gmail = Column(String(255))
    
    # Platform and permissions
    platform = Column(Enum(PlatformEnum), nullable=False, default=PlatformEnum.NA)
    organization_role_id = Column(ForeignKey('organization_roles.id'))
    
    # Location and address information
    coordinate = Column(Text)  # Stored as "lat,lng" string
    address = Column(Text)
    postal_code = Column(String(10))
    country_id = Column(ForeignKey('location_countries.id'), nullable=False, default=212)
    province_id = Column(ForeignKey('location_provinces.id'))
    district_id = Column(ForeignKey('location_districts.id'))
    subdistrict_id = Column(ForeignKey('location_subdistricts.id'))
    
    # Business/Location specific fields
    business_type = Column(Text)
    business_industry = Column(Text)
    business_sub_industry = Column(Text)
    company_name = Column(Text)
    company_phone = Column(Text)
    company_email = Column(String(255))
    tax_id = Column(Text)
    
    # Waste management specific fields
    functions = Column(Text)  # Business unit functions (collector, recycler, sorter, etc.)
    type = Column(Text)  # Business unit type details
    hub_type = Column(Text)  # Hub type for waste management locations (from hubData.type)
    population = Column(Text)
    material = Column(Text)  # Materials handled
    
    # Profile and documents
    profile_image_url = Column(Text)
    national_id = Column(Text)
    national_card_image = Column(Text)
    business_registration_certificate = Column(Text)
    
    # Relationships and hierarchy
    organization_id = Column(ForeignKey('organizations.id'))
    parent_location_id = Column(ForeignKey('user_locations.id'))  # For location hierarchy
    created_by_id = Column(ForeignKey('user_locations.id'))
    auditor_id = Column(ForeignKey('user_locations.id'))
    
    # Organizational tree structure
    parent_user_id = Column(ForeignKey('user_locations.id'))  # Direct parent in organizational hierarchy
    organization_level = Column(Integer, default=0)  # Level in organizational hierarchy (0=root, 1=child, etc.)
    organization_path = Column(Text)  # Materialized path for quick hierarchy queries (e.g., "/1/5/12/")
    
    # Legacy subusers field (can store JSON array of subuser IDs for backward compatibility)
    sub_users = Column(JSON)  # JSON array of subuser IDs for backward compatibility

    # Location members (user assignments for locations)
    members = Column(JSONB)  # JSONB array of member objects with user_id and role
    
    # Localization
    locale = Column(String(15), default='TH')
    nationality_id = Column(ForeignKey('nationalities.id'))
    currency_id = Column(ForeignKey('currencies.id'), nullable=False, default=12)
    phone_code_id = Column(ForeignKey('phone_number_country_code.id'))
    
    # Additional fields
    note = Column(Text)
    expired_date = Column(DateTime)
    footprint = Column(DECIMAL(10, 2))
    
    # Relationships
    organization_role = relationship("OrganizationRole")
    country = relationship("LocationCountry")
    province = relationship("LocationProvince")
    district = relationship("LocationDistrict")
    subdistrict = relationship("LocationSubdistrict")
    nationality = relationship("Nationality")
    currency = relationship("Currency")
    phone_code = relationship("PhoneNumberCountryCode")
    
    # Self-referencing relationships for location hierarchy
    parent_location = relationship("UserLocation", remote_side="UserLocation.id", foreign_keys=[parent_location_id])
    created_by = relationship("UserLocation", remote_side="UserLocation.id", foreign_keys=[created_by_id])
    auditor = relationship("UserLocation", remote_side="UserLocation.id", foreign_keys=[auditor_id])
    
    # Organizational hierarchy relationships
    parent_user = relationship("UserLocation", remote_side="UserLocation.id", foreign_keys=[parent_user_id], back_populates="direct_children")
    direct_children = relationship("UserLocation", foreign_keys=[parent_user_id], back_populates="parent_user")
    
    # Many-to-many relationship for subusers (flexible organizational structure)
    subusers = relationship(
        "UserLocation",
        secondary=user_subusers,
        primaryjoin='UserLocation.id == user_subusers.c.parent_user_id',
        secondaryjoin='UserLocation.id == user_subusers.c.subuser_id',
        back_populates="parent_users"
    )
    
    parent_users = relationship(
        "UserLocation",
        secondary=user_subusers,
        primaryjoin='UserLocation.id == user_subusers.c.subuser_id',
        secondaryjoin='UserLocation.id == user_subusers.c.parent_user_id',
        back_populates="subusers"
    )
    
    # IoT Scale relationships (added for IoT integration)
    owned_iot_scales = relationship(
        "IoTScale", 
        foreign_keys="IoTScale.owner_user_location_id",
        back_populates="owner"
    )
    
    iot_scales_at_location = relationship(
        "IoTScale", 
        foreign_keys="IoTScale.location_point_id",
        back_populates="location"
    )
    
    # Methods for organizational tree management
    def add_subuser(self, subuser):
        """Add a subuser to this user's organization"""
        if subuser not in self.subusers:
            self.subusers.append(subuser)
            # Update organizational hierarchy
            subuser.parent_user_id = self.id
            subuser.organization_level = self.organization_level + 1
            subuser.organization_path = f"{self.organization_path}{self.id}/"
    
    def remove_subuser(self, subuser):
        """Remove a subuser from this user's organization"""
        if subuser in self.subusers:
            self.subusers.remove(subuser)
            # Reset organizational hierarchy for removed subuser
            subuser.parent_user_id = None
            subuser.organization_level = 0
            subuser.organization_path = f"/{subuser.id}/"
    
    def get_all_descendants(self, session):
        """Get all descendants in the organizational tree"""
        from sqlalchemy import text
        
        # Use recursive CTE to get all descendants
        query = text("""
            WITH RECURSIVE org_tree AS (
                SELECT id, parent_user_id, organization_level, name_en, display_name
                FROM user_locations
                WHERE id = :user_id
                
                UNION ALL
                
                SELECT ul.id, ul.parent_user_id, ul.organization_level, ul.name_en, ul.display_name
                FROM user_locations ul
                INNER JOIN org_tree ot ON ul.parent_user_id = ot.id
                WHERE ul.is_active = true
            )
            SELECT * FROM org_tree WHERE id != :user_id
        """)
        
        return session.execute(query, {"user_id": self.id}).fetchall()
    
    def get_organization_root(self, session):
        """Get the root user of this organizational tree"""
        current = self
        while current.parent_user_id is not None:
            current = session.query(UserLocation).get(current.parent_user_id)
        return current
    
    def update_organization_path(self, session):
        """Update the materialized path for this user and all descendants"""
        if self.parent_user_id is None:
            # Root user
            self.organization_path = f"/{self.id}/"
            self.organization_level = 0
        else:
            parent = session.query(UserLocation).get(self.parent_user_id)
            self.organization_path = f"{parent.organization_path}{self.id}/"
            self.organization_level = parent.organization_level + 1
        
        # Update all direct children
        for child in self.direct_children:
            child.update_organization_path(session)