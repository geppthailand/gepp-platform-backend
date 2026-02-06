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
        "organization_id": 1,
        "material_id": 77  # Optional: NULL = applies to all materials (default/fallback)
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

    Material-specific patterns:
    - material_id = NULL: Default pattern, applies to all materials (fallback)
    - material_id = 94: Pattern specific to general waste
    - material_id = 77: Pattern specific to organic waste
    - material_id = 298: Pattern specific to recyclable waste
    - material_id = 113: Pattern specific to hazardous waste
    """
    __tablename__ = 'ai_audit_response_patterns'

    name = Column(String(255), nullable=False)
    condition = Column(String(50), nullable=False, default='cc')  # Simplified: just the code
    priority = Column(Integer, nullable=False, default=1000)  # Default 1000, not used for BMA
    pattern = Column(Text, nullable=False)  # Response template with {{placeholder}}
    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'), nullable=True)  # NULL = applies to all materials

    # Relationships
    organization = relationship("Organization", back_populates="ai_audit_response_patterns")
    material = relationship("Material", foreign_keys=[material_id])
