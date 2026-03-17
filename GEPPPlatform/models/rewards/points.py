"""
Point transaction models
"""

from sqlalchemy import Column, String, ForeignKey, BigInteger, DateTime
from sqlalchemy.types import DECIMAL
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
