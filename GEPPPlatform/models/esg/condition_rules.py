"""
ESG Condition Rule Model - Rules engine for contextual insights and alerts
"""

from sqlalchemy import Column, String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from GEPPPlatform.models.base import Base, BaseModel


class EsgConditionRule(Base, BaseModel):
    """Condition-based rules that trigger insights, alerts, or recommendations"""
    __tablename__ = 'esg_condition_rules'

    rule_code = Column(String(50), unique=True, nullable=False)
    category = Column(String(30), nullable=False)
    condition_type = Column(String(30), nullable=False)
    condition_expression = Column(JSONB, nullable=False)
    insight_type = Column(String(20), nullable=False)
    severity = Column(Integer, nullable=False, default=0)
    target_section = Column(String(50), nullable=True)
    title = Column(String(200), nullable=False)
    title_th = Column(String(200), nullable=True)
    message_template = Column(Text, nullable=False)
    message_template_th = Column(Text, nullable=True)
    action_url = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'rule_code': self.rule_code,
            'category': self.category,
            'condition_type': self.condition_type,
            'condition_expression': self.condition_expression,
            'insight_type': self.insight_type,
            'severity': self.severity,
            'target_section': self.target_section,
            'title': self.title,
            'title_th': self.title_th,
            'message_template': self.message_template,
            'message_template_th': self.message_template_th,
            'action_url': self.action_url,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
