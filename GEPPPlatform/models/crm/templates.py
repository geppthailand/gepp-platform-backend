"""CRM email templates — manual + AI-generated."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer, Boolean, JSON

from ..base import Base, BaseModel


class CrmEmailTemplate(Base, BaseModel):
    __tablename__ = 'crm_email_templates'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    name = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    preview_text = Column(String(500))
    body_html = Column(Text, nullable=False)
    body_plain = Column(Text)
    variables = Column(JSON)
    generated_by = Column(String(16), nullable=False, default='human')
    ai_prompt = Column(Text)
    ai_model = Column(String(128))
    ai_token_usage = Column(JSON)
    version = Column(Integer, nullable=False, default=1)
    # Versioning — added by migration 043
    parent_template_id = Column(BigInteger, ForeignKey('crm_email_templates.id'), nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))
