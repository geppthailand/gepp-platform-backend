"""
Rewards catalog and stock models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class RewardCatalog(Base, BaseModel):
    """Master reward items available for redemption"""
    __tablename__ = 'reward_catalog'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_id = Column(BigInteger, nullable=True)  # FK files.id
    images = Column(JSONB, nullable=True)  # array of files.id
    price = Column(DECIMAL(10, 2), nullable=True)  # purchase price for budgeting
    unit = Column(String(50), nullable=True)


class RewardStock(Base, BaseModel):
    """Stock ledger: positive=deposit, negative=withdraw"""
    __tablename__ = 'reward_stocks'

    reward_catalog_id = Column(BigInteger, ForeignKey('reward_catalog.id'), nullable=False)
    values = Column(Integer, nullable=False)  # +deposit / -withdraw
    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=True)
    note = Column(Text, nullable=True)
    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=True)
    user_location_id = Column(BigInteger, nullable=True)  # FK user_locations.id
