"""
Traceability Consolidation models

Header + N→1 source-join tables for the consolidation feature where N "arrived"
TransportTransactions are merged into a single onward consolidated
TransportTransaction. The consolidated transport itself lives in
``traceability_transport_transactions``; these rows record the parent/source
relationship and the per-source contributed weight.
"""

from sqlalchemy import Column, BigInteger, ForeignKey, Numeric, SmallInteger
from ..base import Base, BaseModel


class TraceabilityConsolidation(Base, BaseModel):
    """
    Header row for one consolidation event.

    ``consolidated_transport_id`` points to the *new* TransportTransaction
    produced by the consolidation (the onward leg). The source TransportTransactions
    contributing weight live in ``TraceabilityConsolidationSource`` rows that
    reference this header via ``consolidation_id``.
    """
    __tablename__ = "traceability_consolidations"

    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False)
    consolidated_transport_id = Column(BigInteger, ForeignKey("traceability_transport_transactions.id"), nullable=False)
    material_id = Column(BigInteger, ForeignKey("materials.id"), nullable=True)
    total_weight = Column(Numeric, nullable=False)
    created_by = Column(BigInteger, ForeignKey("user_locations.id"), nullable=True)


class TraceabilityConsolidationSource(Base, BaseModel):
    """
    One row per source contributing to a consolidation. The source is either
    an existing TransportTransaction (arrived material being forwarded) OR a
    raw transaction_group (origin material not yet shipped). Exactly one of
    ``source_transport_id`` / ``source_group_id`` is populated per row
    (enforced by a CHECK constraint in the DB).

    ``contributed_weight`` may be less than the source's full weight in a
    partial-merge scenario; the spec currently uses the full source weight
    when no explicit contribution is supplied.
    """
    __tablename__ = "traceability_consolidation_sources"

    consolidation_id = Column(BigInteger, ForeignKey("traceability_consolidations.id"), nullable=False)
    source_transport_id = Column(BigInteger, ForeignKey("traceability_transport_transactions.id"), nullable=True)
    source_group_id = Column(BigInteger, ForeignKey("traceability_transaction_group.id"), nullable=True)
    contributed_weight = Column(Numeric, nullable=False)
    ordering = Column(SmallInteger, nullable=True, default=0)
