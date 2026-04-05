"""
Emission Factor Model - conversion factors for tCO2e calculation
"""

from sqlalchemy import Column, BigInteger, String, Numeric, Text
from GEPPPlatform.models.base import Base, BaseModel


class EmissionFactor(Base, BaseModel):
    """Lookup table mapping activity categories to CO2e conversion factors"""
    __tablename__ = 'emission_factors'

    category = Column(String(100), nullable=False, index=True)
    subcategory = Column(String(100), nullable=True)
    fuel_type = Column(String(100), nullable=True)
    factor_value = Column(Numeric(18, 8), nullable=False)
    unit = Column(String(50), nullable=False)
    result_unit = Column(String(50), nullable=False, default='tCO2e')
    scope = Column(String(20), nullable=False)
    source = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'subcategory': self.subcategory,
            'fuel_type': self.fuel_type,
            'factor_value': float(self.factor_value) if self.factor_value else None,
            'unit': self.unit,
            'result_unit': self.result_unit,
            'scope': self.scope,
            'source': self.source,
            'description': self.description,
        }
