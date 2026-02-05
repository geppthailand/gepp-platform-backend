"""
AI Audit models for managing rule sets and response patterns
"""

from sqlalchemy import Column, String, Text, Integer, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base, BaseModel


class AiAuditRuleSet(Base, BaseModel):
    """
    AI Audit Rule Sets - Defines different audit rule configurations
    """
    __tablename__ = 'ai_audit_rule_sets'

    name = Column(String(255), nullable=False, unique=True)
    function_name = Column(String(255), nullable=False)

    # Relationships
    organizations = relationship("Organization", back_populates="ai_audit_rule_set", foreign_keys="Organization.ai_audit_rule_set_id")


class AiAuditResponsePattern(Base, BaseModel):
    """
    AI Audit Response Patterns - Stores customizable response message templates

    Simplified structure for BMA audit:
    {
        "name": "Wrong Category - Message",
        "condition": "wc",  # Simplified: just the code
        "priority": 1000,  # Default, not used for priority sorting
        "pattern": "จากรูป {{claimed_type}} ตรวจพบว่าเป็น {{detect_type}} พบสิ่งของที่ไม่ถูกต้อง: {{warning_items}}",
        "organization_id": 1
    }

    Available codes:
    - ncm: non_complete_material
    - cc: correct_category
    - wc: wrong_category
    - ui: unclear_image
    - hc: heavy_contamination
    - lc: light_contamination
    - pe: parse_error
    - ie: image_error

    Available placeholders:
    - {{code}}: The audit code (e.g., "wc", "cc")
    - {{detect_type}}: Detected material type name (e.g., "general", "organic")
    - {{claimed_type}}: Claimed material type name (e.g., "recyclable")
    - {{warning_items}}: Comma-separated list of wrong items (Thai names)
    """
    __tablename__ = 'ai_audit_response_patterns'

    name = Column(String(255), nullable=False)
    condition = Column(String(50), nullable=False, default='cc')  # Simplified: just the code
    priority = Column(Integer, nullable=False, default=1000)  # Default 1000, not used for BMA
    pattern = Column(Text, nullable=False)  # Response template with {{placeholder}}
    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="ai_audit_response_patterns")
