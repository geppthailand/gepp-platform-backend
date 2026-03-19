"""
ESG Waste Record Model — Classified waste data with CO2e calculations
"""

import enum
from sqlalchemy import Column, BigInteger, String, Text, Numeric, Boolean, DateTime, TIMESTAMP, Date, ForeignKey
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class DataQuality(enum.Enum):
    MEASURED = 'measured'
    ESTIMATED = 'estimated'
    CALCULATED = 'calculated'


class VerificationStatus(enum.Enum):
    UNVERIFIED = 'unverified'
    VERIFIED = 'verified'
    REJECTED = 'rejected'


class EsgWasteRecord(Base, BaseModel):
    __tablename__ = 'esg_waste_records'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(BigInteger, ForeignKey('esg_documents.id', ondelete='SET NULL'))

    # Waste Data
    record_date = Column(Date, nullable=False)
    waste_type = Column(String(100), nullable=False)
    waste_category = Column(String(100))
    treatment_method = Column(String(100), nullable=False)
    weight_kg = Column(Numeric(12, 4), nullable=False)

    # GHG Calculation
    emission_factor_id = Column(BigInteger, ForeignKey('esg_emission_factors.id', ondelete='SET NULL'))
    emission_factor_value = Column(Numeric(10, 6))
    co2e_kg = Column(Numeric(12, 4))

    # Quality & Verification
    data_quality = Column(String(20), nullable=False, default='estimated')
    verification_status = Column(String(20), nullable=False, default='unverified')
    verified_by_id = Column(BigInteger)
    verified_at = Column(DateTime(timezone=True))

    # Source & Location
    source = Column(String(20), nullable=False, default='manual')
    origin_location_id = Column(BigInteger)
    vendor_name = Column(String(255))

    # Additional
    cost = Column(Numeric(12, 2))
    currency = Column(String(10), default='THB')
    notes = Column(Text)

    # Creator
    created_by_id = Column(BigInteger)

    def calculate_co2e(self):
        """Calculate CO2e from weight and emission factor"""
        if self.weight_kg and self.emission_factor_value:
            self.co2e_kg = float(self.weight_kg) * float(self.emission_factor_value)
        return self.co2e_kg

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'document_id': self.document_id,
            'record_date': self.record_date.isoformat() if self.record_date else None,
            'waste_type': self.waste_type,
            'waste_category': self.waste_category,
            'treatment_method': self.treatment_method,
            'weight_kg': float(self.weight_kg) if self.weight_kg else None,
            'emission_factor_id': self.emission_factor_id,
            'emission_factor_value': float(self.emission_factor_value) if self.emission_factor_value else None,
            'co2e_kg': float(self.co2e_kg) if self.co2e_kg else None,
            'data_quality': self.data_quality,
            'verification_status': self.verification_status,
            'verified_by_id': self.verified_by_id,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'source': self.source,
            'origin_location_id': self.origin_location_id,
            'vendor_name': self.vendor_name,
            'cost': float(self.cost) if self.cost else None,
            'currency': self.currency,
            'notes': self.notes,
            'created_by_id': self.created_by_id,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
        }
