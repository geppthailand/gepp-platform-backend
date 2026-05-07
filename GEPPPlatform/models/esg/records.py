"""
EsgRecord — record-centric storage for ESG extractions.

One row = one atomic GHG-calculatable item (one trip, one stay, one
invoice line). The full datapoint set lives in the `datapoints` JSONB
column so a record can be read in a single query — no fan-out across
many esg_data_entries rows.

See migration 058_create_esg_records.sql for the column-by-column
contract and the rationale.
"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Numeric, Date, Boolean,
    DateTime, CHAR, ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from GEPPPlatform.models.base import Base, BaseModel


class GhgStatus:
    PENDING = 'pending'             # not evaluated yet
    COMPUTED = 'computed'           # kgco2e set, method known
    INSUFFICIENT = 'insufficient'   # required activity data missing
    METHOD_UNKNOWN = 'method_unknown'  # had data but no EF available


class EsgRecord(Base, BaseModel):
    __tablename__ = 'esg_records'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    line_user_id = Column(String(64))
    user_id = Column(BigInteger)

    # Source document
    extraction_id = Column(BigInteger,
                           ForeignKey('esg_organization_data_extraction.id',
                                      ondelete='SET NULL'))
    evidence_image_url = Column(String(500))
    file_key = Column(String(500))

    # Hierarchy
    category_id = Column(BigInteger, ForeignKey('esg_data_category.id', ondelete='SET NULL'))
    subcategory_id = Column(BigInteger, ForeignKey('esg_data_subcategory.id', ondelete='SET NULL'))
    scope3_category_id = Column(Integer)
    pillar = Column(CHAR(1))

    # Identity
    record_label = Column(String(255), nullable=False)
    entry_date = Column(Date)

    # Datapoints — see migration for the JSONB shape
    datapoints = Column(JSONB, nullable=False, default=list)

    # GHG
    kgco2e = Column(Numeric(20, 4))
    ghg_status = Column(String(20), nullable=False, default=GhgStatus.PENDING)
    ghg_method = Column(String(60))
    ghg_missing_fields = Column(JSONB, nullable=False, default=list)
    ghg_reason = Column(Text)
    # EF citation — populated from the LLM's `ghg_source_name`,
    # `ghg_source_url`, `ghg_ef_value`, `ghg_ef_unit`. Displayed in
    # the data-warehouse modal popover as a clickable reference so an
    # auditor can re-derive the kgCO2e number from the cited factor.
    ghg_source_name = Column(Text)
    ghg_source_url = Column(Text)
    ghg_ef_value = Column(Numeric(20, 8))
    ghg_ef_unit = Column(String(60))

    # Bookkeeping
    currency = Column(String(8))
    status = Column(String(30), default='PENDING_VERIFY')
    entry_source = Column(String(30), default='LINE_CHAT')
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'line_user_id': self.line_user_id,
            'user_id': self.user_id,
            'extraction_id': self.extraction_id,
            'evidence_image_url': self.evidence_image_url,
            'file_key': self.file_key,
            'category_id': self.category_id,
            'subcategory_id': self.subcategory_id,
            'scope3_category_id': self.scope3_category_id,
            'pillar': self.pillar,
            'record_label': self.record_label,
            'entry_date': str(self.entry_date) if self.entry_date else None,
            'datapoints': self.datapoints or [],
            'kgco2e': float(self.kgco2e) if self.kgco2e is not None else None,
            'ghg_status': self.ghg_status,
            'ghg_method': self.ghg_method,
            'ghg_missing_fields': self.ghg_missing_fields or [],
            'ghg_reason': self.ghg_reason,
            'ghg_source_name': self.ghg_source_name,
            'ghg_source_url': self.ghg_source_url,
            'ghg_ef_value': float(self.ghg_ef_value) if self.ghg_ef_value is not None else None,
            'ghg_ef_unit': self.ghg_ef_unit,
            'currency': self.currency,
            'status': self.status,
            'entry_source': self.entry_source,
            'notes': self.notes,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
        }
