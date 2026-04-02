"""
ESG Data Entry Model - Manual data submissions via LINE LIFF
"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, Numeric, Date, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


class EsgDataEntry(Base, BaseModel):
    """Manual ESG data entries submitted by users via the LIFF app"""
    __tablename__ = 'esg_data_entries'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    category_id = Column(BigInteger, ForeignKey('esg_data_category.id'), nullable=False)
    subcategory_id = Column(BigInteger, ForeignKey('esg_data_subcategory.id'), nullable=False)
    datapoint_id = Column(BigInteger, ForeignKey('esg_datapoint.id'), nullable=True)
    value = Column(Numeric(18, 4), nullable=False)
    unit = Column(String(50), nullable=False)
    entry_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    file_key = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    scope_tag = Column(String(50), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'user_id': self.user_id,
            'category_id': self.category_id,
            'subcategory_id': self.subcategory_id,
            'datapoint_id': self.datapoint_id,
            'value': float(self.value) if self.value else None,
            'unit': self.unit,
            'entry_date': str(self.entry_date) if self.entry_date else None,
            'notes': self.notes,
            'file_key': self.file_key,
            'file_name': self.file_name,
            'scope_tag': self.scope_tag,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
