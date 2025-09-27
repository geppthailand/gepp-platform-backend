"""
Location-related core models
"""

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

class LocationCountry(Base, BaseModel):
    __tablename__ = 'location_countries'
    
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    code = Column(String(10))

class LocationRegion(Base, BaseModel):
    __tablename__ = 'location_regions'
    
    country_id = Column(ForeignKey('location_countries.id'))
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    
    country = relationship("LocationCountry")

class LocationProvince(Base, BaseModel):
    __tablename__ = 'location_provinces'
    
    country_id = Column(ForeignKey('location_countries.id'))
    region_id = Column(ForeignKey('location_regions.id'))
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    
    country = relationship("LocationCountry")
    region = relationship("LocationRegion")

class LocationDistrict(Base, BaseModel):
    __tablename__ = 'location_districts'
    
    province_id = Column(ForeignKey('location_provinces.id'))
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    
    province = relationship("LocationProvince")

class LocationSubdistrict(Base, BaseModel):
    __tablename__ = 'location_subdistricts'
    
    district_id = Column(ForeignKey('location_districts.id'))
    name_en = Column(String(255))
    name_th = Column(String(255))
    name_local = Column(String(255))
    postal_code = Column(String(10))
    
    district = relationship("LocationDistrict")