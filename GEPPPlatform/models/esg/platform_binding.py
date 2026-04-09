"""
ESG External Platform Binding Model
"""

from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgExternalPlatformBinding(Base, BaseModel):
    __tablename__ = 'esg_external_platform_binding'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    channel = Column(String(20), nullable=False)

    # Auth credentials (channel-specific JSONB)
    auth_json = Column(JSONB, nullable=False, default=dict)

    # Authorized groups
    authorized_groups = Column(JSONB, default=list)

    def to_dict(self, mask_secrets=True):
        auth = dict(self.auth_json or {})
        if mask_secrets:
            for key in ('channel_secret', 'channel_token', 'api_key', 'password'):
                if key in auth and auth[key]:
                    auth[key] = '***'

        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'channel': self.channel,
            'auth_json': auth,
            'authorized_groups': self.authorized_groups or [],
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
