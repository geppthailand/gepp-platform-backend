"""
ESG Scope 3 Category Model - GHG Protocol Scope 3 category reference data
"""

from sqlalchemy import Column, Integer, String, Text
from GEPPPlatform.models.base import Base, BaseModel


class EsgScope3Category(Base, BaseModel):
    """GHG Protocol Scope 3 categories (1-15)"""
    __tablename__ = 'esg_scope3_categories'

    category_number = Column(Integer, unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    name_th = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    direction = Column(String(10), nullable=False)
    default_method = Column(String(30), nullable=False, default='spend_based')
    relevance_criteria = Column(Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'category_number': self.category_number,
            'name': self.name,
            'name_th': self.name_th,
            'description': self.description,
            'direction': self.direction,
            'default_method': self.default_method,
            'relevance_criteria': self.relevance_criteria,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
