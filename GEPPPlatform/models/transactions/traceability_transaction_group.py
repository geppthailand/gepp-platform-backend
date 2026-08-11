"""
Traceability Transaction Group - Groups transaction records by origin, material, tag, tenant for a given month/year
"""

from sqlalchemy import Column, BigInteger, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class TraceabilityTransactionGroup(Base, BaseModel):
    """
    Groups of traceability transactions by (origin, material, tag, tenant, organization, year, month).
    Holds lists of transaction_record ids and nested transaction_group ids.
    """
    __tablename__ = 'traceability_transaction_group'

    origin_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    material_id = Column(BigInteger, ForeignKey('materials.id'), nullable=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)
    transaction_record_id = Column(ARRAY(BigInteger), nullable=False, default=[])
    transaction_carried_over = Column(ARRAY(BigInteger), nullable=False, default=[])
    transaction_year = Column(Integer, nullable=True)
    transaction_month = Column(Integer, nullable=True)
    location_tag_id = Column(BigInteger, nullable=True)
    tenant_id = Column(BigInteger, nullable=True)

    # Scale transaction that created this pile. Present = this pile covers ONE
    # weigh-in instead of a whole month, so it is always dispatched whole and
    # absolute_percentage stays correct without any partial-consumption logic.
    # NULL = the original monthly grain: every pre-existing row and every
    # non-scale flow. Part of the group lookup key. Migration 081.
    source_transaction_id = Column(BigInteger, ForeignKey('transactions.id'), nullable=True)
