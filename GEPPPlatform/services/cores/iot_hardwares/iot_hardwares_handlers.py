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


def _coerce_int(v: Any, lo: int | None = None, hi: int | None = None) -> Any:
    """Best-effort int coercion for telemetry fields.

    Telemetry is advisory — a tablet sending garbage must never break its
    own checkin, so anything unparseable becomes None rather than raising.
    """
    if v is None or v == '':
        return None
    try:
        n = int(float(v))
    except Exception:
        return None
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def _coerce_bool(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ('true', '1', 'yes', 'y'):
            return True
        if s in ('false', '0', 'no', 'n'):
            return False
    return None


def handle_iot_hardware_checkin(event: Dict[str, Any], data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """POST /api/iot-hardwares/checkin

    Body: { mac_address, serial_number?, device_code?, device_model?,
            os_version?, app_version?,
            battery_level?, battery_charging?, network_type?,
            network_strength?, storage_free_mb? }

    Returns: { ok: true, hardware_id, force_login? }

    Telemetry (battery / network / storage) is optional and advisory. It is
    stored on the hardware row AND bucketed into
    `iot_hardware_battery_history` because this endpoint is the ONLY path
    that sees a tablet which has never been paired — `iot_device_health` is
    keyed on `device_id` and can't represent one.
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

    # Optional telemetry. Clamped rather than validated — see _coerce_int.
    battery_level = _coerce_int(
        data.get('battery_level', data.get('batteryLevel')), 0, 100
    )
    battery_charging = _coerce_bool(
        data.get('battery_charging', data.get('batteryCharging'))
    )
    network_type = _coerce_str(
        data.get('network_type') or data.get('networkType'), 16
    )
    network_strength = _coerce_int(
        data.get('network_strength', data.get('networkStrength')), 0, 100
    )
    storage_free_mb = _coerce_int(
        data.get('storage_free_mb', data.get('storageFreeMb')), 0
    )
    has_telemetry = any(
        v is not None for v in (
            battery_level, battery_charging, network_type,
            network_strength, storage_free_mb,
        )
    )

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
        "   os_version, app_version, last_checkin_at, last_ip_address, "
        "   last_battery_level, last_battery_charging, last_network_type, "
        "   last_network_strength, last_storage_free_mb, last_telemetry_at, "
        "   checkin_count, first_checkin_at) "
        "VALUES (:mac, :serial, :code, :model, :ov, :av, NOW(), :ip, "
        "        :bat, :chg, :nt, :ns, :sf, "
        "        CASE WHEN :has_tel THEN NOW() ELSE NULL END, "
        "        1, NOW()) "
        "ON CONFLICT (mac_address) DO UPDATE SET "
        "  serial_number = COALESCE(EXCLUDED.serial_number, iot_hardwares.serial_number), "
        "  device_code   = COALESCE(EXCLUDED.device_code, iot_hardwares.device_code), "
        "  device_model  = COALESCE(EXCLUDED.device_model, iot_hardwares.device_model), "
        "  os_version    = COALESCE(EXCLUDED.os_version, iot_hardwares.os_version), "
        "  app_version   = COALESCE(EXCLUDED.app_version, iot_hardwares.app_version), "
        "  last_checkin_at = NOW(), "
        "  last_ip_address = COALESCE(EXCLUDED.last_ip_address, iot_hardwares.last_ip_address), "
        # Telemetry is COALESCE'd rather than overwritten so an older app
        # build that doesn't send battery doesn't blank out the last known
        # reading captured by a newer one.
        "  last_battery_level    = COALESCE(EXCLUDED.last_battery_level, iot_hardwares.last_battery_level), "
        "  last_battery_charging = COALESCE(EXCLUDED.last_battery_charging, iot_hardwares.last_battery_charging), "
        "  last_network_type     = COALESCE(EXCLUDED.last_network_type, iot_hardwares.last_network_type), "
        "  last_network_strength = COALESCE(EXCLUDED.last_network_strength, iot_hardwares.last_network_strength), "
        "  last_storage_free_mb  = COALESCE(EXCLUDED.last_storage_free_mb, iot_hardwares.last_storage_free_mb), "
        "  last_telemetry_at     = CASE WHEN :has_tel THEN NOW() ELSE iot_hardwares.last_telemetry_at END, "
        "  checkin_count   = iot_hardwares.checkin_count + 1, "
        "  first_checkin_at = COALESCE(iot_hardwares.first_checkin_at, NOW()), "
        "  updated_date  = NOW() "
        "RETURNING id, paired_iot_device_id, pending_pin, lifecycle_status, "
        "          deleted_date"
    ), {
        'mac': mac,
        'serial': serial,
        'code': device_code,
        'model': device_model,
        'ov': os_version,
        'av': app_version,
        'ip': src_ip,
        'bat': battery_level,
        'chg': battery_charging,
        'nt': network_type,
        'ns': network_strength,
        'sf': storage_free_mb,
        'has_tel': has_telemetry,
    }).fetchone()

    hardware_id = int(row[0]) if row else None
    paired_device_id = int(row[1]) if (row and row[1] is not None) else None
    pending_pin = row[2] if (row and row[2] is not None) else None
    lifecycle_status = (row[3] if row else None) or 'active'
    is_deleted = bool(row[4]) if row else False

    # Bucket the telemetry into 15-min slots for the admin battery chart.
    # `date_bin` needs PG14+; `to_timestamp(floor(epoch/900)*900)` works
    # everywhere and is what the rest of this codebase can rely on.
    if hardware_id and has_telemetry:
        db_session.execute(text(
            "INSERT INTO iot_hardware_battery_history "
            "  (hardware_id, bucket_start, battery_level, battery_min, "
            "   battery_max, battery_charging, network_type, "
            "   network_strength, samples, last_checkin_at) "
            "VALUES (:hw, "
            "        to_timestamp(floor(extract(epoch FROM NOW()) / 900) * 900), "
            "        :bat, :bat, :bat, :chg, :nt, :ns, 1, NOW()) "
            "ON CONFLICT (hardware_id, bucket_start) DO UPDATE SET "
            "  battery_level    = COALESCE(EXCLUDED.battery_level, iot_hardware_battery_history.battery_level), "
            "  battery_min      = LEAST(COALESCE(EXCLUDED.battery_level, iot_hardware_battery_history.battery_min), "
            "                           COALESCE(iot_hardware_battery_history.battery_min, EXCLUDED.battery_level)), "
            "  battery_max      = GREATEST(COALESCE(EXCLUDED.battery_level, iot_hardware_battery_history.battery_max), "
            "                              COALESCE(iot_hardware_battery_history.battery_max, EXCLUDED.battery_level)), "
            "  battery_charging = COALESCE(EXCLUDED.battery_charging, iot_hardware_battery_history.battery_charging), "
            "  network_type     = COALESCE(EXCLUDED.network_type, iot_hardware_battery_history.network_type), "
            "  network_strength = COALESCE(EXCLUDED.network_strength, iot_hardware_battery_history.network_strength), "
            "  samples          = iot_hardware_battery_history.samples + 1, "
            "  last_checkin_at  = NOW()"
        ), {
            'hw': hardware_id,
            'bat': battery_level,
            'chg': battery_charging,
            'nt': network_type,
            'ns': network_strength,
        })

    db_session.commit()

    response: Dict[str, Any] = {
        'ok': True,
        'hardware_id': hardware_id,
        'server_time': datetime.now(timezone.utc).isoformat(),
        'next_interval_s': 5,
        # EXPLICIT pairing-state signal. The tablet uses this to detect
        # admin-initiated unpair from the backoffice — without an
        # explicit flag the tablet has no way to know "I used to be
        # paired, but my hardware row no longer has paired_iot_device_id"
        # versus "I just haven't been paired yet". Both cases produced
        # an identical response body before this field existed.
        #
        # Tablet handling:
        #   paired=true  → keep flowing (force_login below carries new
        #                   tokens iff the tablet doesn't have them yet);
        #   paired=false → if tablet is `setupComplete=true` locally,
        #                   that means the admin unpaired since the last
        #                   pair. Tablet wipes credentials, flips
        #                   setupComplete=false, and drops to
        #                   /device-setup.
        'paired': paired_device_id is not None,
        'paired_device_id': paired_device_id,
        # Lets the tablet show a "this unit is retired / in maintenance"
        # banner without a second call. Advisory only.
        'lifecycle_status': lifecycle_status,
    }

    # A soft-deleted or retired unit must never be handed fresh credentials.
    # NOTE: soft delete deliberately does NOT revive the row — the tablet
    # keeps checking in every ~5 s, so reviving on checkin would make the
    # admin Delete button appear not to work. `last_checkin_at` still
    # advances so the "Deleted" view shows when it last phoned home.
    login_blocked = is_deleted or lifecycle_status == 'retired'

    if is_deleted and hardware_id:
        # One breadcrumb per 24 h — enough for ops to notice "this deleted
        # tablet is still out there and switched on", without spamming the
        # timeline every 5 s.
        db_session.execute(text(
            "INSERT INTO iot_hardware_history "
            "  (hardware_id, event_type, severity, title, detail) "
            "SELECT :hw, 'checkin_after_delete', 'warning', "
            "       'Deleted hardware is still checking in', "
            "       'This unit was soft-deleted but is still powered on and "
            "reporting. Restore it if it is back in service, or power it down.' "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM iot_hardware_history "
            "   WHERE hardware_id = :hw AND event_type = 'checkin_after_delete' "
            "     AND created_date > NOW() - INTERVAL '24 hours')"
        ), {'hw': hardware_id})
        db_session.commit()

    # Pair-pending → return force_login directive with a freshly-minted JWT.
    # Tablet stores it like a normal device login + transitions to /sync flow.
    if paired_device_id and not login_blocked:
        device_row = db_session.execute(text(
            "SELECT id, device_name, device_type, organization_id, "
            "       (SELECT raw->>'admin_watching_until' "
            "          FROM iot_device_health WHERE device_id = iot_devices.id) "
            "         AS admin_watching_until "
            "FROM iot_devices WHERE id = :id AND deleted_date IS NULL"
        ), {'id': paired_device_id}).fetchone()
        # Wake-up signal: when an admin has just paired/unpaired/issued a
        # command (admin_watching_until > NOW()) we flip `sync_now: true` so
        # the tablet's HwCheckin loop calls sync_service.forceCycle() and
        # picks up the queued command within ~1 s instead of waiting for
        # the next adaptive sync cycle (up to 30 s in idle mode).
        if device_row and device_row[4]:
            try:
                from datetime import datetime as _dt
                watching_until_str = str(device_row[4])
                # Strip trailing 'Z' so fromisoformat parses on Python <3.11.
                if watching_until_str.endswith('Z'):
                    watching_until_str = watching_until_str[:-1] + '+00:00'
                if _dt.fromisoformat(watching_until_str) > datetime.now(timezone.utc):
                    response['sync_now'] = True
            except Exception:
                pass
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
