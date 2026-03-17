"""
Redemption, user, and droppoint models
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer
from ..base import Base, BaseModel


class RewardRedemption(Base, BaseModel):
    """Redemption records"""
    __tablename__ = 'reward_redemptions'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=False)
    reward_campaign_id = Column(BigInteger, ForeignKey('reward_campaigns.id'), nullable=False)
    catalog_id = Column(BigInteger, ForeignKey('reward_catalog.id'), nullable=False)
    points_redeemed = Column(Integer, nullable=False)
    quantity = Column(Integer, default=1)
    status = Column(String(20), default='inprogress')  # inprogress / completed / canceled
    stock_action_id = Column(BigInteger, nullable=True)  # FK reward_stocks.id
    hash = Column(String(64), unique=True, nullable=False)
    staff_id = Column(BigInteger, nullable=True)  # FK organization_reward_users.id
    note = Column(Text, nullable=True)


class RewardUser(Base, BaseModel):
    """Omnichannel user identity (shared across organizations)"""
    __tablename__ = 'reward_users'

    display_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    # LINE
    line_user_id = Column(String(255), unique=True, nullable=True)
    line_display_name = Column(String(255), nullable=True)
    line_picture_url = Column(String(500), nullable=True)
    line_status_message = Column(String(500), nullable=True)
    # WhatsApp
    whatsapp_user_id = Column(String(255), unique=True, nullable=True)
    # WeChat
    wechat_user_id = Column(String(255), unique=True, nullable=True)


class OrganizationRewardUser(Base, BaseModel):
    """Links reward users to organizations with role"""
    __tablename__ = 'organization_reward_users'

    reward_user_id = Column(BigInteger, ForeignKey('reward_users.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    role = Column(String(20), default='user')  # user / staff


class Droppoint(Base, BaseModel):
    """Physical collection/redemption points"""
    __tablename__ = 'droppoints'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    hash = Column(String(64), unique=True, nullable=False)
    tag_id = Column(BigInteger, nullable=True)  # FK user_location_tags.id
    tenant_id = Column(BigInteger, nullable=True)  # FK user_tenants.id
    user_location_id = Column(BigInteger, nullable=True)  # FK user_locations.id
    type = Column(String(50), nullable=False)  # reward_droppoint / logistic_droppoint


class DroppointType(Base, BaseModel):
    """Global droppoint categories"""
    __tablename__ = 'droppoint_types'

    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
