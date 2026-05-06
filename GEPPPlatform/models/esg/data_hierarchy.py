"""
ESG Data Hierarchy Models - Category, Subcategory, Datapoint
"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgDataCategory(Base, BaseModel):
    __tablename__ = 'esg_data_category'

    pillar = Column(String(1), nullable=False)
    name = Column(String(200), nullable=False)
    name_th = Column(String(200))
    description = Column(Text)
    sort_order = Column(Integer, default=0)

    # Scope 3 focus mode (migration 056).
    # is_scope3 = TRUE for the 15 GHG Protocol Scope 3 categories.
    # scope3_category_id = 1..15 with stable numbering even if `id` differs.
    is_scope3 = Column(Boolean, nullable=False, default=False)
    scope3_category_id = Column(Integer)

    def to_dict(self):
        return {
            'id': self.id,
            'pillar': self.pillar,
            'name': self.name,
            'name_th': self.name_th,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_scope3': bool(self.is_scope3),
            'scope3_category_id': self.scope3_category_id,
            'is_active': self.is_active,
        }


class EsgDataSubcategory(Base, BaseModel):
    __tablename__ = 'esg_data_subcategory'

    pillar = Column(String(1), nullable=False)
    esg_data_category_id = Column(BigInteger, ForeignKey('esg_data_category.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(200), nullable=False)
    name_th = Column(String(200))
    description = Column(Text)
    sort_order = Column(Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'pillar': self.pillar,
            'esg_data_category_id': self.esg_data_category_id,
            'name': self.name,
            'name_th': self.name_th,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        }


class EsgDatapoint(Base, BaseModel):
    __tablename__ = 'esg_datapoint'

    pillar = Column(String(1), nullable=False)
    esg_data_subcategory_id = Column(BigInteger, ForeignKey('esg_data_subcategory.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(300), nullable=False)
    name_th = Column(String(300))
    description = Column(Text)
    unit = Column(String(50))
    data_type = Column(String(20), default='numeric')
    sort_order = Column(Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'pillar': self.pillar,
            'esg_data_subcategory_id': self.esg_data_subcategory_id,
            'name': self.name,
            'name_th': self.name_th,
            'description': self.description,
            'unit': self.unit,
            'data_type': self.data_type,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        }
