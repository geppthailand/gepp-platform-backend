"""
ESG CBAM Models - EU Carbon Border Adjustment Mechanism products and reports
"""

from sqlalchemy import Column, BigInteger, String, Numeric, Integer, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class EsgCbamProduct(Base, BaseModel):
    """CBAM-relevant products with embedded emission data"""
    __tablename__ = 'esg_cbam_products'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    cn_code = Column(String(20), nullable=False)
    product_name = Column(String(300), nullable=False)
    product_name_th = Column(String(300), nullable=True)
    production_volume = Column(Numeric(18, 4), nullable=True)
    production_unit = Column(String(50), nullable=False, default='tonne')
    direct_emissions_tco2e = Column(Numeric(18, 6), nullable=True)
    indirect_emissions_tco2e = Column(Numeric(18, 6), nullable=True)
    precursor_emissions_tco2e = Column(Numeric(18, 6), nullable=True)
    total_embedded_emissions = Column(Numeric(18, 6), nullable=True)
    specific_embedded_emissions = Column(Numeric(18, 8), nullable=True)
    default_value_tco2e = Column(Numeric(18, 6), nullable=True)
    reporting_period_start = Column(Date, nullable=True)
    reporting_period_end = Column(Date, nullable=True)
    installation_id = Column(String(100), nullable=True)
    verification_status = Column(String(20), nullable=False, default='unverified')
    extra_data = Column('metadata', JSONB, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'cn_code': self.cn_code,
            'product_name': self.product_name,
            'product_name_th': self.product_name_th,
            'production_volume': float(self.production_volume) if self.production_volume else None,
            'production_unit': self.production_unit,
            'direct_emissions_tco2e': float(self.direct_emissions_tco2e) if self.direct_emissions_tco2e else None,
            'indirect_emissions_tco2e': float(self.indirect_emissions_tco2e) if self.indirect_emissions_tco2e else None,
            'precursor_emissions_tco2e': float(self.precursor_emissions_tco2e) if self.precursor_emissions_tco2e else None,
            'total_embedded_emissions': float(self.total_embedded_emissions) if self.total_embedded_emissions else None,
            'specific_embedded_emissions': float(self.specific_embedded_emissions) if self.specific_embedded_emissions else None,
            'default_value_tco2e': float(self.default_value_tco2e) if self.default_value_tco2e else None,
            'reporting_period_start': str(self.reporting_period_start) if self.reporting_period_start else None,
            'reporting_period_end': str(self.reporting_period_end) if self.reporting_period_end else None,
            'installation_id': self.installation_id,
            'verification_status': self.verification_status,
            'metadata': self.extra_data or {},
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }


class EsgCbamReport(Base, BaseModel):
    """CBAM quarterly reports"""
    __tablename__ = 'esg_cbam_reports'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    reporting_quarter = Column(Integer, nullable=False)
    reporting_year = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='draft')
    report_data = Column(JSONB, default=dict)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    export_url = Column(String(500), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'reporting_quarter': self.reporting_quarter,
            'reporting_year': self.reporting_year,
            'status': self.status,
            'report_data': self.report_data or {},
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'export_url': self.export_url,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
