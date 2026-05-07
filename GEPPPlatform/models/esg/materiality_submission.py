"""
EsgMaterialitySubmission — append-only history of every materiality
assessment a user has run. Distinct from `esg_user_materiality` which
stores only the latest state.

One row per submission. Re-running the wizard creates a NEW row; we
never UPDATE these. Carries the LIFF-prompted `submitter_name` (the
"ชื่อ/ชื่อบริษัท" textbox shown before the wizard starts) and a
direct ref to the LINE platform user id so we can correlate submissions
across the same email even when the user_id row gets re-bound.
"""

from sqlalchemy import Column, BigInteger, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgMaterialitySubmission(Base, BaseModel):
    __tablename__ = 'esg_materiality_submissions'

    user_id = Column(BigInteger)
    organization_id = Column(BigInteger)

    # Captured from the LIFF wizard's pre-assessment textbox.
    submitter_name = Column(String(255), nullable=False)

    # LINE identity refs. Optional (web flow won't have them).
    line_user_id = Column(String(64))
    line_display_name = Column(String(255))

    # Snapshot at submit time
    questions_version = Column(String(32))
    answers = Column(JSONB, nullable=False, default=dict)
    derived_categories = Column(JSONB, nullable=False, default=list)
    category_scores = Column(JSONB, nullable=False, default=dict)
    industry_other_text = Column(String(255))

    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'userId': self.user_id,
            'organizationId': self.organization_id,
            'submitterName': self.submitter_name,
            'lineUserId': self.line_user_id,
            'lineDisplayName': self.line_display_name,
            'questionsVersion': self.questions_version,
            'answers': self.answers or {},
            'derivedCategories': self.derived_categories or [],
            'categoryScores': self.category_scores or {},
            'industryOtherText': self.industry_other_text,
            'submittedAt': self.submitted_at.isoformat() if self.submitted_at else None,
            'createdDate': self.created_date.isoformat() if self.created_date else None,
        }
