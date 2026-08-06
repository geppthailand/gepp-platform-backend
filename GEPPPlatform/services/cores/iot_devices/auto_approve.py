"""
Auto-approval switch for IoT scale intake.

A transaction posted by a digital scale (POST /api/iot-devices/records) is normally
written as `pending` and waits for a human or the AI audit. Organisations that trust
the reading on the tablet (the operator confirms the weight before saving) can have
it written as `approved` straight away instead.

Resolution order — first match wins:

  1. device_settings.auto_approve_mode == 'on' / 'off'   (per-device override)
  2. organizations.auto_approve_scale_transactions        (per-org switch, migration 078)
  3. False                                                (system default)

The per-device override wins in BOTH directions on purpose: pulling one
misbehaving scale out of auto-approval must not require flipping the whole org,
and piloting one scale must not require flipping it either.

Both reads are column-only SELECTs — this runs on every single weighing.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Kept in sync with AdminService._SETTINGS_AUTO_APPROVE_MODES.
_MODES = ('inherit', 'on', 'off')

# Returned as `source` so the caller can record WHY a transaction was
# auto-approved in its audit note.
SOURCE_DEVICE = 'device'
SOURCE_ORG = 'org'
SOURCE_DEFAULT = 'default'


def _device_mode(db_session, device_id: Any) -> str:
    """The device's override mode, or 'inherit' when unset/unreadable."""
    if not device_id:
        return 'inherit'
    try:
        row = db_session.execute(text(
            "SELECT device_settings->>'auto_approve_mode' "
            "FROM iot_devices WHERE id = :device_id AND deleted_date IS NULL"
        ), {'device_id': device_id}).fetchone()
    except Exception as exc:  # noqa: BLE001 — column added by migration 062
        logger.warning("[auto_approve] device_settings read failed for %s: %s", device_id, exc)
        return 'inherit'

    mode = (row[0] if row and row[0] else '') or ''
    mode = str(mode).strip().lower()
    return mode if mode in _MODES else 'inherit'


def _org_flag(db_session, organization_id: Any) -> bool:
    """The org-level switch, or False when unset/unreadable."""
    if not organization_id:
        return False
    try:
        row = db_session.execute(text(
            "SELECT auto_approve_scale_transactions "
            "FROM organizations WHERE id = :organization_id"
        ), {'organization_id': organization_id}).fetchone()
    except Exception as exc:  # noqa: BLE001 — column added by migration 078
        logger.warning(
            "[auto_approve] organizations flag read failed for %s (migration 078 not run?): %s",
            organization_id, exc,
        )
        return False
    return bool(row[0]) if row else False


def resolve_auto_approve(
    db_session,
    device_id: Any,
    organization_id: Any,
) -> Tuple[bool, str]:
    """Return (auto_approve_enabled, source).

    `source` is one of 'device' / 'org' / 'default' and is recorded in the
    auto-approval audit note so an auditor can tell later which switch caused it.
    Any read failure degrades to (False, 'default') — the safe direction is
    always "leave it pending for a human".
    """
    mode = _device_mode(db_session, device_id)
    if mode == 'on':
        return True, SOURCE_DEVICE
    if mode == 'off':
        return False, SOURCE_DEVICE

    if _org_flag(db_session, organization_id):
        return True, SOURCE_ORG
    return False, SOURCE_DEFAULT


def stamp_scale_origin(data: Dict[str, Any]) -> None:
    """Mark a create-transaction payload as coming from a scale, in place.

    The tablet posts `transaction_type: 'manual_input'` and `transaction_method: 'origin'`,
    which makes a weighing indistinguishable from something typed on the web — the operator
    on the tablet is the creator either way. Anything arriving on /api/iot-devices/records
    came from a device by definition, so the server stamps the source itself rather than
    waiting for an app release (and old tablets get it right too).

      • transaction_method='scale_input' — transaction-level, so the list can label and
        filter without joining records. The value already exists in the DB constraint
        (migration 002) and nothing was writing it.
      • transaction_type='iot' — record-level, the value the schema always intended for
        this channel.

    Rows created before this shipped cannot be back-filled: nothing distinguishes them.
    """
    data['transaction_method'] = 'scale_input'
    for record in (data.get('records') or data.get('transaction_records') or []):
        if isinstance(record, dict):
            record['transaction_type'] = 'iot'


def apply_auto_approve_to_payload(data: Dict[str, Any]) -> None:
    """Mark a create-transaction payload as approved, in place.

    Both levels must be set: `transactions.status` drives the transaction list and
    the traceability first hop, while `transaction_records[].status` is what the
    manual-audit inbox and the aggregated status column in the UI actually read.
    Setting only one of them leaves the two views disagreeing.
    """
    data['status'] = 'approved'
    for record in (data.get('records') or data.get('transaction_records') or []):
        if isinstance(record, dict):
            record['status'] = 'approved'
