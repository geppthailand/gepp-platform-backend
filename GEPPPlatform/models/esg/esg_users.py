"""
ESG Users — External platform users (LINE, WhatsApp, WeChat, etc.)
Separate from user_locations (desktop web users).
"""

from sqlalchemy import Column, BigInteger, String, ForeignKey, UniqueConstraint
from GEPPPlatform.models.base import Base, BaseModel


class EsgUser(Base, BaseModel):
    __tablename__ = 'esg_users'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True, index=True)
    platform = Column(String(20), nullable=False)           # 'line', 'whatsapp', 'wechat', 'telegram'
    platform_user_id = Column(String(255), nullable=False)  # LINE userId / WhatsApp number / etc.
    display_name = Column(String(255), nullable=True)
    profile_image_url = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint('platform', 'platform_user_id', name='uq_esg_users_platform_user'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'platform': self.platform,
            'platform_user_id': self.platform_user_id,
            'display_name': self.display_name,
            'profile_image_url': self.profile_image_url,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
