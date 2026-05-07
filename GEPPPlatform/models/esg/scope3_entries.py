"""
ESG Scope 3 Entry Model - Individual Scope 3 emission calculations
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class EsgScope3Entry(Base, BaseModel):
    """Individual Scope 3 emission entries with calculation details"""
    __tablename__ = 'esg_scope3_entries'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    category_number = Column(Integer, nullable=False)
    supplier_id = Column(BigInteger, ForeignKey('esg_suppliers.id'), nullable=True, index=True)
    record_id = Column(BigInteger, ForeignKey('esg_records.id'), nullable=True)
    reporting_year = Column(Integer, nullable=False)
    reporting_month = Column(Integer, nullable=True)
    calculation_method = Column(String(30), nullable=True)
    activity_data = Column(Numeric(18, 4), nullable=True)
    activity_unit = Column(String(50), nullable=True)
    emission_factor_value = Column(Numeric(18, 8), nullable=True)
    emission_factor_source = Column(String(200), nullable=True)
    calculated_tco2e = Column(Numeric(18, 6), nullable=False)
    spend_amount = Column(Numeric(18, 2), nullable=True)
    spend_currency = Column(String(10), nullable=False, default='THB')
    data_quality_indicator = Column(String(20), nullable=False, default='estimated')
    notes = Column(Text, nullable=True)
    extra_data = Column('metadata', JSONB, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'category_number': self.category_number,
            'supplier_id': self.supplier_id,
            'record_id': self.record_id,
            'reporting_year': self.reporting_year,
            'reporting_month': self.reporting_month,
            'calculation_method': self.calculation_method,
            'activity_data': float(self.activity_data) if self.activity_data else None,
            'activity_unit': self.activity_unit,
            'emission_factor_value': float(self.emission_factor_value) if self.emission_factor_value else None,
            'emission_factor_source': self.emission_factor_source,
            'calculated_tco2e': float(self.calculated_tco2e) if self.calculated_tco2e else None,
            'spend_amount': float(self.spend_amount) if self.spend_amount else None,
            'spend_currency': self.spend_currency,
            'data_quality_indicator': self.data_quality_indicator,
            'notes': self.notes,
            'metadata': self.extra_data or {},
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
