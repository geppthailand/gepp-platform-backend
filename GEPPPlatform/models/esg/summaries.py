"""
ESG Scope 3 Summary Model — Pre-calculated monthly/yearly summaries
"""

from sqlalchemy import Column, BigInteger, Integer, String, Numeric, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgScope3Summary(Base, BaseModel):
    __tablename__ = 'esg_scope3_summaries'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # Period
    period_type = Column(String(10), nullable=False)  # monthly, yearly
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer)  # NULL for yearly

    # Aggregated Data
    total_waste_kg = Column(Numeric(14, 4), nullable=False, default=0)
    total_co2e_kg = Column(Numeric(14, 4), nullable=False, default=0)
    total_records = Column(Integer, nullable=False, default=0)

    # Breakdown
    by_waste_type = Column(JSONB, default={})
    by_treatment = Column(JSONB, default={})
    by_location = Column(JSONB, default={})

    # Quality Metrics
    verified_percent = Column(Numeric(5, 2), default=0)
    measured_percent = Column(Numeric(5, 2), default=0)

    # Calculation timestamp
    calculated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'period_type': self.period_type,
            'period_year': self.period_year,
            'period_month': self.period_month,
            'total_waste_kg': float(self.total_waste_kg) if self.total_waste_kg else 0,
            'total_co2e_kg': float(self.total_co2e_kg) if self.total_co2e_kg else 0,
            'total_records': self.total_records,
            'by_waste_type': self.by_waste_type or {},
            'by_treatment': self.by_treatment or {},
            'by_location': self.by_location or {},
            'verified_percent': float(self.verified_percent) if self.verified_percent else 0,
            'measured_percent': float(self.measured_percent) if self.measured_percent else 0,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None,
        }
