"""
IoT Devices HTTP handlers
Handles all /api/iot-devices/* routes
"""

import time as _time_mod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from GEPPPlatform.services.cores.transactions.transaction_handlers import handle_create_transaction
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.users.user_service import UserService
from GEPPPlatform.services.cores.users.user_handlers import handle_get_location_allowed_materials
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from GEPPPlatform.models.cores.references import Material
from GEPPPlatform.models.cores.iot_devices import IoTDevice

from ....exceptions import APIException, UnauthorizedException, ValidationException, NotFoundException

import logging as _iot_log

_iot_logger = _iot_log.getLogger(__name__)


# ── Short-key → full-column mapper for heartbeat payload (bandwidth optimisation) ──
_HB_SHORT_KEY_MAP: Dict[str, str] = {
    'bl': 'battery_level',
    'bc': 'battery_charging',
    'tc': 'cpu_temp_c',
    'nt': 'network_type',
    'ns': 'network_strength',
    'ip': 'ip_address',
    'sf': 'storage_free_mb',
    'rf': 'ram_free_mb',
    'ov': 'os_version',
    'av': 'app_version',
    'cr': 'current_route',
    'cu': 'current_user_id',
    'co': 'current_org_id',
    'cl': 'current_location_id',
    'sc': 'scale_connected',
    'sm': 'scale_mac_bt',
    'cs': 'cache_summary',
    # Per-tablet GPS — written to iot_hardwares (not iot_device_health) by
    # the /sync handler so the location follows the physical tablet across
    # iot_devices logins. Tablet only includes these on full cycles.
    'lat': 'last_lat',
    'lng': 'last_lng',
    'acc': 'last_location_accuracy_m',
}

# Columns that map onto iot_device_health table — used to decide which UPSERT slots are valid.
_DEVICE_HEALTH_COLUMNS: Set[str] = {
    'battery_level', 'battery_charging', 'cpu_temp_c', 'network_type', 'network_strength',
    'ip_address', 'storage_free_mb', 'ram_free_mb', 'os_version', 'app_version',
    'current_route', 'current_user_id', 'current_org_id', 'current_location_id',
    'scale_connected', 'scale_mac_bt', 'cache_summary',
}

_ALLOWED_COMMAND_TYPES: Set[str] = {
    'force_login', 'force_logout', 'navigate', 'reset_to_home', 'reset_input',
    'overwrite_cache', 'clear_storage', 'restart_app', 'ping',
}


