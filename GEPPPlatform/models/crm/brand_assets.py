"""CRM brand assets — platform defaults + per-org overrides for email templates."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime
from sqlalchemy.sql import func

from ..base import Base


class CrmBrandAsset(Base):
    __tablename__ = 'crm_brand_assets'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'))
    asset_key = Column(String(64), nullable=False)
    asset_value = Column(Text, nullable=False)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
