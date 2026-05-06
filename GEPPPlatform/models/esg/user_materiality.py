"""
ESG Per-User Materiality Filter State

Stores each user's answers to the Carbon Scope 3 materiality wizard
(see migration 055). The wizard runs once per new LINE-registered user
on first LIFF entry; its output `derived_categories` also seeds the
org-level whitelist on EsgOrganizationSettings.enabled_scope3_categories.

The same scoring algorithm runs in the frontend
(v3/frontend/gepp-esg/src/mat_filters/scoring.ts) and here
(GEPPPlatform/services/esg/materiality_config.py). They share fixtures
to prevent drift.
"""

from sqlalchemy import Column, BigInteger, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB

from ..base import Base, BaseModel


class EsgUserMateriality(Base, BaseModel):
    __tablename__ = 'esg_user_materiality'

    user_id = Column(BigInteger, nullable=False)
    organization_id = Column(BigInteger, nullable=False)

    questions_version = Column(Integer, nullable=False, default=1)

    # { q1_industry: { kind: 'single', selected, freeText? }, ... }
    answers = Column(JSONB, nullable=False, default=dict)

    # [1, 4, 5, 6, 7] — material category IDs after server-side scoring
    derived_categories = Column(JSONB, nullable=False, default=list)

    # { "1": 1.4, "5": 0.8, ... } — for analytics / re-bucketing
    category_scores = Column(JSONB)

    industry_other_text = Column(String(200))
    last_question_id = Column(String(64))

    completed_at = Column(DateTime(timezone=True))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'userId': self.user_id,
            'organizationId': self.organization_id,
            'questionsVersion': self.questions_version,
            'answers': self.answers or {},
            'derivedCategories': self.derived_categories or [],
            'categoryScores': self.category_scores or {},
            'industryOtherText': self.industry_other_text,
            'lastQuestionId': self.last_question_id,
            'completed': self.completed_at is not None,
            'completedAt': str(self.completed_at) if self.completed_at else None,
            'createdDate': str(self.created_date) if self.created_date else None,
            'updatedDate': str(self.updated_date) if self.updated_date else None,
        }
