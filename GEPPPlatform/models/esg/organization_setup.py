"""
ESG Organization Setup Model
"""

from sqlalchemy import Column, BigInteger, Integer, String, Numeric, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgOrganizationSetup(Base, BaseModel):
    __tablename__ = 'esg_organization_setup'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True)

    # ESG Operational Config
    industry_sector = Column(String(100))
    employee_count = Column(Integer)
    revenue_currency = Column(String(10), default='THB')
    annual_revenue = Column(Numeric(14, 2))
    reporting_framework = Column(String(50), default='gri')
    fiscal_year_start = Column(Integer, default=1)

    # Data Collection Config
    auto_extract_enabled = Column(Boolean, default=True)
    notification_enabled = Column(Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'industry_sector': self.industry_sector,
            'employee_count': self.employee_count,
            'revenue_currency': self.revenue_currency,
            'annual_revenue': float(self.annual_revenue) if self.annual_revenue else None,
            'reporting_framework': self.reporting_framework,
            'fiscal_year_start': self.fiscal_year_start,
            'auto_extract_enabled': self.auto_extract_enabled,
            'notification_enabled': self.notification_enabled,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
        }
