"""
"[DEBUG] Test Scale" stamp for IoT scale intake.

While an admin has Debug Log Mode on for a device (backoffice
/v3-iot-devices/show/{id} → POST /api/admin/iot-devices/{id}/debug-log, active
for 1 hour), every weighing that device posts to /api/iot-devices/records gets
its notes stamped so test data can be told apart from real intake in the
transaction list, exports and reports.

Decided on the server, not the tablet: no app release is needed, and a tablet
can neither forget the flag nor send it on its own.

Source of truth is the same one /sync uses for `debug_log_active`:
iot_device_health.raw->>'debug_log_until' compared against now. Turning the
mode off (key removed) or letting the hour lapse stops the stamping.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

DEBUG_NOTE = '[DEBUG] Test Scale'


def _parse_until(value: Any) -> Optional[datetime]:
    """'YYYY-MM-DDTHH:MM:SSZ' (as written by the admin toggle) → aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_debug_log_active(db_session, device_id: Any, now: Optional[datetime] = None) -> bool:
    """True while the device's Debug Log Mode window is open.

    Any read failure means "not in debug": stamping real intake as test data
    would be the worse mistake.
    """
    if not device_id:
        return False
    try:
        row = db_session.execute(text(
            "SELECT raw->>'debug_log_until' "
            "FROM iot_device_health WHERE device_id = :device_id"
        ), {'device_id': device_id}).fetchone()
    except Exception as exc:  # noqa: BLE001 — a flag read must never break a weighing
        logger.warning("[debug_stamp] debug_log_until read failed for %s: %s", device_id, exc)
        return False
    until = _parse_until(row[0] if row else None)
    return until is not None and until > (now or datetime.now(timezone.utc))


def _prefixed(existing: Any) -> str:
    s = str(existing).strip() if existing else ''
    if s.startswith(DEBUG_NOTE):
        return s  # idempotent — a retried post must not stack the prefix
    return f"{DEBUG_NOTE}\n{s}" if s else DEBUG_NOTE


def stamp_debug_notes(data: Dict[str, Any]) -> None:
    """Prefix the transaction's notes and every record's notes, in place.

    Records are stamped too because they are listed and exported on their own,
    and their notes already carry the tablet name, which is kept after the
    prefix.
    """
    data['notes'] = _prefixed(data.get('notes'))
    for rec in (data.get('records') or []):
        if isinstance(rec, dict):
            rec['notes'] = _prefixed(rec.get('notes'))
