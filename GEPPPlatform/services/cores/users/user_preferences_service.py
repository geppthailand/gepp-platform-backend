"""
Per-user UI preferences (report settings + transaction-list columns).

Stored as JSON on the user's `user_locations_settings` row (migration 091), so they follow
the user across devices and the PDF export can read them without the browser.

Only known keys with valid values are stored; anything else in a request is dropped. That
keeps the JSON a small, predictable contract instead of a free-form bag the report code has
to defend against.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from ....models.users.user_locations_settings import UserLocationSettings

REPORT_MODES = ('location', 'tag', 'tenant')
OVERVIEW_CHART_MODES = ('yearly', 'monthly', 'daily')
COMPARE_MODES = ('yearly', 'monthly')

REPORT_DEFAULTS: Dict[str, Any] = {
    'mode': 'location',
    'overview_chart': 'monthly',
    'compare_mode': 'yearly',
}

_COLUMN_KEY = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{0,63}$')
_MAX_COLUMNS = 60


def _clean_report(patch: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if patch.get('mode') in REPORT_MODES:
        out['mode'] = patch['mode']
    if patch.get('overview_chart') in OVERVIEW_CHART_MODES:
        out['overview_chart'] = patch['overview_chart']
    if patch.get('compare_mode') in COMPARE_MODES:
        out['compare_mode'] = patch['compare_mode']
    return out


def _clean_columns(value: Any) -> Optional[List[Dict[str, Any]]]:
    """[{key, visible}] in display order; None when the value isn't a usable list."""
    if not isinstance(value, list):
        return None
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in value[:_MAX_COLUMNS]:
        if not isinstance(item, dict):
            continue
        key = item.get('key')
        if not isinstance(key, str) or not _COLUMN_KEY.match(key) or key in seen:
            continue
        seen.add(key)
        out.append({'key': key, 'visible': bool(item.get('visible', True))})
    return out


def _clean_transaction(patch: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ('transaction_columns', 'record_columns'):
        cols = _clean_columns(patch.get(key))
        if cols is not None:
            out[key] = cols
    return out


class UserPreferencesService:
    def __init__(self, db):
        self.db = db

    def _row(self, user_location_id: int) -> Optional[UserLocationSettings]:
        return self.db.query(UserLocationSettings).filter(
            UserLocationSettings.user_location_id == user_location_id,
            UserLocationSettings.deleted_date.is_(None),
        ).first()

    def get(self, user_location_id: Optional[int]) -> Dict[str, Any]:
        """Effective preferences: stored values over defaults (report), stored as-is (columns)."""
        row = self._row(int(user_location_id)) if user_location_id else None
        report = dict(REPORT_DEFAULTS)
        report.update(_clean_report((row.report_preferences or {}) if row else {}))
        transaction = _clean_transaction((row.transaction_preferences or {}) if row else {})
        return {'report_preferences': report, 'transaction_preferences': transaction}

    def update(self, user_location_id: int, organization_id: Optional[int], body: Dict[str, Any]) -> Dict[str, Any]:
        """Merge the given top-level keys into the stored JSON (other keys are kept)."""
        report_patch = _clean_report(body.get('report_preferences') or {}) if isinstance(body.get('report_preferences'), dict) else {}
        txn_patch = _clean_transaction(body.get('transaction_preferences') or {}) if isinstance(body.get('transaction_preferences'), dict) else {}
        row = self._row(user_location_id)
        if not row:
            row = UserLocationSettings(
                user_location_id=user_location_id,
                organization_id=organization_id,
                input_destination=False,
                show_all_location_options=True,
                report_preferences={},
                transaction_preferences={},
            )
            self.db.add(row)
        if organization_id and not row.organization_id:
            row.organization_id = organization_id
        if report_patch:
            row.report_preferences = {**(row.report_preferences or {}), **report_patch}
            flag_modified(row, 'report_preferences')
        if txn_patch:
            row.transaction_preferences = {**(row.transaction_preferences or {}), **txn_patch}
            flag_modified(row, 'transaction_preferences')
        self.db.commit()
        self.db.refresh(row)
        return self.get(user_location_id)
