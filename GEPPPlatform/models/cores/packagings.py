"""
Packaging catalogue (migration 098).

A packaging item — one brand's product container, e.g. "Singha drinking water 600 ml" —
converts to one or more materials by weight per piece (PET 0.070 kg + HDPE 0.001 kg).
GEPP maintains the catalogue in the back office; GEPP Rewards campaigns can offer a
packaging item so members claim by pieces and the waste side receives kilograms per
material (see services/rewards/packaging_conversion.py).
"""

from sqlalchemy import Column, String, BigInteger, Integer, ForeignKey
from sqlalchemy.types import DECIMAL

from ..base import Base, BaseModel

PACKAGING_TYPES = ('bottle', 'can', 'carton', 'pouch', 'cup', 'box', 'other')


class PackagingBrand(Base, BaseModel):
    __tablename__ = 'packaging_brands'

    name_th = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=True)
    logo_file_id = Column(BigInteger, nullable=True)  # files.id


class Packaging(Base, BaseModel):
    __tablename__ = 'packagings'

    brand_id = Column(BigInteger, ForeignKey('packaging_brands.id'), nullable=True)
    name_th = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=True)
    size_label = Column(String(64), nullable=True)      # "600 มล.", "9 บาท"
    volume_ml = Column(DECIMAL(10, 2), nullable=True)
    barcode = Column(String(64), nullable=True)
    packaging_type = Column(String(32), nullable=False, default='other')
    image_file_id = Column(BigInteger, nullable=True)   # files.id
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)  # NULL = global


class PackagingMaterial(Base, BaseModel):
    """One material of a packaging and its weight per piece (kg)."""
    __tablename__ = 'packaging_materials'

    packaging_id = Column(BigInteger, ForeignKey('packagings.id', ondelete='CASCADE'), nullable=False)
    material_id = Column(BigInteger, ForeignKey('materials.id'), nullable=False)
    weight_kg = Column(DECIMAL(12, 6), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
