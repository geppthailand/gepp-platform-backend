"""
Materiality Filter Service.

Manages the per-user wizard state and the org-level Scope 3 category
whitelist on EsgOrganizationSettings.

The scoring is delegated to materiality_config.compute_scores() so the
frontend and backend share a single source of truth (both load the same
YAML at v3/frontend/gepp-esg/src/mat_filters/).

Endpoints (registered in esg_handlers.handle_esg_routes):
  GET    /api/esg/materiality/me            → get_state
  PATCH  /api/esg/materiality/me            → patch_progress
  POST   /api/esg/materiality/me/complete   → complete
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ...models.esg.user_materiality import EsgUserMateriality
from ...models.esg.settings import EsgOrganizationSettings
from . import materiality_config

logger = logging.getLogger(__name__)


class MaterialityService:
    def __init__(self, db: Session):
        self.db = db

    # ─── reads ──────────────────────────────────────────────────────────

    def _get_record(
        self, user_id: int, org_id: int
    ) -> Optional[EsgUserMateriality]:
        return (
            self.db.query(EsgUserMateriality)
            .filter(
                EsgUserMateriality.user_id == user_id,
                EsgUserMateriality.organization_id == org_id,
                EsgUserMateriality.deleted_date.is_(None),
            )
            .first()
        )

    def get_state(self, user_id: int, org_id: int) -> dict[str, Any]:
        rec = self._get_record(user_id, org_id)
        if not rec:
            return {
                'completed': False,
                'answers': {},
                'derivedCategories': [],
                'lastQuestionId': None,
                'questionsVersion': materiality_config.questions_version(),
            }
        out = rec.to_dict()
        out['questionsVersion'] = materiality_config.questions_version()
        # Echo the org whitelist so the frontend can refresh it without a
        # second round-trip.
        out['enabledScope3Categories'] = self._get_org_whitelist(org_id)
        return out

    def _get_org_whitelist(self, org_id: int) -> list[int]:
        settings = self._get_or_create_settings(org_id)
        existing = settings.enabled_scope3_categories or []
        if existing:
            return list(existing)
        return materiality_config.default_categories_pre_materiality()

    def _get_or_create_settings(self, org_id: int) -> EsgOrganizationSettings:
        settings = (
            self.db.query(EsgOrganizationSettings)
            .filter(EsgOrganizationSettings.organization_id == org_id)
            .first()
        )
        if not settings:
            settings = EsgOrganizationSettings(
                organization_id=org_id,
                enabled_scope3_categories=[],
                focus_mode='scope3_only',
            )
            self.db.add(settings)
            self.db.flush()
        return settings

    # ─── writes ─────────────────────────────────────────────────────────

    def patch_progress(
        self,
        user_id: int,
        org_id: int,
        answers: dict,
        last_question_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Autosave: upsert partial answers without flipping completed_at."""
        rec = self._get_record(user_id, org_id)
        if not rec:
            rec = EsgUserMateriality(
                user_id=user_id,
                organization_id=org_id,
                questions_version=materiality_config.questions_version(),
                answers=answers or {},
                last_question_id=last_question_id,
            )
            self.db.add(rec)
        else:
            # Merge: new keys overwrite old; we don't drop unrelated keys.
            merged = dict(rec.answers or {})
            merged.update(answers or {})
            rec.answers = merged
            if last_question_id:
                rec.last_question_id = last_question_id
            # Capture industry "Other" free-text for analytics.
            q1 = (answers or {}).get('q1_industry') or {}
            if q1.get('selected') == 'other' and q1.get('freeText'):
                rec.industry_other_text = q1.get('freeText')
        self.db.commit()
        return rec.to_dict()

    def complete(
        self,
        user_id: int,
        org_id: int,
        answers: dict,
    ) -> dict[str, Any]:
        """
        Final submit: re-runs scoring server-side, persists the result,
        and set-unions derived_categories into the org-level whitelist.
        """
        result = materiality_config.compute_scores(answers or {})
        derived = list(result.get('derivedCategories') or [])
        scores = {str(k): v for k, v in (result.get('scores') or {}).items()}

        # Upsert the per-user record.
        rec = self._get_record(user_id, org_id)
        if not rec:
            rec = EsgUserMateriality(
                user_id=user_id,
                organization_id=org_id,
                questions_version=materiality_config.questions_version(),
            )
            self.db.add(rec)
        rec.answers = answers or {}
        rec.derived_categories = derived
        rec.category_scores = scores
        rec.completed_at = datetime.now(timezone.utc)

        q1 = (answers or {}).get('q1_industry') or {}
        if q1.get('selected') == 'other' and q1.get('freeText'):
            rec.industry_other_text = q1.get('freeText')

        # Set-union into the org whitelist so any teammate's material
        # categories are visible across the org.
        settings = self._get_or_create_settings(org_id)
        existing = set(int(x) for x in (settings.enabled_scope3_categories or []))
        unioned = sorted(existing.union(int(x) for x in derived))
        settings.enabled_scope3_categories = unioned

        self.db.commit()

        return {
            'success': True,
            'derivedCategories': derived,
            'enabledScope3Categories': unioned,
            'scores': scores,
            'focusMode': settings.focus_mode or 'scope3_only',
        }
