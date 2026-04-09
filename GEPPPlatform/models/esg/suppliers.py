"""
ESG Supplier Model - Supply chain partners tracked for Scope 3 emissions
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class SupplierTier:
    TIER1 = 'tier1'
    TIER2 = 'tier2'
    TIER3 = 'tier3'


class SupplierStatus:
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    PENDING = 'pending'


class EsgSupplier(Base, BaseModel):
    """ESG suppliers for supply chain emission tracking"""
    __tablename__ = 'esg_suppliers'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    supplier_name = Column(String(300), nullable=False)
    supplier_code = Column(String(100), nullable=True)
    tax_id = Column(String(50), nullable=True)
    country = Column(String(3), nullable=False, default='THA')
    industry_sector = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_name = Column(String(255), nullable=True)
    tier = Column(String(10), nullable=False, default=SupplierTier.TIER1)
    data_collection_level = Column(String(10), nullable=False, default='1')
    annual_spend = Column(Numeric(18, 2), nullable=True)
    spend_currency = Column(String(10), nullable=False, default='THB')
    primary_scope3_category = Column(Integer, nullable=True)
    emission_data_source = Column(String(30), nullable=False, default='default')
    total_reported_tco2e = Column(Numeric(18, 6), nullable=False, default=0)
    data_quality_score = Column(Numeric(5, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default=SupplierStatus.ACTIVE)
    extra_data = Column('metadata', JSONB, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'supplier_name': self.supplier_name,
            'supplier_code': self.supplier_code,
            'tax_id': self.tax_id,
            'country': self.country,
            'industry_sector': self.industry_sector,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'contact_name': self.contact_name,
            'tier': self.tier,
            'data_collection_level': self.data_collection_level,
            'annual_spend': float(self.annual_spend) if self.annual_spend else None,
            'spend_currency': self.spend_currency,
            'primary_scope3_category': self.primary_scope3_category,
            'emission_data_source': self.emission_data_source,
            'total_reported_tco2e': float(self.total_reported_tco2e) if self.total_reported_tco2e else 0,
            'data_quality_score': float(self.data_quality_score) if self.data_quality_score else 0,
            'status': self.status,
            'metadata': self.extra_data or {},
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
