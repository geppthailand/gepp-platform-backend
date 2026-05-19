"""
ESG Organization Settings Model
"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, Numeric, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgOrganizationSettings(Base, BaseModel):
    __tablename__ = 'esg_organization_settings'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True)

    # ESG Configuration
    reporting_year = Column(Integer, nullable=False, default=2026)
    methodology = Column(String(50), nullable=False, default='ghg_protocol')
    organizational_boundary = Column(String(50), nullable=False, default='operational_control')
    base_year = Column(Integer)
    reduction_target_percent = Column(Numeric(5, 2))
    reduction_target_year = Column(Integer)

    # Scope 3 focus mode + per-org category whitelist (migration 056).
    # 'scope3_only' (default) → UI hides S/G + non-Scope-3 E surfaces and
    # the LLM cascade prompt is narrowed to Scope 3 only.
    # 'full_esg' → original UI + prompt with all pillars visible.
    focus_mode = Column(String(32), nullable=False, default='scope3_only')

    # Set-union of all teammates' derived_categories from the materiality
    # wizard. Drives the For You page, Data Warehouse hierarchy filter,
    # dashboard widgets, the LLM prompt menu, and the
    # _create_entry_from_extraction validation guard.
    enabled_scope3_categories = Column(JSONB, nullable=False, default=list)

    # LINE Integration
    line_channel_id = Column(String(255))
    line_channel_secret = Column(String(255))
    line_channel_token = Column(Text)
    line_webhook_url = Column(String(500))
    line_rich_menu_id = Column(String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'reporting_year': self.reporting_year,
            'methodology': self.methodology,
            'organizational_boundary': self.organizational_boundary,
            'base_year': self.base_year,
            'reduction_target_percent': float(self.reduction_target_percent) if self.reduction_target_percent else None,
            'reduction_target_year': self.reduction_target_year,
            'focus_mode': self.focus_mode or 'scope3_only',
            'enabled_scope3_categories': list(self.enabled_scope3_categories or []),
            'line_channel_id': self.line_channel_id,
            'line_channel_secret': '***' if self.line_channel_secret else None,
            'line_channel_token': '***' if self.line_channel_token else None,
            'line_webhook_url': self.line_webhook_url,
            'line_rich_menu_id': self.line_rich_menu_id,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
