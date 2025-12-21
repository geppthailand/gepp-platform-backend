from sqlalchemy import Column, String, BigInteger, Boolean, Numeric, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

class Gri306_1(Base, BaseModel):
    """
    GRI 306-1: Waste generation and significant waste-related impacts
    """
    __tablename__ = 'gri306_1'

    # id, is_active, created_date, updated_date, deleted_date are in BaseModel
    
    input_material = Column(String(255))
    activity = Column(String(255))
    output_material = Column(BigInteger, ForeignKey('materials.id'))
    output_category = Column(BigInteger, ForeignKey('material_categories.id'))
    method = Column(String(255))
    onsite = Column(Boolean)
    weight = Column(Numeric)
    description = Column(Text)
    value_chain_position = Column(Text)
    record_year = Column(String(20))
    organization = Column(BigInteger, ForeignKey('organizations.id'))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))

class Gri306_2(Base, BaseModel):
    """
    GRI 306-2: Management of significant waste-related impacts
    """
    __tablename__ = 'gri306_2'

    approached_id = Column(BigInteger, ForeignKey('gri306_1.id'))
    prevention_action = Column(String(255))
    verify_method = Column(String(255))
    collection_method = Column(String(255))
    record_year = Column(String(20))
    organization = Column(BigInteger, ForeignKey('organizations.id'))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))

    # Relationship to 306-1
    approached_item = relationship("Gri306_1")

class Gri306_3(Base, BaseModel):
    """
    GRI 306-3: Waste generated (Spills/Leaks)
    """
    __tablename__ = 'gri306_3'

    spill_type = Column(String(255))
    surface_type = Column(String(255))
    location = Column(String(255))
    volume = Column(Numeric)
    unit = Column(String(50))
    cleanup_cost = Column(Numeric)
    record_year = Column(String(20))
    organization = Column(BigInteger, ForeignKey('organizations.id'))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))

class Gri306Export(Base, BaseModel):
    """
    History of GRI 306 report exports
    """
    __tablename__ = 'gri306_export'

    version = Column(String(255))  # Changed from Integer to String to support version names like "Test 1"
    export_file_url = Column(Text)
    record_year = Column(String(20))
    organization = Column(BigInteger, ForeignKey('organizations.id'))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))
