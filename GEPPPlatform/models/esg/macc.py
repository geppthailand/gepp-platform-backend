"""
ESG MACC Initiative Model - Marginal Abatement Cost Curve initiatives
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class EsgMaccInitiative(Base, BaseModel):
    """MACC initiatives for emission reduction planning"""
    __tablename__ = 'esg_macc_initiatives'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True, index=True)
    name = Column(String(300), nullable=False)
    name_th = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    applicable_scope = Column(String(20), nullable=False, default='all')
    abatement_potential_tco2e = Column(Numeric(18, 6), nullable=False, default=0)
    implementation_cost = Column(Numeric(18, 2), nullable=False, default=0)
    annual_operating_cost = Column(Numeric(18, 2), nullable=False, default=0)
    annual_savings = Column(Numeric(18, 2), nullable=False, default=0)
    cost_per_tco2e = Column(Numeric(18, 4), nullable=False, default=0)
    payback_years = Column(Numeric(6, 2), nullable=True)
    implementation_timeline = Column(String(20), nullable=False, default='short_term')
    difficulty = Column(String(20), nullable=False, default='moderate')
    is_template = Column(Boolean, nullable=False, default=False)
    industry_sector = Column(String(100), nullable=True)
    source = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default='available')
    extra_data = Column('metadata', JSONB, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'name': self.name,
            'name_th': self.name_th,
            'description': self.description,
            'category': self.category,
            'applicable_scope': self.applicable_scope,
            'abatement_potential_tco2e': float(self.abatement_potential_tco2e) if self.abatement_potential_tco2e else 0,
            'implementation_cost': float(self.implementation_cost) if self.implementation_cost else 0,
            'annual_operating_cost': float(self.annual_operating_cost) if self.annual_operating_cost else 0,
            'annual_savings': float(self.annual_savings) if self.annual_savings else 0,
            'cost_per_tco2e': float(self.cost_per_tco2e) if self.cost_per_tco2e else 0,
            'payback_years': float(self.payback_years) if self.payback_years else None,
            'implementation_timeline': self.implementation_timeline,
            'difficulty': self.difficulty,
            'is_template': self.is_template,
            'industry_sector': self.industry_sector,
            'source': self.source,
            'status': self.status,
            'metadata': self.extra_data or {},
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
