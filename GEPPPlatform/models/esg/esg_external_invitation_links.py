"""
ESG External Invitation Links — platform-agnostic invitation system.
One link works for LINE, WhatsApp, WeChat, etc.
Tracks who used it: platform, platform_user_id, display_name, timestamp.
"""

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


class EsgExternalInvitationLink(Base, BaseModel):
    __tablename__ = 'esg_external_invitation_links'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    invited_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Tracking: who used this invitation
    used_at = Column(DateTime(timezone=True), nullable=True)
    used_by_esg_user_id = Column(BigInteger, ForeignKey('esg_users.id'), nullable=True)
    used_by_platform = Column(String(20), nullable=True)          # 'line', 'whatsapp', etc.
    used_by_platform_user_id = Column(String(255), nullable=True) # LINE userId / WhatsApp number
    used_by_display_name = Column(String(255), nullable=True)     # display name at time of use

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'invited_by_id': self.invited_by_id,
            'token': self.token,
            'expires_at': str(self.expires_at) if self.expires_at else None,
            'used_at': str(self.used_at) if self.used_at else None,
            'used_by_esg_user_id': self.used_by_esg_user_id,
            'used_by_platform': self.used_by_platform,
            'used_by_platform_user_id': self.used_by_platform_user_id,
            'used_by_display_name': self.used_by_display_name,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
        }
