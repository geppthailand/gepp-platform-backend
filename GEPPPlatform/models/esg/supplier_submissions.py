"""
ESG Supplier Submission Model - Data submissions received from suppliers
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class SubmissionStatus:
    PENDING = 'pending'
    SUBMITTED = 'submitted'
    VERIFIED = 'verified'
    REJECTED = 'rejected'


class EsgSupplierSubmission(Base, BaseModel):
    """Supplier data submissions for emission reporting"""
    __tablename__ = 'esg_supplier_submissions'

    supplier_id = Column(BigInteger, ForeignKey('esg_suppliers.id'), nullable=False, index=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    reporting_year = Column(Integer, nullable=False)
    reporting_period = Column(String(20), nullable=False, default='annual')
    scope3_category = Column(Integer, nullable=True)
    submission_status = Column(String(20), nullable=False, default=SubmissionStatus.PENDING)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    data_tier = Column(String(10), nullable=False, default='1')
    raw_data = Column(JSONB, nullable=False, default=dict)
    calculated_tco2e = Column(Numeric(18, 6), nullable=True)
    anomaly_flags = Column(JSONB, nullable=False, default=list)
    file_key = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'supplier_id': self.supplier_id,
            'organization_id': self.organization_id,
            'reporting_year': self.reporting_year,
            'reporting_period': self.reporting_period,
            'scope3_category': self.scope3_category,
            'submission_status': self.submission_status,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'verified_by_id': self.verified_by_id,
            'data_tier': self.data_tier,
            'raw_data': self.raw_data or {},
            'calculated_tco2e': float(self.calculated_tco2e) if self.calculated_tco2e else None,
            'anomaly_flags': self.anomaly_flags or [],
            'file_key': self.file_key,
            'notes': self.notes,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
