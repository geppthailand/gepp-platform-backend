"""
IoT hardware registry — public checkin endpoint.

Routed in app.py BEFORE the auth-required branch so unauthenticated tablets
(those that haven't logged in yet) can self-report their identity. Every
~15 s while the app is open & screen on, the tablet POSTs to /checkin and
gets back either:

   { ok: true }                                   ← keep waiting
   { ok: true, force_login: { device_id, ... } }  ← admin paired you; log in

The force_login response contains a freshly-minted device JWT bound to the
paired iot_devices row, so the tablet can transition straight to the normal
device-token sync flow without needing a human to type credentials on-site.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text

from ....exceptions import APIException, ValidationException
from ...auth.auth_handlers import AuthHandlers


_logger = logging.getLogger(__name__)


def _coerce_str(v: Any, max_len: int = 128) -> Any:
    if v is None:
        return None
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    if not v:
        return None
    return v[:max_len]


def handle_iot_hardware_checkin(event: Dict[str, Any], data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """POST /api/iot-hardwares/checkin

    Body: { mac_address, serial_number?, device_code?, device_model?,
            os_version?, app_version? }

    Returns: { ok: true, hardware_id, force_login? }
    """
    db_session = kwargs.get('db_session')
    if db_session is None:
        raise APIException('db_session not provided to checkin handler')

    if not isinstance(data, dict):
        raise ValidationException('Body must be an object')

    mac = _coerce_str(data.get('mac_address') or data.get('mac') or data.get('macAddress'), 64)
    if not mac:
        raise ValidationException('mac_address is required')

    serial = _coerce_str(data.get('serial_number') or data.get('serial'), 128)
    device_code = _coerce_str(data.get('device_code'), 128)
    device_model = _coerce_str(data.get('device_model') or data.get('model'), 128)
    os_version = _coerce_str(data.get('os_version'), 64)
    app_version = _coerce_str(data.get('app_version'), 32)

    # Best-effort source IP. The Lambda event puts it under
    # requestContext.http.sourceIp; the Flask local server passes the headers.
    src_ip = None
    try:
        src_ip = (
            event.get('requestContext', {})
                 .get('http', {})
                 .get('sourceIp')
        )
        if not src_ip:
            hdrs = event.get('headers') or {}
            for k, v in hdrs.items():
                if k.lower() in ('x-forwarded-for', 'x-real-ip'):
                    src_ip = (v or '').split(',')[0].strip()
                    break
    except Exception:
        src_ip = None

    # UPSERT by mac_address. The PK on (mac_address) (UNIQUE constraint
    # in migration 051) makes this idempotent.
    row = db_session.execute(text(
        "INSERT INTO iot_hardwares "
        "  (mac_address, serial_number, device_code, device_model, "
        "   os_version, app_version, last_checkin_at, last_ip_address) "
        "VALUES (:mac, :serial, :code, :model, :ov, :av, NOW(), :ip) "
        "ON CONFLICT (mac_address) DO UPDATE SET "
        "  serial_number = COALESCE(EXCLUDED.serial_number, iot_hardwares.serial_number), "
        "  device_code   = COALESCE(EXCLUDED.device_code, iot_hardwares.device_code), "
        "  device_model  = COALESCE(EXCLUDED.device_model, iot_hardwares.device_model), "
        "  os_version    = COALESCE(EXCLUDED.os_version, iot_hardwares.os_version), "
        "  app_version   = COALESCE(EXCLUDED.app_version, iot_hardwares.app_version), "
        "  last_checkin_at = NOW(), "
        "  last_ip_address = COALESCE(EXCLUDED.last_ip_address, iot_hardwares.last_ip_address), "
        "  updated_date  = NOW() "
        "RETURNING id, paired_iot_device_id, pending_pin"
    ), {
        'mac': mac,
        'serial': serial,
        'code': device_code,
        'model': device_model,
        'ov': os_version,
        'av': app_version,
        'ip': src_ip,
    }).fetchone()
    db_session.commit()

    hardware_id = int(row[0]) if row else None
    paired_device_id = int(row[1]) if (row and row[1] is not None) else None
    pending_pin = row[2] if (row and row[2] is not None) else None

    response: Dict[str, Any] = {
        'ok': True,
        'hardware_id': hardware_id,
        'server_time': datetime.now(timezone.utc).isoformat(),
        'next_interval_s': 5,
    }

    # Pair-pending → return force_login directive with a freshly-minted JWT.
    # Tablet stores it like a normal device login + transitions to /sync flow.
    if paired_device_id:
        device_row = db_session.execute(text(
            "SELECT id, device_name, device_type, organization_id "
            "FROM iot_devices WHERE id = :id AND deleted_date IS NULL"
        ), {'id': paired_device_id}).fetchone()
        if device_row:
            try:
                auth = AuthHandlers(db_session)
                tokens = auth.generate_device_tokens(
                    int(device_row[0]),
                    device_row[1],
                )
                force_login: Dict[str, Any] = {
                    'device_id': int(device_row[0]),
                    'device_name': device_row[1],
                    'device_type': device_row[2],
                    'organization_id': (
                        int(device_row[3]) if device_row[3] is not None else None
                    ),
                    'auth_token': tokens.get('auth_token'),
                    'refresh_token': tokens.get('refresh_token'),
                    'token_type': 'Bearer',
                    'expires_in': 86400,
                }
                # Admin-supplied settings PIN — included once, cleared from
                # the row in the same transaction so the next checkin doesn't
                # leak it again. The tablet persists it locally on receipt.
                if pending_pin:
                    force_login['pin'] = pending_pin
                    db_session.execute(text(
                        "UPDATE iot_hardwares SET pending_pin = NULL, "
                        "  updated_date = NOW() WHERE id = :id"
                    ), {'id': hardware_id})
                    db_session.commit()
                response['force_login'] = force_login
            except Exception as e:
                _logger.warning(
                    "[iot-hardwares.checkin] failed to mint device tokens for paired_device_id=%s: %s",
                    paired_device_id, e,
                )

    return response


def handle_iot_hardware_routes(event: Dict[str, Any], data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Top-level public dispatch for /api/iot-hardwares/*."""
    raw_path = event.get('rawPath') or event.get('path') or ''
    method = (
        event.get('requestContext', {}).get('http', {}).get('method')
        or kwargs.get('method')
        or ''
    ).upper()

    # Only one public route exists today; future public actions can be added
    # alongside this dispatch.
    if method == 'POST' and raw_path.endswith('/checkin'):
        return handle_iot_hardware_checkin(event, data, **kwargs)

    raise APIException('Unknown iot-hardwares route', status_code=404)
