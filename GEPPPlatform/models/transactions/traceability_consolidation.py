"""
Traceability Consolidation models.

A *consolidation* is a first-class event: N material sources (any mix of
already-arrived TransportTransactions and raw origin-side TransactionGroups)
are merged into ONE onward TransportTransaction that lands at a designated
*consolidation point* (a user_location).

Schema shape (after migration 061):

    traceability_consolidations  ─── header, one per consolidation event
      id
      organization_id
      consolidated_transport_id   FK → traceability_transport_transactions
      consolidation_point_id      FK → user_locations  (where the batch lands)
      material_id                 FK → materials       (the merged material)
      total_weight                NUMERIC              (sum of contributions)
      batch_name                  VARCHAR(255)         (user-supplied label)
      status                      VARCHAR(20)          ('active' | 'reverted')
      created_by, *_date, deleted_date, is_active     (BaseModel)

    traceability_consolidation_sources  ─── one row per contributing source
      id
      consolidation_id            FK → traceability_consolidations
      source_kind                 VARCHAR(20)          ('transport' | 'group')
      source_transport_id         FK → traceability_transport_transactions  (NULL when group)
      source_group_id             FK → traceability_transaction_group       (NULL when transport)
      contributed_weight          NUMERIC
      ordering                    SMALLINT
      *_date, deleted_date, is_active                  (BaseModel)

A CHECK constraint enforces that exactly one of source_transport_id /
source_group_id is set and matches ``source_kind`` — readers don't need to
disambiguate via NULL checks alone.
"""

from sqlalchemy import Column, BigInteger, ForeignKey, Numeric, SmallInteger, String
from ..base import Base, BaseModel


# Source kind enum (string literals to avoid SQL-level enum migrations).
SOURCE_KIND_TRANSPORT = "transport"
SOURCE_KIND_GROUP = "group"

# Header lifecycle status.
CONSOLIDATION_STATUS_ACTIVE = "active"
CONSOLIDATION_STATUS_REVERTED = "reverted"


class TraceabilityConsolidation(Base, BaseModel):
    """
    Header row for a single consolidation event.

    All fields that describe the event itself (where it lands, what it's
    called, whether it's still active) live HERE — not on the consolidated
    transport's meta_data. The consolidated TransportTransaction is just the
    downstream side-effect of the event.
    """
    __tablename__ = "traceability_consolidations"

    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=False)

    # The new onward TransportTransaction produced by this event.
    consolidated_transport_id = Column(
        BigInteger,
        ForeignKey("traceability_transport_transactions.id"),
        nullable=False,
    )

    # Explicit consolidation point. Mirrors consolidated_transport.destination_id
    # but is denormalised here so a reader can identify the merge target without
    # joining transports.
    consolidation_point_id = Column(
        BigInteger,
        ForeignKey("user_locations.id"),
        nullable=True,  # legacy rows may be NULL until back-filled
    )

    # Material being consolidated. One consolidation event = one material.
    material_id = Column(BigInteger, ForeignKey("materials.id"), nullable=True)

    # Cached sum of contributed_weight across the source rows.
    total_weight = Column(Numeric, nullable=False)

    # User-supplied batch label (e.g. "UOB Plaza Bangkok – Q2 plastics").
    batch_name = Column(String(255), nullable=True)

    # Lifecycle: 'active' or 'reverted'. The is_active / deleted_date flags
    # from BaseModel still apply; this column is the explicit business state.
    status = Column(String(20), nullable=False, default=CONSOLIDATION_STATUS_ACTIVE)

    created_by = Column(BigInteger, ForeignKey("user_locations.id"), nullable=True)


class TraceabilityConsolidationSource(Base, BaseModel):
    """
    One row per source contributing to a consolidation.

    ``source_kind`` is the canonical discriminator:
      - ``transport``  → ``source_transport_id`` references an existing
                          TransportTransaction that has already arrived.
      - ``group``      → ``source_group_id`` references a raw origin-side
                          TransactionGroup that had not yet been picked up.

    The DB enforces exactly-one-of via ``chk_consolidation_source_kind``.
    """
    __tablename__ = "traceability_consolidation_sources"

    consolidation_id = Column(
        BigInteger,
        ForeignKey("traceability_consolidations.id"),
        nullable=False,
    )

    source_kind = Column(String(20), nullable=False)  # 'transport' | 'group'

    source_transport_id = Column(
        BigInteger,
        ForeignKey("traceability_transport_transactions.id"),
        nullable=True,
    )
    source_group_id = Column(
        BigInteger,
        ForeignKey("traceability_transaction_group.id"),
        nullable=True,
    )

    # Weight this source contributed (may be < the source's full weight in a
    # partial-merge scenario; defaults to the source's full weight otherwise).
    contributed_weight = Column(Numeric, nullable=False)

    ordering = Column(SmallInteger, nullable=True, default=0)
