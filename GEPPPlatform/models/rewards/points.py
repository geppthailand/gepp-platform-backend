"""
Point transaction models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime
from sqlalchemy.types import DECIMAL
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class RewardPointTransaction(Base, BaseModel):
    """Point earn/spend ledger"""
    __tablename__ = 'reward_point_transactions'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=False)
    points = Column(DECIMAL(10, 2), nullable=False)  # positive=earn, negative=spend
    reward_activity_materials_id = Column(BigInteger, ForeignKey('reward_activity_materials.id'), nullable=True)
    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=True)
    value = Column(DECIMAL(10, 4), nullable=True)  # quantity used to claim
    unit = Column(String(50), nullable=True)  # snapshot of unit at claim time
    claimed_date = Column(DateTime(timezone=True), nullable=True)
    staff_id = Column(BigInteger, nullable=True)  # FK organization_reward_users.id
    droppoint_id = Column(BigInteger, ForeignKey('droppoints.id'), nullable=True)
    reference_type = Column(String(20), nullable=True)  # claim / redeem / adjust / expire / summary
    reference_id = Column(BigInteger, nullable=True)  # FK to source record
    image_ids = Column(JSONB, nullable=True)  # array of file IDs from claim photo
    # [ADMIN-TOOLS] who put this claim on the ledger: 'staff' (droppoint staff, the
    # original flow), 'admin' (attached from the web Members tab) or 'self' (a non-staff
    # member's own submission, created when the admin approves it).
    source = Column(String(16), nullable=False, default='staff')
    created_by_user_location_id = Column(BigInteger, nullable=True)  # admin (user_locations.id) for source='admin'
    transaction_id = Column(BigInteger, nullable=True)         # waste transaction created with this claim
    transaction_record_id = Column(BigInteger, nullable=True)  # its record for this item
    note = Column(Text, nullable=True)
    # [PACKAGING] pieces claimed for a packaging item. `value` stays in KG (the total of the
    # components) so every weight aggregate keeps summing kilograms; the per-material split
    # is in reward_point_transaction_components.
    quantity = Column(DECIMAL(14, 3), nullable=True)
    quantity_unit = Column(String(16), nullable=True)  # 'pcs'


class RewardPointTransactionComponent(Base, BaseModel):
    """[PACKAGING] kg per material of one packaging claim, snapshotted when claimed (the
    catalogue may change later). Source of GHG / material totals for packaging claims.
    No FK to reward_point_transactions — see migration 098."""
    __tablename__ = 'reward_point_transaction_components'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    reward_point_transaction_id = Column(BigInteger, nullable=False)
    material_id = Column(BigInteger, ForeignKey('materials.id'), nullable=False)
    weight_kg = Column(DECIMAL(14, 6), nullable=False)
    transaction_record_id = Column(BigInteger, nullable=True)
