"""
Reference data models - Banks, currencies, materials, etc.
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Boolean, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.types import DECIMAL
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel

class Bank(Base, BaseModel):
    __tablename__ = 'banks'
    
    country_id = Column(BigInteger, nullable=False, default=212)
    bank_code = Column(String(10))
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    abbreviation = Column(String(10))
    valid_account_number = Column(String(255))

class Currency(Base, BaseModel):
    __tablename__ = 'currencies'
    
    name = Column(String(255))
    code = Column(String(10))
    symbol = Column(String(10))

class Locale(Base, BaseModel):
    __tablename__ = 'locales'
    
    name = Column(String(255))
    code = Column(String(10))

class MaterialCategory(Base, BaseModel):
    __tablename__ = 'material_categories'

    name_th = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)
    description = Column(Text)
    color = Column(String(7), nullable=False, default='#808080')  # Hex color code

class MainMaterial(Base, BaseModel):
    __tablename__ = 'main_materials'

    name_th = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False)
    name_local = Column(String(255))
    code = Column(String(50))
    color = Column(String(7), nullable=False, default='#808080')
    display_order = Column(BigInteger, nullable=False, default=0)

    # Tag-based system support - using actual database column name
    material_tag_groups = Column(ARRAY(BigInteger), nullable=False, default=[])  # Array of material_tag_group IDs

class MaterialTag(Base, BaseModel):
    __tablename__ = 'material_tags'

    name = Column(String(255), nullable=False)
    description = Column(Text)
    color = Column(String(7), nullable=False, default='#808080')  # Hex color code
    is_global = Column(Boolean, nullable=False, default=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)

    # Relationships
    organization = relationship("Organization")

class MaterialTagGroup(Base, BaseModel):
    __tablename__ = 'material_tag_groups'

    name = Column(String(255), nullable=False)
    description = Column(Text)
    color = Column(String(7), nullable=False, default='#808080')  # Hex color code
    is_global = Column(Boolean, nullable=False, default=False)
    tags = Column(ARRAY(BigInteger), nullable=False, default=[])  # Array of material_tag ids
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)

    # Relationships
    organization = relationship("Organization")

# Base Materials class removed - using main_materials instead

class Material(Base, BaseModel):
    __tablename__ = 'materials'

    # Legacy structure (maintained for backward compatibility)
    category_id = Column(BigInteger, ForeignKey('material_categories.id'), nullable=True)
    main_material_id = Column(BigInteger, ForeignKey('main_materials.id'), nullable=True)

    # New tag-based structure (using main_material_id instead of base_material_id)
    tags = Column(JSONB, nullable=False, default=[])  # Array of tuples [(tag_group_id, tag_id), ...]

    # Multi-tenant support
    is_global = Column(Boolean, nullable=False, default=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)

    # Material properties
    unit_name_th = Column(String(255), nullable=False)
    unit_name_en = Column(String(255), nullable=False)
    unit_weight = Column(DECIMAL(10, 3), nullable=False, default=1)
    color = Column(String(7), nullable=False, default='#808080')  # Hex color code
    calc_ghg = Column(DECIMAL(10, 3), nullable=False, default=0)
    name_th = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False)

    # Relationships
    category = relationship("MaterialCategory")
    main_material = relationship("MainMaterial")
    organization = relationship("Organization")

class Nationality(Base, BaseModel):
    __tablename__ = 'nationalities'
    
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))

class PhoneNumberCountryCode(Base, BaseModel):
    __tablename__ = 'phone_number_country_code'
    
    country_id = Column(ForeignKey('location_countries.id'))
    country_code = Column(String(10))
    phone_code = Column(String(10))
    
    country = relationship("LocationCountry")