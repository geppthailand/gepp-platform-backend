"""
Rewards catalog and stock models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.dialects.postgresql import JSONB, UUID
from ..base import Base, BaseModel


class RewardCatalogCategory(Base, BaseModel):
    """Org-managed preset categories for catalog items"""
    __tablename__ = 'reward_catalog_categories'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)


class RewardCatalog(Base, BaseModel):
    """Master reward items available for redemption"""
    __tablename__ = 'reward_catalog'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_id = Column(BigInteger, nullable=True)  # FK files.id
    images = Column(JSONB, nullable=True)  # array of files.id
    price = Column(DECIMAL(10, 2), nullable=True)  # purchase price for budgeting
    cost_baht = Column(DECIMAL(10, 2), nullable=True)  # actual cost (THB) — used by Overview budget KPI
    unit = Column(String(50), nullable=True)

    # Inventory tab extensions (migration 007)
    category_id = Column(BigInteger, ForeignKey('reward_catalog_categories.id'), nullable=True)
    min_threshold = Column(Integer, nullable=False, default=0)  # low-stock alert threshold
    limit_per_user_per_campaign = Column(Integer, nullable=True)  # NULL = unlimited
    status = Column(String(20), nullable=False, default='active')  # 'active' | 'archived'


class RewardStock(Base, BaseModel):
    """Stock ledger: positive=deposit, negative=withdraw"""
    __tablename__ = 'reward_stocks'

    reward_catalog_id = Column(BigInteger, ForeignKey('reward_catalog.id'), nullable=False)
    values = Column(Integer, nullable=False)  # +deposit / -withdraw
    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=True)
    note = Column(Text, nullable=True)
    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=True)
    user_location_id = Column(BigInteger, nullable=True)  # FK user_locations.id

    # Inventory tab extensions (migration 007)
    ledger_type = Column(String(20), nullable=False, default='deposit')
    # 'deposit' | 'withdraw' | 'transfer' | 'redeem' | 'return'
    transfer_group_id = Column(UUID(as_uuid=True), nullable=True)  # pairs 2 rows of a transfer
    vendor = Column(String(200), nullable=True)
    unit_price = Column(DECIMAL(12, 2), nullable=True)
    total_price = Column(DECIMAL(12, 2), nullable=True)
    receipt_file_id = Column(BigInteger, nullable=True)  # FK files.id
    admin_user_id = Column(BigInteger, nullable=True)  # platform user who performed action
