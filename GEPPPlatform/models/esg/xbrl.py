"""
ESG XBRL Models - Taxonomy tags and report values for structured disclosure
"""

from sqlalchemy import Column, BigInteger, String, Text, Integer, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


class EsgXbrlTag(Base, BaseModel):
    """XBRL taxonomy tags mapped to ESG datapoints"""
    __tablename__ = 'esg_xbrl_tags'

    taxonomy = Column(String(50), nullable=True)
    tag_name = Column(String(200), nullable=False)
    tag_label = Column(String(300), nullable=True)
    tag_label_th = Column(String(300), nullable=True)
    data_type = Column(String(30), nullable=False, default='quantity')
    datapoint_id = Column(BigInteger, ForeignKey('esg_datapoint.id'), nullable=True)
    category_id = Column(BigInteger, ForeignKey('esg_data_category.id'), nullable=True)
    period_type = Column(String(20), nullable=False, default='duration')
    unit = Column(String(50), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'taxonomy': self.taxonomy,
            'tag_name': self.tag_name,
            'tag_label': self.tag_label,
            'tag_label_th': self.tag_label_th,
            'data_type': self.data_type,
            'datapoint_id': self.datapoint_id,
            'category_id': self.category_id,
            'period_type': self.period_type,
            'unit': self.unit,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }


class EsgXbrlReportValue(Base, BaseModel):
    """Actual XBRL values for a given organization and reporting year"""
    __tablename__ = 'esg_xbrl_report_values'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    tag_id = Column(BigInteger, ForeignKey('esg_xbrl_tags.id'), nullable=False, index=True)
    reporting_year = Column(Integer, nullable=False)
    value = Column(Text, nullable=False)
    unit = Column(String(50), nullable=True)
    context_ref = Column(String(100), nullable=True)
    record_id = Column(BigInteger, ForeignKey('esg_records.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'tag_id': self.tag_id,
            'reporting_year': self.reporting_year,
            'value': self.value,
            'unit': self.unit,
            'context_ref': self.context_ref,
            'record_id': self.record_id,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
