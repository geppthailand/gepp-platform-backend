"""
TransportTransactionFile — per-TransportTransaction file attachment join.

Shared by both the consolidation flow (attachments on the onward leg) and the
normal single-source pickup flow (attachments on a regular transport row).
Each row links one ``traceability_transport_transactions`` row to one ``files`` row.
"""

from sqlalchemy import Column, BigInteger, ForeignKey, SmallInteger
from ..base import Base, BaseModel


class TransportTransactionFile(Base, BaseModel):
    """
    Join table: traceability_transport_transactions ↔ files (many-to-many).

    Soft-delete is via ``is_active=False`` + ``deleted_date`` like everything
    else in this codebase. The UNIQUE (transport_transaction_id, file_id)
    constraint is enforced at the DB level so callers can blindly insert and
    rely on the constraint to dedupe, or pre-check before inserting.
    """
    __tablename__ = "traceability_transport_files"

    transport_transaction_id = Column(BigInteger, ForeignKey("traceability_transport_transactions.id"), nullable=False)
    file_id = Column(BigInteger, ForeignKey("files.id"), nullable=False)
    ordering = Column(SmallInteger, nullable=True, default=0)
    uploaded_by = Column(BigInteger, ForeignKey("user_locations.id"), nullable=True)