def _expand_hb_keys(hb: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Expand short heartbeat keys (e.g. ``bl``) onto full column names (``battery_level``).

    Unknown keys are dropped silently. Full-form keys pass through.
    Only keys mapping to known iot_device_health columns are kept.
    """
    if not isinstance(hb, dict):
        return {}
    expanded: Dict[str, Any] = {}
    for k, v in hb.items():
        if not isinstance(k, str):
            continue
        full = _HB_SHORT_KEY_MAP.get(k, k)
        if full in _DEVICE_HEALTH_COLUMNS:
            expanded[full] = v
    return expanded


def _emit_iot_event(db_session, event_type: str, organization_id=None, user_id=None, properties: dict = None):
    """Fire-and-forget CRM event emission for IoT events. Never raises and
    never poisons the outer transaction.

    Wrapped in a SAVEPOINT (nested transaction) so a failure inside the CRM
    layer — e.g. the known schema drift where `crm_events` is missing the
    `is_active` / `deleted_date` columns the ORM model assumes — gets rolled
    back without aborting the parent /sync upsert. Without this, the
    pending `CrmEvent` object stays in the session.identity_map and the
    next `commit()` re-fires the bad INSERT, turning every /sync into a
    500.
    """
    try:
        savepoint = db_session.begin_nested()
    except Exception as _exc:
        _iot_logger.warning("CRM emit_event: could not open savepoint: %s", _exc)
        return

    try:
        from GEPPPlatform.services.admin.crm.crm_service import emit_event
        emit_event(
            db_session,
            event_type=event_type,
            event_category='iot',
            organization_id=organization_id,
            user_location_id=user_id,
            properties=properties or {},
            # `crm_events.event_source` has a CHECK constraint accepting
            # only {'server','client','system','email_provider'}. The
            # tablet acts as a client — use that label. Previously emitted
            # 'device' which spammed the log with chk_crm_event_source
            # violations on every /sync (caught by the SAVEPOINT but still
            # noisy).
            event_source='client',
            commit=False,
        )
        # Force the INSERT now (inside the savepoint) so any schema drift
        # surfaces here and we can rollback the savepoint cleanly. If we
        # let the parent commit do the flush, the failure aborts the whole
        # transaction.
        try:
            db_session.flush()
        except Exception:
            raise
        savepoint.commit()
    except Exception as _exc:
        try:
            savepoint.rollback()
        except Exception:
            pass
        _iot_logger.warning("CRM emit_event non-fatal (iot): %s", _exc)


def handle_get_locations_by_membership(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any], db_session) -> Dict[str, Any]:
    """Handle POST /api/iot-devices/my-memberships - Get locations where current user is in members list (default role=dataInput)"""
    try:
        if not current_user or not current_user.get('user_id'):
            raise UnauthorizedException('Unauthorized')

        role = (query_params.get('role') or 'dataInput').strip()
        # Normalize common role variants used by clients/DB
        # DB memberships commonly store camelCase role (e.g. "dataInput")
        if role in ('data_input', 'data-input', 'datainput'):
            role = 'dataInput'
        organization_id = current_user.get('organization_id') if current_user else None

        if not organization_id:
            raise NotFoundException('User is not part of any organization')

        member_locations = user_service.get_locations_by_member(
            member_user_id=current_user['user_id'],
            role=role,
            organization_id=organization_id
        )

        member_origin_ids: List[int] = [
            int(loc.get('origin_id'))
            for loc in member_locations
            if loc.get('origin_id') is not None
        ]

        # Expand to include all descendants of member locations (based on org setup tree)
        def _expand_descendants_from_setup(
            setup_root_nodes,
            seed_ids: Set[int],
        ) -> Set[int]:
            if not setup_root_nodes or not seed_ids:
                return set(seed_ids)

            roots = setup_root_nodes
            if isinstance(roots, dict):
                roots = [roots]
            if not isinstance(roots, list):
                return set(seed_ids)

            expanded: Set[int] = set(seed_ids)

            def to_int(v) -> Optional[int]:
                if v is None:
                    return None
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
                return None

            def collect_all(node: Dict[str, Any]) -> None:
                nid = to_int(node.get('nodeId'))
                if nid is not None:
                    expanded.add(nid)
                children = node.get('children') or []
                if isinstance(children, list):
                    for ch in children:
                        if isinstance(ch, dict):
                            collect_all(ch)

            def walk(nodes: List[Dict[str, Any]]) -> None:
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    nid = to_int(node.get('nodeId'))
                    children = node.get('children') or []
                    if nid is not None and nid in seed_ids:
                        collect_all(node)
                    else:
                        if isinstance(children, list) and children:
                            walk([ch for ch in children if isinstance(ch, dict)])

            walk([n for n in roots if isinstance(n, dict)])
            return expanded

        setup = (
            db_session.query(OrganizationSetup)
            .filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True,
                OrganizationSetup.deleted_date.is_(None),
            )
            .order_by(OrganizationSetup.created_date.desc())
            .first()
        )

        expanded_ids = _expand_descendants_from_setup(
            setup.root_nodes if setup else None,
            set(member_origin_ids),
        )

        # Keep original membership order first, then append remaining descendants
        ordered_ids: List[int] = []
        seen: Set[int] = set()
        for mid in member_origin_ids:
            if mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        for did in sorted(expanded_ids - seen):
            ordered_ids.append(did)
            seen.add(did)

        # Build location paths for all returned locations
        location_paths = user_service._build_location_paths(
            organization_id=organization_id,
            location_data=[{'id': loc_id} for loc_id in ordered_ids],
        )
        
        # Get ALL materials (active and not deleted, no organization filtering)
        # Use eager loading to fetch category and main_material relationships
        all_materials = db_session.query(Material).options(
            joinedload(Material.category),
            joinedload(Material.main_material)
        ).filter(
            Material.is_active == True,
            Material.deleted_date.is_(None)
        ).all()
        
        # Format materials in the same structure as location materials
        materials_list = []
        for material in all_materials:
            material_obj = {
                'material_id': material.id,
                'name_en': material.name_en or '',
                'name_th': material.name_th or '',
                'category_id': material.category_id or 0,
                'main_material_id': material.main_material_id or 0,
                'unit_name_th': material.unit_name_th or 'กิโลกรัม',
                'unit_name_en': material.unit_name_en or 'Kilogram',
                'unit_weight': float(material.unit_weight) if material.unit_weight is not None else 1.0,
            }
            
            # Add category as object
            if material.category:
                material_obj['category'] = {
                    'id': material.category.id,
                    'name_en': material.category.name_en or '',
                    'name_th': material.category.name_th or '',
                    'code': material.category.code or '',
                }
            else:
                material_obj['category'] = None

            # Add main_material as object
            if material.main_material:
                material_obj['main_material'] = {
                    'id': material.main_material.id,
                    'name_en': material.main_material.name_en or '',
                    'name_th': material.main_material.name_th or '',
                    'name_local': material.main_material.name_local or '',
                    'code': material.main_material.code or '',
                }
            else:
                material_obj['main_material'] = None
            
            materials_list.append(material_obj)
        
        # Load tags and tenants per location (id, name, members)
        origin_ids = ordered_ids
        origin_to_loc = {}
        tag_ids_all = set()
        tenant_ids_all = set()
        if origin_ids:
            locations_orm = db_session.query(UserLocation).filter(
                UserLocation.id.in_(origin_ids),
                UserLocation.deleted_date.is_(None)
            ).all()
            origin_to_loc = {loc.id: loc for loc in locations_orm}
            for loc in locations_orm:
                for tid in (loc.tags or []):
                    tag_ids_all.add(int(tid) if isinstance(tid, str) and tid.isdigit() else tid)
                for tid in (loc.tenants or []):
                    tenant_ids_all.add(int(tid) if isinstance(tid, str) and tid.isdigit() else tid)
        tag_ids_all = [x for x in tag_ids_all if x is not None]
        tenant_ids_all = [x for x in tenant_ids_all if x is not None]
        tag_by_id = {}
        tenant_by_id = {}
        if tag_ids_all:
            tags_orm = db_session.query(UserLocationTag).filter(
                UserLocationTag.id.in_(tag_ids_all),
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.is_active == True,
                UserLocationTag.deleted_date.is_(None)
            ).all()
            tag_by_id = {t.id: t for t in tags_orm}
        if tenant_ids_all:
            tenants_orm = db_session.query(UserTenant).filter(
                UserTenant.id.in_(tenant_ids_all),
                UserTenant.organization_id == organization_id,
                UserTenant.is_active == True,
                UserTenant.deleted_date.is_(None)
            ).all()
            tenant_by_id = {t.id: t for t in tenants_orm}
        # Build locations_list with tags and tenants (id, name, members)
        locations_list = []
        for origin_id in ordered_ids:
            loc_orm = origin_to_loc.get(origin_id)
            if not loc_orm:
                continue
            location_path = location_paths.get(origin_id) or ''
            tags_list = []
            tenants_list = []
            if loc_orm:
                for tid in (loc_orm.tags or []):
                    tid_int = int(tid) if isinstance(tid, str) and tid.isdigit() else tid
                    t = tag_by_id.get(tid_int)
                    if t:
                        tags_list.append({
                            'id': t.id,
                            'name': t.name or f'Tag {t.id}',
                            'members': t.members or [],
                            'start_date': t.start_date.isoformat() if t.start_date else None,
                            'end_date': t.end_date.isoformat() if t.end_date else None
                        })
                for tid in (loc_orm.tenants or []):
                    tid_int = int(tid) if isinstance(tid, str) and tid.isdigit() else tid
                    t = tenant_by_id.get(tid_int)
                    if t:
                        tenants_list.append({
                            'id': t.id,
                            'name': t.name or f'Tenant {t.id}',
                            'members': t.members or [],
                            'start_date': t.start_date.isoformat() if t.start_date else None,
                            'end_date': t.end_date.isoformat() if t.end_date else None
                        })
            locations_list.append({
                'origin_id': origin_id,
                'display_name': (loc_orm.display_name if loc_orm and loc_orm.display_name else ''),
                'path': location_path,
                'tags': tags_list,
                'tenants': tenants_list
            })
        
        return {
            'success': True,
            'data': {
                'locations': locations_list,
                'materials': materials_list
            }
        }

    except Exception as e:
        raise APIException(f'Error fetching member locations: {str(e)}')

# ========== /sync + /commands/{id}/ack HANDLERS ==========


def _run_daily_log_cleanup(db_session) -> None:
    """Delete IoT device-log rows older than yesterday (UTC).

    Triggered by the day-rollover branch in `handle_iot_device_sync` —
    fires at most once per day per device (subsequent same-day syncs see a
    matching date on the previous last_seen_at). Three log tables get
    pruned:

      * iot_device_events         — append-only action trail (~50/min/device)
      * iot_device_health_history — 5-min health buckets (already 7-day
                                    retention via the aggregator, but we
                                    enforce 1-day here too so the user-spec
                                    is consistent across all log tables)
      * iot_device_commands       — only TERMINAL rows (succeeded / failed
                                    / expired). Pending / delivered cmds
                                    are NEVER pruned — those are the cmds
                                    the tablet hasn't picked up yet.

    "Older than yesterday" = `< CURRENT_DATE - INTERVAL '1 day'`. So if
    today is 2026-05-25, anything with date < 2026-05-24 dies; 2026-05-24
    + 2026-05-25 survive ≈ "1 full day" max retention.

    Per /sync (i.e. per device-tick) the cleanup is server-wide — it
    deletes across ALL devices, not just the calling one. Idempotent:
    once today's run cleared the boundary rows, subsequent runs are
    no-ops because the predicate `< CURRENT_DATE - 1` is already empty.
    """
    from sqlalchemy import text as _t

    db_session.execute(_t(
        "DELETE FROM iot_device_events "
        "WHERE occurred_at < CURRENT_DATE - INTERVAL '1 day'"
    ))
    db_session.execute(_t(
        "DELETE FROM iot_device_health_history "
        "WHERE bucket_start < CURRENT_DATE - INTERVAL '1 day'"
    ))
    db_session.execute(_t(
        "DELETE FROM iot_device_commands "
        "WHERE issued_at < CURRENT_DATE - INTERVAL '1 day' "
        "  AND status IN ('succeeded', 'failed', 'expired')"
    ))
    db_session.commit()


def _compute_next_interval(hb_full: Dict[str, Any], delivered_count: int) -> int:
    """Adaptive cadence per the plan."""
    if delivered_count > 0:
        return 5
    cache = hb_full.get('cache_summary')
    app_state = None
    if isinstance(cache, dict):
        app_state = cache.get('app_state')
    if app_state == 'background':
        return 120
    route = hb_full.get('current_route')
    if route in ('/welcome', '/login'):
        return 30
    return 10


def _coerce_dt(value: Any) -> Optional[datetime]:
    """Accept ISO string or epoch number; return tz-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            from dateutil.parser import parse as _parse
            dt = _parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    return None


def handle_iot_sync(db_session, current_device: Dict[str, Any], data: Dict[str, Any], current_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Combined heartbeat + event-batch + command-poll endpoint.

    Body shape:
        {
            "kind": "full" | "delta",
            "hb": {...short-keys or full keys...},
            "events": [{"occurred_at": ..., "event_type": ..., "route": ..., "payload": ..., "user_id": ..., "session_id": ...}],
            "long_poll": bool
        }
    """
    if not isinstance(data, dict):
        raise ValidationException('Body must be an object')

    device_id = current_device.get('device_id')
    if not device_id:
        raise UnauthorizedException('Unauthorized device')

    kind = (data.get('kind') or 'delta').strip()
    if kind not in ('full', 'delta'):
        raise ValidationException('kind must be full or delta')
    hb_raw = data.get('hb') or {}
    if not isinstance(hb_raw, dict):
        raise ValidationException('hb must be an object')
    expanded_hb = _expand_hb_keys(hb_raw)

    events_in = data.get('events') or []
    if not isinstance(events_in, list):
        raise ValidationException('events must be an array')

    # Cap event batch — overflow rejected with a warning event injected client-side next cycle.
    rejected_count = 0
    if len(events_in) > 50:
        rejected_count = len(events_in) - 50
        events_in = events_in[:50]

    long_poll_req = bool(data.get('long_poll', False))

    # ── 1. UPSERT iot_device_health ────────────────────────────────────────────
    # JSONB columns on iot_device_health (other than `raw`, which is handled
    # separately below). psycopg2 does not adapt a Python dict directly into
    # JSONB — we json.dumps these values AND wrap their placeholders in
    # CAST(... AS JSONB). Otherwise the upsert errors with
    #     (psycopg2.ProgrammingError) can't adapt type 'dict'
    import json as _json
    _JSONB_HEALTH_COLS = {'cache_summary'}

    # Build column->value mapping for known columns. last_seen_at always = NOW().
    upsert_cols: List[str] = []
    upsert_params: Dict[str, Any] = {'device_id': device_id}
    for col, val in expanded_hb.items():
        upsert_cols.append(col)
        if col in _JSONB_HEALTH_COLS and not isinstance(val, str):
            # dict / list / None → JSON string for psycopg2 adaptation.
            upsert_params[col] = _json.dumps(val) if val is not None else None
        else:
            upsert_params[col] = val

    def _placeholder(col: str) -> str:
        ph = f':{col}'
        return f'CAST({ph} AS JSONB)' if col in _JSONB_HEALTH_COLS else ph

    # Build the full SQL.  raw column handled separately for full vs delta.
    insert_cols = ['device_id', 'last_seen_at'] + upsert_cols + ['raw']
    insert_placeholders = (
        [':device_id', 'NOW()']
        + [_placeholder(c) for c in upsert_cols]
        + ['CAST(:raw_full AS JSONB)']
    )

    # raw_full = the full hb_raw dict (preserves short keys + any extras).
    upsert_params['raw_full'] = _json.dumps(hb_raw or {})

    if kind == 'full':
        # Replace raw with full snapshot, and set all known cols (NULLing missing ones).
        update_assignments = ['last_seen_at = NOW()']
        for col in _DEVICE_HEALTH_COLUMNS:
            if col in expanded_hb:
                update_assignments.append(f"{col} = EXCLUDED.{col}")
            else:
                # On full snapshot, blanks → NULL for clarity.
                update_assignments.append(f"{col} = NULL")
        update_assignments.append('raw = EXCLUDED.raw')
    else:
        # Delta: COALESCE merge — only update non-null fields, JSONB-merge raw.
        update_assignments = ['last_seen_at = NOW()']
        for col in expanded_hb.keys():
            update_assignments.append(f"{col} = COALESCE(EXCLUDED.{col}, iot_device_health.{col})")
        update_assignments.append('raw = COALESCE(iot_device_health.raw, \'{}\'::jsonb) || EXCLUDED.raw')

    # Capture the PREVIOUS last_seen_at so we can detect a UTC-day rollover
    # — used by the post-upsert daily-log cleanup. Cheap one-row read; the
    # ON CONFLICT path overwrites it in the same statement so without this
    # SELECT we'd lose the "yesterday" timestamp.
    _prev_row = db_session.execute(text(
        "SELECT last_seen_at FROM iot_device_health WHERE device_id = :device_id"
    ), {'device_id': device_id}).fetchone()
    _prev_last_seen = _prev_row[0] if _prev_row else None

    sql = (
        f"INSERT INTO iot_device_health ({', '.join(insert_cols)}) "
        f"VALUES ({', '.join(insert_placeholders)}) "
        f"ON CONFLICT (device_id) DO UPDATE SET {', '.join(update_assignments)} "
        f"RETURNING raw, current_route, cache_summary, last_seen_at"
    )

    res = db_session.execute(text(sql), upsert_params).fetchone()

    # ── 1b. GPS → iot_hardwares ────────────────────────────────────────
    # Tablet opportunistically reports its GPS coords on full cycles. We
    # write them onto the PHYSICAL tablet row (iot_hardwares) — not the
    # logical login (iot_devices) — so the location follows the tablet
    # across re-pairings. UPDATE is a no-op when the iot_devices row has
    # no hardware_id (legacy / unpaired login).
    try:
        _lat = hb_raw.get('lat')
        _lng = hb_raw.get('lng')
        if isinstance(_lat, (int, float)) and isinstance(_lng, (int, float)):
            _acc = hb_raw.get('acc')
            db_session.execute(text(
                "UPDATE iot_hardwares SET "
                "  last_lat = :lat, last_lng = :lng, "
                "  last_location_accuracy_m = :acc, "
                "  last_location_at = NOW(), "
                "  updated_date = NOW() "
                "WHERE id = ("
                "  SELECT hardware_id FROM iot_devices WHERE id = :device_id "
                ") "
                "  AND (SELECT hardware_id FROM iot_devices WHERE id = :device_id) IS NOT NULL"
            ), {
                'lat': float(_lat),
                'lng': float(_lng),
                'acc': float(_acc) if isinstance(_acc, (int, float)) else None,
                'device_id': device_id,
            })
    except Exception as _e:
        _iot_logger.warning("[/sync] GPS write skipped: %s", _e)

    # ── 1a. Day-rollover cleanup ───────────────────────────────────────
    # If today's date != the date of THIS device's previous /sync, we
    # crossed midnight (UTC). Use the rollover as a trigger to delete log
    # records older than yesterday — keeps device_events / older command
    # rows / older history buckets from accumulating forever.
    #
    # Spec: "วันที่ 25 เป็น trigger point ให้ลบของวันที่ 23 ทิ้ง" — i.e.
    # delete strictly before yesterday (CURRENT_DATE - 1 day). Today and
    # yesterday survive; everything else dies.
    #
    # The cleanup runs at most once per day per device because subsequent
    # syncs from the same tablet on the same UTC date find an updated
    # last_seen_at already in today's date and skip the branch.
    try:
        if _prev_last_seen is not None:
            from datetime import datetime as _dt, timezone as _tz
            now_utc = _dt.now(_tz.utc).date()
            prev_utc = _prev_last_seen.astimezone(_tz.utc).date() \
                if _prev_last_seen.tzinfo else _prev_last_seen.date()
            if prev_utc != now_utc:
                _run_daily_log_cleanup(db_session)
                _iot_logger.info(
                    "[/sync] daily log rollover trigger: prev=%s now=%s — cleanup ran",
                    prev_utc, now_utc,
                )
    except Exception as _e:
        # Cleanup is best-effort. If it ever fails, /sync must NOT fail —
        # the heartbeat is more important than disk hygiene.
        _iot_logger.warning("[/sync] daily log cleanup error (non-fatal): %s", _e)
    # Force-flush the upsert to the DB right now (still inside the parent
    # transaction). If anything later in this handler fails or rolls back,
    # the rollback would otherwise undo the heartbeat too — defeating the
    # whole point. Flushing here pins the row to the connection so a later
    # failure inside (e.g.) the CRM emit only loses the savepoint, not this.
    try:
        db_session.flush()
    except Exception as _e:
        _iot_logger.error("[/sync] iot_device_health flush failed: %s", _e)
        raise
    _iot_logger.info(
        "[/sync] iot_device_health upsert OK device_id=%s kind=%s last_seen_at=%s",
        device_id, kind, res[3] if res is not None else None,
    )

    raw_after = {}
    current_route_after = None
    cache_after = None
    if res is not None:
        raw_after = (res[0] or {}) if not isinstance(res[0], str) else _json.loads(res[0])
        current_route_after = res[1]
        cache_after = res[2] or {}
    if isinstance(cache_after, str):
        try:
            cache_after = _json.loads(cache_after)
        except Exception:
            cache_after = {}

    # ── 2. Bulk-INSERT iot_device_events ─────────────────────────────────────
    if events_in:
        ev_sql = text(
            "INSERT INTO iot_device_events "
            "(device_id, occurred_at, event_type, route, payload, user_id, session_id) "
            "VALUES (:device_id, :occurred_at, :event_type, :route, CAST(:payload AS jsonb), :user_id, :session_id)"
        )
        for ev in events_in:
            if not isinstance(ev, dict):
                continue
            occurred = _coerce_dt(ev.get('occurred_at')) or datetime.now(timezone.utc)
            etype = (ev.get('event_type') or 'unknown').strip()[:48]
            db_session.execute(ev_sql, {
                'device_id': device_id,
                'occurred_at': occurred,
                'event_type': etype,
                'route': (ev.get('route') or None),
                'payload': _json.dumps(ev.get('payload') or {}),
                'user_id': ev.get('user_id'),
                'session_id': (ev.get('session_id') or None),
            })

    if rejected_count > 0:
        db_session.execute(text(
            "INSERT INTO iot_device_events (device_id, occurred_at, event_type, payload) "
            "VALUES (:device_id, NOW(), 'event_batch_overflow', CAST(:payload AS jsonb))"
        ), {
            'device_id': device_id,
            'payload': _json.dumps({'rejected_count': rejected_count}),
        })

    # ── 3. Atomically claim pending commands (limit 10) ─────────────────
    claim_sql = text(
        "UPDATE iot_device_commands "
        "SET status='delivered', delivered_at=NOW() "
        "WHERE id IN ("
        "  SELECT id FROM iot_device_commands "
        "  WHERE device_id = :device_id AND status='pending' AND expires_at > NOW() "
        "  ORDER BY issued_at ASC LIMIT 10 FOR UPDATE SKIP LOCKED"
        ") "
        "RETURNING id, command_type, payload"
    )
    rows = db_session.execute(claim_sql, {'device_id': device_id}).fetchall()
    cmds: List[Dict[str, Any]] = [
        {'id': r[0], 'type': r[1], 'payload': r[2]}
        for r in rows
    ]

    # ── 4. Long-poll (best-effort) ───────────────────────────────────────
    # Long-poll if device asked for it OR admin is "watching" this device.
    server_long_poll = False
    admin_watching = raw_after.get('admin_watching_until') if isinstance(raw_after, dict) else None
    if admin_watching:
        try:
            admin_watching_dt = _coerce_dt(admin_watching)
            if admin_watching_dt and admin_watching_dt > datetime.now(timezone.utc):
                server_long_poll = True
        except Exception:
            pass

    if not cmds and (long_poll_req or server_long_poll):
        # Commit the heartbeat/events first so the row is visible mid-poll.
        try:
            db_session.commit()
        except Exception:
            pass

        max_iterations = 50  # 50 × 0.5s = 25s wall-clock cap
        for _ in range(max_iterations):
            _time_mod.sleep(0.5)
            rows = db_session.execute(claim_sql, {'device_id': device_id}).fetchall()
            if rows:
                cmds = [{'id': r[0], 'type': r[1], 'payload': r[2]} for r in rows]
                break

    # Build hb_full for cadence calculation.
    hb_full_for_cadence: Dict[str, Any] = {}
    if isinstance(raw_after, dict):
        hb_full_for_cadence.update(_expand_hb_keys(raw_after))
    if current_route_after:
        hb_full_for_cadence['current_route'] = current_route_after
    if cache_after:
        hb_full_for_cadence['cache_summary'] = cache_after

    next_interval_s = _compute_next_interval(hb_full_for_cadence, len(cmds))

    # CRM event piggyback: keep legacy heartbeat emission (non-fatal).
    _emit_iot_event(
        db_session,
        event_type='iot_heartbeat',
        organization_id=(current_user or {}).get('organization_id') if current_user else None,
        user_id=(current_user or {}).get('user_id') if current_user else None,
        properties={
            'device_id': device_id,
            'kind': kind,
            'events_count': len(events_in),
            'cmds_delivered': len(cmds),
        },
    )

    return {
        'cmds': cmds,
        'next_interval_s': next_interval_s,
        'server_time': datetime.now(timezone.utc).isoformat(),
        'long_poll_active': bool(server_long_poll),
    }


def handle_iot_command_ack(db_session, current_device: Dict[str, Any], command_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Device acks a command outcome."""
    if not isinstance(data, dict):
        raise ValidationException('Body must be an object')

    device_id = current_device.get('device_id')
    if not device_id:
        raise UnauthorizedException('Unauthorized device')

    status = (data.get('status') or '').strip()
    if status not in ('succeeded', 'failed'):
        raise ValidationException("status must be 'succeeded' or 'failed'")

    result_payload = data.get('result') or {}
    import json as _json

    # UPDATE only if device matches (one device cannot ack another's command).
    res = db_session.execute(text(
        "UPDATE iot_device_commands "
        "SET status = :status, result = CAST(:result AS jsonb), acked_at = NOW(), completed_at = NOW() "
        "WHERE id = :command_id AND device_id = :device_id "
        "RETURNING command_type"
    ), {
        'status': status,
        'result': _json.dumps(result_payload),
        'command_id': command_id,
        'device_id': device_id,
    }).fetchone()

    if res is None:
        raise NotFoundException('Command not found or does not belong to this device')

    command_type = res[0]

    # Auto-insert a 'command_executed' event row.
    db_session.execute(text(
        "INSERT INTO iot_device_events (device_id, occurred_at, event_type, payload) "
        "VALUES (:device_id, NOW(), 'command_executed', CAST(:payload AS jsonb))"
    ), {
        'device_id': device_id,
        'payload': _json.dumps({
            'command_id': command_id,
            'command_type': command_type,
            'status': status,
            'result': result_payload,
        }),
    })

    return {'ok': True}


# ========== MAIN ROUTE HANDLER ==========

def handle_iot_devices_routes(event: Dict[str, Any], data: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all IoT devices-related endpoints
    """
    db_session = common_params.get('db_session')
    method = common_params.get('method', '')
    query_params = common_params.get('query_params', {})
    current_device = common_params.get('current_device', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    if not current_device or not current_device.get('device_id'):
        raise UnauthorizedException('Unauthorized device')
    
    # Check organization match between device and user (if user is present)
    if current_user and current_user.get('user_id'):
        device_id = current_device.get('device_id')
        device = db_session.query(IoTDevice).filter_by(
            id=device_id,
            is_active=True
        ).first()
        
        if not device:
            raise NotFoundException('Device not found')
        
        user_organization_id = current_user.get('organization_id')
        device_organization_id = device.organization_id
        
        # Only check if both have organization IDs set
        if user_organization_id is not None and device_organization_id is not None:
            if user_organization_id != device_organization_id:
                raise UnauthorizedException('User organization does not match device organization')
    
    try:
        if method == '':
            raise APIException(
                f"Method is invalid",
                status_code=405,
                error_code="INVALID_METHOD"
            )

        # ── New: combined heartbeat/events/command-poll ──────────────
        if path == '/api/iot-devices/sync':
            if method != 'POST':
                raise APIException('Method not allowed', status_code=405, error_code='INVALID_METHOD')
            return handle_iot_sync(db_session, current_device, data or {}, current_user=current_user)

        # ── New: device acks a command ──────────────────────────────
        if '/api/iot-devices/commands/' in path and path.endswith('/ack'):
            if method != 'POST':
                raise APIException('Method not allowed', status_code=405, error_code='INVALID_METHOD')
            try:
                command_id = int(path.split('/api/iot-devices/commands/')[1].split('/')[0])
            except (ValueError, IndexError):
                raise ValidationException('Invalid command id')
            return handle_iot_command_ack(db_session, current_device, command_id, data or {})

        if path == '/api/iot-devices/my-memberships':
            # Use UserService for membership-based location lookup
            user_service = UserService(db_session)
            return handle_get_locations_by_membership(user_service, query_params, current_user, db_session)
        if path == '/api/iot-devices/records':
            data = data.get('data')
            if not data:
                raise ValidationException('Data is required')
            transaction_service = TransactionService(db_session)
            current_user_id = current_user.get('user_id')
            current_user_organization_id = current_user.get('organization_id')
            result = handle_create_transaction(
                transaction_service,
                data,
                current_user_id,
                current_user_organization_id
            )
            # ── CRM: emit scale_reading_received ──
            _emit_iot_event(
                db_session,
                event_type='scale_reading_received',
                organization_id=current_user_organization_id,
                user_id=current_user_id,
                properties={
                    'device_id': current_device.get('device_id'),
                    'transaction_id': result.get('transaction_id') if isinstance(result, dict) else None,
                    'origin_id': data.get('origin_id') if isinstance(data, dict) else None,
                },
            )
            return result
        if path == '/api/iot-devices/qr-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login_iot_user(data, **common_params)
        if path == '/api/iot-devices/manual-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login(data, **common_params)
        if path == '/api/iot-devices/user-id-login':
            auth_handler = AuthHandlers(db_session)
            # Use user_id from body to login, return as normal manual login
            user_id = data.get('user_id')
            
            if not user_id:
                raise ValidationException('user_id is required')
            
            # Get user by user_id
            user = db_session.query(UserLocation).filter_by(
                id=user_id,
                is_active=True
            ).first()
            
            if not user:
                raise UnauthorizedException('Invalid user_id')
            
            # Generate JWT auth and refresh tokens
            tokens = auth_handler.generate_jwt_tokens(user.id, user.organization_id, user.email)
            
            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 60 minutes in seconds
                'user': {
                    'id': user.id,
                    'email': user.email or '',
                    'displayName': user.display_name or '',
                    'organization_id': user.organization_id or 0
                }
            }
        if '/api/iot-devices/locations/' in path and path.endswith('/allowed-materials') and method == 'POST':
            # GET /api/iot-devices/locations/{location_id}/allowed-materials
            if not current_user or not current_user.get('user_id'):
                raise UnauthorizedException('User token is required')
            location_id = path.split('/locations/')[1].split('/')[0]
            organization_id = current_user.get('organization_id')
            if not organization_id:
                raise ValidationException('User is not associated with an organization')
            # Verify user is a member of the requested location (including descendants)
            user_service = UserService(db_session)
            member_locations = user_service.get_locations_by_member(
                member_user_id=current_user['user_id'],
                organization_id=organization_id
            )
            member_origin_ids: Set[int] = {
                int(loc.get('origin_id'))
                for loc in member_locations
                if loc.get('origin_id') is not None
            }
            # Expand to include descendants via org setup tree
            setup = (
                db_session.query(OrganizationSetup)
                .filter(
                    OrganizationSetup.organization_id == organization_id,
                    OrganizationSetup.is_active == True,
                    OrganizationSetup.deleted_date.is_(None),
                )
                .order_by(OrganizationSetup.created_date.desc())
                .first()
            )
            if setup and setup.root_nodes:
                roots = setup.root_nodes
                if isinstance(roots, dict):
                    roots = [roots]
                if isinstance(roots, list):
                    def _to_int(v) -> Optional[int]:
                        if v is None:
                            return None
                        if isinstance(v, int):
                            return v
                        if isinstance(v, str) and v.isdigit():
                            return int(v)
                        return None

                    def _collect_all(node: Dict[str, Any], ids: Set[int]) -> None:
                        nid = _to_int(node.get('nodeId'))
                        if nid is not None:
                            ids.add(nid)
                        for ch in (node.get('children') or []):
                            if isinstance(ch, dict):
                                _collect_all(ch, ids)

                    def _walk(nodes: List[Dict[str, Any]], seed: Set[int], out: Set[int]) -> None:
                        for node in nodes:
                            if not isinstance(node, dict):
                                continue
                            nid = _to_int(node.get('nodeId'))
                            children = node.get('children') or []
                            if nid is not None and nid in seed:
                                _collect_all(node, out)
                            elif isinstance(children, list) and children:
                                _walk([ch for ch in children if isinstance(ch, dict)], seed, out)

                    expanded: Set[int] = set(member_origin_ids)
                    _walk([n for n in roots if isinstance(n, dict)], member_origin_ids, expanded)
                    member_origin_ids = expanded

            if int(location_id) not in member_origin_ids:
                raise UnauthorizedException('User is not a member of this location')
            return handle_get_location_allowed_materials(db_session, location_id, organization_id)

        # Unknown route under /api/iot-devices
        raise NotFoundException('Endpoint not found')

    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except UnauthorizedException as e:
        raise APIException(str(e), status_code=401, error_code="UNAUTHORIZED")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )
