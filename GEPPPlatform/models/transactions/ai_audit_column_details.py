"""
AI Audit Column Details Model
Defines which columns can be verified by AI audit with human-readable descriptions and matching rules
"""

from sqlalchemy import Column, String, Text, Index
from ..base import Base, BaseModel


class AiAuditColumnDetail(Base, BaseModel):
    """
    Column-level audit check definitions.
    Each record describes a verifiable column with its display name, matching rules, and
    optional JOIN configuration for resolving foreign key values to human-readable names.
    """
    __tablename__ = 'ai_audit_column_details'

    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    description_en = Column(Text, nullable=False)
    description_th = Column(Text, nullable=False)
    check_rules = Column(Text, nullable=True)
    target_table = Column(String(100), nullable=True)
    ref_column = Column(String(100), nullable=True)
    target_column = Column(String(100), nullable=True)

    __table_args__ = (
        Index('idx_ai_audit_col_details_table', 'table_name'),
    )

    def __repr__(self):
        return f"<AiAuditColumnDetail(id={self.id}, {self.table_name}.{self.column_name})>"

    def to_dict(self):
        return {
            'id': self.id,
            'table_name': self.table_name,
            'column_name': self.column_name,
            'description_en': self.description_en,
            'description_th': self.description_th,
            'check_rules': self.check_rules,
            'target_table': self.target_table,
            'ref_column': self.ref_column,
            'target_column': self.target_column,
            'is_active': self.is_active,
        }
