"""
Transport Transaction - Rows in traceability_transport_transactions for transport/weight entries
"""

from sqlalchemy import Column, BigInteger, Boolean, DateTime, ForeignKey, String, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class TransportTransaction(Base, BaseModel):
    """
    Transport transactions linked to a traceability_transaction_group.
    vehicle_info and messenger_info are stored in meta_data.
    status: in_transit | idle (idle = weight reserved for future use).
    """
    __tablename__ = "traceability_transport_transactions"

    origin_id = Column(BigInteger, ForeignKey("user_locations.id"), nullable=True)
    destination_id = Column(BigInteger, ForeignKey("user_locations.id"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("materials.id"), nullable=True)
    weight = Column(Numeric, nullable=True)
    meta_data = Column(JSONB, nullable=True)
    organization_id = Column(BigInteger, ForeignKey("organizations.id"), nullable=True)
    transaction_group_id = Column(BigInteger, ForeignKey("traceability_transaction_group.id"), nullable=True)
    disposal_method = Column(String(255), nullable=True)
    arrival_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(100), nullable=True)
    is_root = Column(Boolean, nullable=False, default=True)
    parent_id = Column(BigInteger, ForeignKey("traceability_transport_transactions.id"), nullable=True)
    absolute_percentage = Column(Numeric, nullable=True)
