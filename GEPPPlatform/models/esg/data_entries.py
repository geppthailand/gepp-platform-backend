"""
ESG Data Entry Model - Data submissions via LINE Chat or LIFF
"""

from sqlalchemy import Column, BigInteger, String, Text, Numeric, Date, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


# Status/source values stored as plain VARCHAR (matches SQL migration)
class EntrySource:
    LINE_CHAT = 'LINE_CHAT'
    LIFF_MANUAL = 'LIFF_MANUAL'


class EntryStatus:
    PENDING_VERIFY = 'PENDING_VERIFY'
    VERIFIED = 'VERIFIED'


class EsgDataEntry(Base, BaseModel):
    """ESG data entries from LINE Chat (quick capture) or LIFF (manual form)"""
    __tablename__ = 'esg_data_entries'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('esg_users.id'), nullable=True, index=True)
    line_user_id = Column(String(100), nullable=True, index=True)
    category_id = Column(BigInteger, ForeignKey('esg_data_category.id'), nullable=True)
    subcategory_id = Column(BigInteger, ForeignKey('esg_data_subcategory.id'), nullable=True)
    datapoint_id = Column(BigInteger, ForeignKey('esg_datapoint.id'), nullable=True)
    category = Column(String(100), nullable=True)
    value = Column(Numeric(18, 4), nullable=False)
    unit = Column(String(50), nullable=False)
    calculated_tco2e = Column(Numeric(18, 6), nullable=True)
    entry_date = Column(Date, nullable=True)
    record_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    file_key = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    evidence_image_url = Column(String(500), nullable=True)
    scope_tag = Column(String(50), nullable=True)
    entry_source = Column(String(20), nullable=False, default=EntrySource.LIFF_MANUAL)
    status = Column(String(20), nullable=False, default=EntryStatus.PENDING_VERIFY)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'user_id': self.user_id,
            'line_user_id': self.line_user_id,
            'category_id': self.category_id,
            'subcategory_id': self.subcategory_id,
            'datapoint_id': self.datapoint_id,
            'category': self.category,
            'value': float(self.value) if self.value else None,
            'unit': self.unit,
            'calculated_tco2e': float(self.calculated_tco2e) if self.calculated_tco2e else None,
            'entry_date': str(self.entry_date) if self.entry_date else None,
            'record_date': str(self.record_date) if self.record_date else None,
            'notes': self.notes,
            'file_key': self.file_key,
            'file_name': self.file_name,
            'evidence_image_url': self.evidence_image_url,
            'scope_tag': self.scope_tag,
            'entry_source': self.entry_source,
            'status': self.status,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
