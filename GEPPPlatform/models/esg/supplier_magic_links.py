"""
ESG Supplier Magic Link Model - Tokenised links for supplier data submission
"""

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


class EsgSupplierMagicLink(Base, BaseModel):
    """Magic links sent to suppliers for self-service data submission"""
    __tablename__ = 'esg_supplier_magic_links'

    supplier_id = Column(BigInteger, ForeignKey('esg_suppliers.id'), nullable=False, index=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False)
    email_sent_to = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(String(30), nullable=False, default='data_submission')

    def to_dict(self):
        return {
            'id': self.id,
            'supplier_id': self.supplier_id,
            'organization_id': self.organization_id,
            'token': self.token,
            'email_sent_to': self.email_sent_to,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'scope': self.scope,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
