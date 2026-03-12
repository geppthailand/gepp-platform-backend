"""
Organization Audit Settings Models
Per-organization configuration for AI audit document requirements and column checks
"""

from sqlalchemy import Column, BigInteger, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class OrganizationAuditDocRequireTypes(Base, BaseModel):
    """
    Per-organization required document types for AI audit.
    If no record exists for an organization, no documents are required.
    """
    __tablename__ = 'organization_audit_doc_require_types'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True)
    transaction_document_requires = Column(JSONB, nullable=False, default=[])
    record_document_requires = Column(JSONB, nullable=False, default=[])

    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        Index('idx_org_audit_doc_require_org', 'organization_id'),
    )

    def __repr__(self):
        return f"<OrganizationAuditDocRequireTypes(id={self.id}, org={self.organization_id})>"

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'transaction_document_requires': self.transaction_document_requires,
            'record_document_requires': self.record_document_requires,
            'is_active': self.is_active,
        }


class OrganizationAuditCheckColumns(Base, BaseModel):
    """
    Per-organization column check configuration for AI audit data matching.
    Defines which transaction and record columns should be verified against evidence.
    """
    __tablename__ = 'organization_audit_check_columns'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True)
    transaction_checks = Column(JSONB, nullable=False, default={})
    transaction_record_checks = Column(JSONB, nullable=False, default={})

    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        Index('idx_org_audit_check_columns_org', 'organization_id'),
    )

    def __repr__(self):
        return f"<OrganizationAuditCheckColumns(id={self.id}, org={self.organization_id})>"

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'transaction_checks': self.transaction_checks,
            'transaction_record_checks': self.transaction_record_checks,
            'is_active': self.is_active,
        }
