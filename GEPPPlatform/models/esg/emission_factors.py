"""
ESG Emission Factors Model
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Boolean, DateTime, TIMESTAMP, Date
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgEmissionFactor(Base, BaseModel):
    __tablename__ = 'esg_emission_factors'

    # Classification
    waste_type = Column(String(100), nullable=False)
    waste_category = Column(String(100))
    treatment_method = Column(String(100), nullable=False)

    # Emission Factor
    factor_value = Column(Numeric(10, 6), nullable=False)
    factor_unit = Column(String(50), nullable=False, default='kgCO2e/kg')

    # Source & Validity
    source = Column(String(100), nullable=False, default='TGO')
    source_version = Column(String(50))
    country_code = Column(String(5), default='TH')
    valid_from = Column(Date)
    valid_to = Column(Date)

    # Metadata
    notes = Column(Text)

    def to_dict(self):
        return {
            'id': self.id,
            'waste_type': self.waste_type,
            'waste_category': self.waste_category,
            'treatment_method': self.treatment_method,
            'factor_value': float(self.factor_value) if self.factor_value else None,
            'factor_unit': self.factor_unit,
            'source': self.source,
            'source_version': self.source_version,
            'country_code': self.country_code,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'notes': self.notes,
            'is_active': self.is_active,
        }
