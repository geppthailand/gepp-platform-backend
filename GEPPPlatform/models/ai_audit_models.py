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

    Example structure:
    {
        "name": "Wrong Category - Organic Detected",
        "condition": ["remark.code == 'wrong_category'", "remark.details.detected == 'organic'"],
        "priority": 0,
        "pattern": "จากรูป {claimed_type} ตรวจพบว่าเป็น {remark.details.detected} เนื่องจากพบ {remark.details.reason}",
        "organization_id": 1
    }

    LLM Output Structure that this pattern will format:
    {
        "claimed_type": "recyclable",
        "audit_status": "reject",
        "confidence_score": 0.95,
        "remark": {
            "code": "wrong_category",
            "severity": "critical",
            "details": {
                "detected": "organic waste",
                "reason": "visible food scraps on container"
            },
            "correction_action": "Remove food scraps and wash the container."
        }
    }
    """
    __tablename__ = 'ai_audit_response_patterns'

    name = Column(String(255), nullable=False)
    condition = Column(JSONB, nullable=False, default=[])  # List of condition expressions
    priority = Column(Integer, nullable=False, default=0)  # 0 = highest priority
    pattern = Column(Text, nullable=False)  # Response template with placeholders
    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="ai_audit_response_patterns")
