"""
Audit Settings Service
Handles CRUD for organization audit doc requirements, check columns, document types, and column details
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from GEPPPlatform.models.transactions.ai_audit_document_types import AiAuditDocumentType
from GEPPPlatform.models.transactions.ai_audit_column_details import AiAuditColumnDetail
from GEPPPlatform.models.subscriptions.organization_audit_settings import (
    OrganizationAuditDocRequireTypes,
    OrganizationAuditCheckColumns,
)

logger = logging.getLogger(__name__)


class AuditSettingsService:
    def __init__(self, db: Session):
        self.db = db

    # ── Document Types (read-only for frontend) ──

    def get_document_types(self) -> List[Dict[str, Any]]:
        types = self.db.query(AiAuditDocumentType).filter(
            AiAuditDocumentType.deleted_date.is_(None),
            AiAuditDocumentType.is_active.is_(True),
        ).order_by(AiAuditDocumentType.id).all()
        return [t.to_dict() for t in types]

    # ── Column Details (read-only for frontend) ──

    def get_column_details(self) -> List[Dict[str, Any]]:
        cols = self.db.query(AiAuditColumnDetail).filter(
            AiAuditColumnDetail.deleted_date.is_(None),
            AiAuditColumnDetail.is_active.is_(True),
        ).order_by(AiAuditColumnDetail.id).all()
        return [c.to_dict() for c in cols]

    # ── Organization Doc Require Types ──

    def get_doc_require_types(self, organization_id: int) -> Dict[str, Any]:
        record = self.db.query(OrganizationAuditDocRequireTypes).filter(
            OrganizationAuditDocRequireTypes.organization_id == organization_id,
            OrganizationAuditDocRequireTypes.deleted_date.is_(None),
        ).first()

        if record:
            return record.to_dict()
        return {
            'id': None,
            'organization_id': organization_id,
            'transaction_document_requires': [],
            'record_document_requires': [],
            'is_active': True,
        }

    def update_doc_require_types(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        record = self.db.query(OrganizationAuditDocRequireTypes).filter(
            OrganizationAuditDocRequireTypes.organization_id == organization_id,
            OrganizationAuditDocRequireTypes.deleted_date.is_(None),
        ).first()

        tx_requires = data.get('transaction_document_requires', [])
        rec_requires = data.get('record_document_requires', [])

        if record:
            record.transaction_document_requires = tx_requires
            record.record_document_requires = rec_requires
            flag_modified(record, 'transaction_document_requires')
            flag_modified(record, 'record_document_requires')
        else:
            record = OrganizationAuditDocRequireTypes(
                organization_id=organization_id,
                transaction_document_requires=tx_requires,
                record_document_requires=rec_requires,
            )
            self.db.add(record)

        self.db.commit()
        return record.to_dict()

    # ── Organization Check Columns ──

    def get_check_columns(self, organization_id: int) -> Dict[str, Any]:
        record = self.db.query(OrganizationAuditCheckColumns).filter(
            OrganizationAuditCheckColumns.organization_id == organization_id,
            OrganizationAuditCheckColumns.deleted_date.is_(None),
        ).first()

        if record:
            return record.to_dict()
        return {
            'id': None,
            'organization_id': organization_id,
            'transaction_checks': {},
            'transaction_record_checks': {},
            'is_active': True,
        }

    def update_check_columns(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        record = self.db.query(OrganizationAuditCheckColumns).filter(
            OrganizationAuditCheckColumns.organization_id == organization_id,
            OrganizationAuditCheckColumns.deleted_date.is_(None),
        ).first()

        tx_checks = data.get('transaction_checks', {})
        rec_checks = data.get('transaction_record_checks', {})

        if record:
            record.transaction_checks = tx_checks
            record.transaction_record_checks = rec_checks
            flag_modified(record, 'transaction_checks')
            flag_modified(record, 'transaction_record_checks')
        else:
            record = OrganizationAuditCheckColumns(
                organization_id=organization_id,
                transaction_checks=tx_checks,
                transaction_record_checks=rec_checks,
            )
            self.db.add(record)

        self.db.commit()
        return record.to_dict()
