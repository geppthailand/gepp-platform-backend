"""
Audit rules model for AI-based auditing system
"""

from sqlalchemy import Column, String, Text, Enum, Boolean, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base, BaseModel
import enum

class RuleType(enum.Enum):
    consistency = 'consistency'
    redundancy = 'redundancy'
    completeness = 'completeness'
    accuracy = 'accuracy'
    validity = 'validity'
    compliance = 'compliance'
    validation = 'validation'
    improvement = 'improvement'

class AuditRule(Base, BaseModel):
    __tablename__ = 'audit_rules'

    rule_id = Column(String(20), nullable=False, unique=True)  # e.g., "DC-01"
    rule_type = Column(Enum(RuleType), nullable=False)
    rule_name = Column(String(500), nullable=False)
    process = Column(String(255), nullable=True)
    condition = Column(Text, nullable=True)  # condition trigger
    thresholds = Column(Text, nullable=True)
    metrics = Column(Text, nullable=True)  # Key Data Points / Metrics (ข้อมูล/ตัวชี้วัด)
    actions = Column(JSONB, nullable=False, default=[])  # JSON array of action objects
    is_global = Column(Boolean, nullable=False, default=True)  # Whether rule applies to all organizations
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)  # Organization-specific rules

    # Relationships
    organization = relationship("Organization")

    # Actions JSON structure:
    # [
    #     {
    #         "type": "system_action",  # system_action, human_action, recommendations
    #         "action": "Flag for Auditor Review"
    #     },
    #     {
    #         "type": "recommendations",
    #         "action": "Review data completeness"
    #     },
    #     {
    #         "type": "human_action",
    #         "action": "Manual verification required"
    #     }
    # ]