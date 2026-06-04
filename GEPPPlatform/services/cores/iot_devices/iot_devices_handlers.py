"""
IoT Devices HTTP handlers
Handles all /api/iot-devices/* routes
"""

import time as _time_mod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from sqlalchemy import text

from GEPPPlatform.services.cores.transactions.transaction_handlers import handle_create_transaction
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.users.user_service import UserService
from GEPPPlatform.services.cores.users.user_handlers import handle_get_location_allowed_materials
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from GEPPPlatform.models.cores.iot_devices import IoTDevice

from ....exceptions import APIException, UnauthorizedException, ValidationException, NotFoundException

import logging as _iot_log

_iot_logger = _iot_log.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Module-level cache for the global materials payload.
#
# `/api/iot-devices/my-memberships` is called by every tablet right
# after PIN login, and on each call it loads the *entire* Material
# table (no org filter — materials are global) through the ORM, joins
# `category` + `main_material`, and serialises every row to JSON. With
# a few hundred materials this is the dominant cost in the login flow.
#
# Since the dataset is global and rarely changes, we cache the
# already-serialised list in the warm Lambda container. Cold containers
# rebuild; warm containers serve the cache for `_MATERIALS_TTL_S`.
#
# TTL is intentionally short (60 s) so backoffice edits propagate fast
# enough that no one waits more than a minute for a new material to
# appear on tablets. Bump higher if material edits are infrequent.
# ─────────────────────────────────────────────────────────────────────
_MATERIALS_TTL_S: float = 60.0
# Bump this string whenever the cached payload shape or backing query
# changes — forces a fresh fetch on warm containers that loaded the
# previous version's code, so a stale Lambda warm pool can't keep
# returning a broken structure after a hotfix deploy.
_MATERIALS_SCHEMA_VERSION: str = '2026-05-12.b'
_materials_cache: Dict[str, Any] = {
    'expires_at': 0.0,
    'payload': None,
    'schema': '',
}


def _build_materials_list(db_session) -> List[Dict[str, Any]]:
    """Single SELECT over the materials table — column-only (no ORM
    hydration of unused fields, no `joinedload`). The previous
    `query(Material).options(joinedload(...))` loaded every column on
    `materials`, `material_categories`, and `materials` (self-join) just
    to serialise ~10 fields per row. We now select exactly the columns
    we serialise, in one query."""
    # NOTE: `materials.main_material_id` FKs into `main_materials` (a
    # separate table — see Material model line 89), NOT a self-join.
    # The previous version of this query self-joined `materials mm`
    # which (a) returned wrong data when materials.name_local existed
    # and (b) 500'd with "column mm.name_local does not exist" on DBs
    # where the Material model doesn't define name_local (it doesn't —
    # only `MainMaterial` does). Fixed by joining the right table.
    rows = db_session.execute(text(
        "SELECT m.id, m.name_en, m.name_th, m.category_id, m.main_material_id, "
        "       m.unit_name_th, m.unit_name_en, m.unit_weight, "
        "       c.id AS cat_id, c.name_en AS cat_en, c.name_th AS cat_th, c.code AS cat_code, "
        "       mm.id AS mm_id, mm.name_en AS mm_en, mm.name_th AS mm_th, "
        "       mm.name_local AS mm_local, mm.code AS mm_code "
        "FROM materials m "
        "LEFT JOIN material_categories c ON c.id = m.category_id "
        "LEFT JOIN main_materials mm ON mm.id = m.main_material_id "
        "WHERE m.is_active = TRUE AND m.deleted_date IS NULL"
    )).fetchall()

    materials_list: List[Dict[str, Any]] = []
    for r in rows:
        item: Dict[str, Any] = {
            'material_id': r[0],
            'name_en': r[1] or '',
            'name_th': r[2] or '',
            'category_id': r[3] or 0,
            'main_material_id': r[4] or 0,
            'unit_name_th': r[5] or 'กิโลกรัม',
            'unit_name_en': r[6] or 'Kilogram',
            'unit_weight': float(r[7]) if r[7] is not None else 1.0,
        }
        if r[8] is not None:
            item['category'] = {
                'id': r[8],
                'name_en': r[9] or '',
                'name_th': r[10] or '',
                'code': r[11] or '',
            }
        else:
            item['category'] = None
        if r[12] is not None:
            item['main_material'] = {
                'id': r[12],
                'name_en': r[13] or '',
                'name_th': r[14] or '',
                'name_local': r[15] or '',
                'code': r[16] or '',
            }
        else:
            item['main_material'] = None
        materials_list.append(item)
    return materials_list


def _get_cached_materials(db_session) -> List[Dict[str, Any]]:
    """Return the cached serialised materials list, rebuilding on miss.
    Safe to call concurrently — the worst case is two cold rebuilds in
    a race, which is cheaper than a lock.

    Includes a schema-version guard so a warm container that loaded an
    older version of this module before a hotfix deploy doesn't keep
    serving a stale payload shape.
    """
    now = _time_mod.time()
    cached = _materials_cache.get('payload')
    same_schema = _materials_cache.get('schema') == _MATERIALS_SCHEMA_VERSION
    if (
        cached is not None
        and same_schema
        and _materials_cache.get('expires_at', 0) > now
    ):
        return cached
    payload = _build_materials_list(db_session)
    _materials_cache['payload'] = payload
    _materials_cache['expires_at'] = now + _MATERIALS_TTL_S
    _materials_cache['schema'] = _MATERIALS_SCHEMA_VERSION
    return payload


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
        
        # Global materials list. Cached at module level in the warm Lambda
        # container so subsequent /my-memberships calls (across all
        # tablets) skip both the DB query AND the JSON serialisation.
        # The cache rebuild itself is also faster than before — column-
        # only SELECT instead of ORM hydration with joinedload.
        materials_list = _get_cached_materials(db_session)
        
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


def _run_log_cleanup(db_session, device_id: Optional[int] = None) -> None:
    """Split-retention cleanup for IoT device logs.

    Triggered by the hour-rollover branch in `handle_iot_device_sync`
    (was day-rollover before 2026-05-12 — see commit log for the
    cadence change rationale). Now scoped per-device so chatty fleets
    don't trample the same global DELETE on every cycle, and so each
    device gets its own guaranteed-hourly prune (the user's explicit
    requirement — "ทุก 1 hour สำหรับแต่ละ device").

    When ``device_id`` is given, every DELETE is gated on
    ``device_id = :device_id``. That keeps the touched-row set small
    and indexed, and avoids cross-device lock contention between
    near-simultaneous /sync handlers.

    When ``device_id`` is None the function operates server-wide. The
    paired global mop-up (`_run_global_log_sweep`) calls it that way
    to catch orphan rows from devices that have stopped syncing.

    Retention windows:

      * `iot_device_events` general rows           → **1 hour**
            /sync-driven action trail (nav, click, error,
            command_executed, stage.transition, ...). ~50/min/device,
            short-term debugging only.
      * `iot_device_events` WHERE event_type = 'state.snapshot' → **7 days**
            15-min periodic checkpoints emitted by StateSnapshotService;
            backs the backoffice timeline plot.
      * `iot_device_health_history`                → **7 days**
            5-min health-aggregate buckets for time-series plots.
      * `iot_device_commands` (terminal)           → **1 hour**
            `succeeded`/`failed`/`expired` rows. Pending/delivered cmds
            are NEVER pruned (still in flight).
      * `iot_debug_logs`                            → **7 days**
            Captured only when admin toggles debug-log mode.

    Idempotent: once the boundary rows are cleared for the current
    hour-for-that-device, subsequent runs in the same hour are no-ops
    (predicates already empty).
    """
    from sqlalchemy import text as _t

    where_dev = "AND device_id = :device_id " if device_id is not None else ""
    params = {'device_id': device_id} if device_id is not None else {}

    # General events — 1-hour retention. Bulk of the table by volume.
    db_session.execute(_t(
        "DELETE FROM iot_device_events "
        "WHERE occurred_at < NOW() - INTERVAL '1 hour' "
        "  AND event_type != 'state.snapshot' "
        + where_dev
    ), params)
    # State snapshots — 7-day retention. Drives the timeline plot.
    db_session.execute(_t(
        "DELETE FROM iot_device_events "
        "WHERE occurred_at < NOW() - INTERVAL '7 days' "
        "  AND event_type = 'state.snapshot' "
        + where_dev
    ), params)
    # Health-history buckets — 7-day retention.
    db_session.execute(_t(
        "DELETE FROM iot_device_health_history "
        "WHERE bucket_start < NOW() - INTERVAL '7 days' "
        + where_dev
    ), params)
    # Terminal commands — 1-hour retention. In-flight cmds untouched.
    db_session.execute(_t(
        "DELETE FROM iot_device_commands "
        "WHERE issued_at < NOW() - INTERVAL '1 hour' "
        "  AND status IN ('succeeded', 'failed', 'expired') "
        + where_dev
    ), params)
    # Debug logs — 7-day retention.
    db_session.execute(_t(
        "DELETE FROM iot_debug_logs "
        "WHERE received_at < NOW() - INTERVAL '7 days' "
        + where_dev
    ), params)
    # Don't commit here — the caller is responsible for transaction
    # management. When invoked from /sync, the surrounding SAVEPOINT
    # owns commit/rollback semantics. A commit() here would either
    # double-commit (no-op) or, worse, release a SAVEPOINT it
    # doesn't own and break the caller's recovery path.


def _run_global_log_sweep(db_session) -> bool:
    """Orphan-row mop-up: cleans across all devices, gated to once-per-UTC-hour.

    Why this exists: the per-device cleanup is triggered by THAT device's
    /sync hour-rollover. A device that stops syncing forever (lost, factory
    reset, disposed) keeps its sub-hour-old rows in the table indefinitely
    because nothing on its row triggers the prune. This sweep catches those.

    Coordination: we use ``pg_try_advisory_xact_lock(<hour-key>)`` — a
    transactional advisory lock keyed on the current UTC hour. Whichever
    Lambda invocation grabs the lock first runs the sweep; everyone else
    in the same UTC hour gets ``False`` back and skips. Lock is released
    automatically when the transaction commits/rolls back, so no leak
    risk.

    Returns True iff this caller ran the sweep.
    """
    from sqlalchemy import text as _t
    from datetime import datetime as _dt, timezone as _tz

    now_utc = _dt.now(_tz.utc)
    # Stable per-hour lock key. Postgres advisory locks take a bigint, so
    # we pack year/month/day/hour into a deterministic value with plenty
    # of headroom (≤ 8 digits + 2 + 2 + 2 = 14 digits, well under
    # bigint's 19).
    hour_key = (
        now_utc.year * 1_000_000
        + now_utc.month * 10_000
        + now_utc.day * 100
        + now_utc.hour
    )
    got_lock = db_session.execute(
        _t("SELECT pg_try_advisory_xact_lock(:k)"),
        {'k': hour_key},
    ).scalar()
    if not got_lock:
        return False
    _run_log_cleanup(db_session, device_id=None)
    return True


# Backwards-compat alias. Older callers (and any stale Lambda layers)
# referenced `_run_daily_log_cleanup`. Keep the name resolvable so a
# deploy with mixed-version artifacts doesn't 500.
_run_daily_log_cleanup = _run_log_cleanup


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
    #
    # CRITICAL: wrap in SAVEPOINT, NOT just try/except. Plain
    # try/except catches the Python exception but leaves the
    # PostgreSQL transaction in "aborted" state — every subsequent
    # statement in the same /sync handler then fails with
    # `InFailedSqlTransaction`. That was the smoking gun for the
    # "ทำอย่างอื่นได้หมด แต่ /sync ไม่ทำงาน" report: GPS UPDATE
    # quietly failed (e.g. missing column from an old hw schema)
    # → transaction poisoned → the next events INSERT 500'd →
    # /sync returned 500 forever even though all the surrounding
    # endpoints worked.
    _lat = hb_raw.get('lat')
    _lng = hb_raw.get('lng')
    if isinstance(_lat, (int, float)) and isinstance(_lng, (int, float)):
        _acc = hb_raw.get('acc')
        try:
            with db_session.begin_nested():
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

    # ── 1c. MAC-pairing integrity check ────────────────────────────────
    # Cross-check that the tablet currently syncing IS still bound to the
    # hardware row this iot_device was paired to. Defends against:
    #   * Admin unpaired hardware_A and re-paired hardware_B with the
    #     same iot_device_id, but tablet A still holds the old JWT.
    #   * A leaked JWT being replayed from a different physical device.
    # On mismatch we queue a `force_logout {unpair:true}` device-command,
    # which the same /sync response delivers (the claim step below picks
    # it up from iot_device_commands). The tablet's hijack agent runs
    # `DeviceResetService.resetToFactoryDefaults` + flips setupComplete
    # back to false → it drops to /device-setup and waits for a fresh
    # admin pair.
    # SAVEPOINT-wrapped: any SELECT/INSERT failure here (e.g.
    # iot_device_commands schema drift, payload JSONB syntax errors)
    # must NOT poison the outer transaction.
    try:
        with db_session.begin_nested():
            _tablet_mac = hb_raw.get('mac') if isinstance(hb_raw, dict) else None
            if isinstance(_tablet_mac, str) and _tablet_mac.strip():
                _row = db_session.execute(text(
                    "SELECT h.mac_address "
                    "FROM iot_devices d "
                    "LEFT JOIN iot_hardwares h ON h.id = d.hardware_id "
                    "WHERE d.id = :device_id"
                ), {'device_id': device_id}).fetchone()
                # Only enforce when the device IS paired to a hardware row.
                # Devices with hardware_id IS NULL are legacy / manual-login
                # cases — we don't want to lock them out by guessing.
                _expected_mac = _row[0] if _row else None
                if isinstance(_expected_mac, str) and _expected_mac.strip():
                    if _expected_mac.strip().lower() != _tablet_mac.strip().lower():
                        # Look for an already-queued unpair so we don't pile
                        # up dozens of force_logouts on every cycle while the
                        # tablet is on its way out.
                        _pending = db_session.execute(text(
                            "SELECT 1 FROM iot_device_commands "
                            "WHERE device_id = :device_id "
                            "  AND command_type = 'force_logout' "
                            "  AND status IN ('pending', 'delivered') "
                            "  AND payload @> '{\"unpair\": true}'::jsonb "
                            "LIMIT 1"
                        ), {'device_id': device_id}).fetchone()
                        if not _pending:
                            db_session.execute(text(
                                "INSERT INTO iot_device_commands "
                                "(device_id, command_type, payload, status, issued_by) "
                                "VALUES (:device_id, 'force_logout', "
                                "        CAST(:pl AS JSONB), 'pending', NULL)"
                            ), {
                                'device_id': device_id,
                                'pl': '{"unpair": true, "reason": "mac_mismatch"}',
                            })
                            _iot_logger.warning(
                                "[/sync] MAC mismatch device_id=%s expected=%s got=%s "
                                "— queued force_logout {unpair:true}",
                                device_id,
                                _expected_mac,
                                _tablet_mac,
                            )
    except Exception as _e:
        # Integrity check failure must NOT take down the /sync path —
        # better to keep heartbeats flowing and log the anomaly.
        _iot_logger.warning("[/sync] MAC integrity check skipped: %s", _e)

    # ── 1a. Hour-rollover cleanup ──────────────────────────────────────
    # Two-stage strategy (rationale: see `_run_log_cleanup` /
    # `_run_global_log_sweep` docstrings):
    #
    #   Stage A — PER-DEVICE prune
    #     Runs whenever THIS device's previous /sync was in an earlier
    #     UTC hour. Scoped to `device_id = :device_id` so the touched
    #     row set is tiny, indexed, and never contends with another
    #     concurrent /sync. This is the guaranteed-hourly cleanup per
    #     device — every device that's syncing gets its own rows
    #     pruned at least once per UTC hour.
    #
    #   Stage B — GLOBAL orphan sweep
    #     `_run_global_log_sweep` uses a transactional advisory lock
    #     keyed on the current UTC hour so AT MOST one caller
    #     server-wide actually executes the full-table prune per hour.
    #     This catches old rows from devices that have stopped syncing
    #     entirely (lost / disposed / reset tablets) — without it
    #     those rows would orphan forever.
    #
    # Both stages are best-effort: failures are swallowed because the
    # heartbeat itself is more important than disk hygiene.
    try:
        if _prev_last_seen is not None:
            from datetime import datetime as _dt, timezone as _tz
            now_utc = _dt.now(_tz.utc)
            prev_utc = _prev_last_seen.astimezone(_tz.utc) \
                if _prev_last_seen.tzinfo else _prev_last_seen.replace(tzinfo=_tz.utc)
            if (now_utc.year, now_utc.month, now_utc.day, now_utc.hour) != \
               (prev_utc.year, prev_utc.month, prev_utc.day, prev_utc.hour):
                # Stage A: this device's own rows. Wrap in SAVEPOINT
                # so a DELETE failure (e.g. on a schema that's
                # mid-migration) doesn't poison the parent
                # transaction and bring down the entire /sync
                # response with it.
                try:
                    with db_session.begin_nested():
                        _run_log_cleanup(db_session, device_id=device_id)
                    _iot_logger.info(
                        "[/sync] hourly per-device cleanup: device=%s prev=%s now=%s",
                        device_id, prev_utc, now_utc,
                    )
                except Exception as _ea:
                    _iot_logger.warning(
                        "[/sync] per-device cleanup failed (non-fatal): %s", _ea,
                    )
                # Stage B: opportunistic global mop-up. Returns False
                # for every caller after the first one this hour.
                # Same SAVEPOINT discipline.
                try:
                    with db_session.begin_nested():
                        if _run_global_log_sweep(db_session):
                            _iot_logger.info(
                                "[/sync] global orphan sweep ran (device=%s won the hour lock)",
                                device_id,
                            )
                except Exception as _e2:
                    _iot_logger.warning(
                        "[/sync] global log sweep error (non-fatal): %s", _e2,
                    )
    except Exception as _e:
        # Cleanup is best-effort. If it ever fails, /sync must NOT fail —
        # the heartbeat is more important than disk hygiene.
        _iot_logger.warning("[/sync] hourly log cleanup error (non-fatal): %s", _e)
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

    # Debug-log mode flag. Single comparison against NOW() — no separate
    # expiry job, admin toggle just writes the timestamp. When this is
    # `true` the tablet ships [Error]/[Warn] log lines to
    # /iot-devices/debug-logs; when false it drops its capture buffer.
    debug_log_active = False
    debug_log_until_raw = raw_after.get('debug_log_until') if isinstance(raw_after, dict) else None
    if debug_log_until_raw:
        try:
            dl_dt = _coerce_dt(debug_log_until_raw)
            if dl_dt and dl_dt > datetime.now(timezone.utc):
                debug_log_active = True
        except Exception:
            pass

    # Per-device runtime settings (login methods, photo enforcement,
    # user-manual toggle, font scale). The tablet writes the values
    # straight into the existing SharedPreferences keys so all the
    # in-app readers (LoginMethodsService, PhotoRequirementService,
    # TutorialService, fontScaleProvider) keep working unchanged.
    #
    # `null` means "no override on file" — the tablet keeps whatever
    # the operator set locally.
    #
    # IMPORTANT: wrap in a SAVEPOINT so /sync STAYS UP even when
    # migration 20260512_130000_062 hasn't been applied yet. A plain
    # try/except wouldn't be enough — a SELECT against a missing
    # column poisons the entire transaction in PostgreSQL ("current
    # transaction is aborted, commands ignored until end of
    # transaction block"). The SAVEPOINT lets us roll back JUST the
    # failed SELECT and keep the heartbeat upsert / MAC check /
    # command-claim work that already committed to this session.
    #
    # This was the smoking gun for the "ทำอย่างอื่นได้หมด login
    # user-id ได้ แต่ ไม่ sync" report: missing column made /sync
    # return 500 on every cycle while all OTHER endpoints worked
    # fine.
    device_settings = None
    try:
        with db_session.begin_nested():
            device_settings_row = db_session.execute(text(
                "SELECT device_settings FROM iot_devices WHERE id = :device_id"
            ), {'device_id': device_id}).fetchone()
            device_settings = (device_settings_row[0] if device_settings_row else None) or None
    except Exception as _e:
        # Most common cause: migration 062 not run yet. SAVEPOINT
        # automatically rolled back; the parent transaction is fine.
        _iot_logger.warning(
            "[/sync] device_settings SELECT failed (migration 062 not run?): %s",
            _e,
        )

    return {
        'cmds': cmds,
        'next_interval_s': next_interval_s,
        'server_time': datetime.now(timezone.utc).isoformat(),
        'long_poll_active': bool(server_long_poll),
        'debug_log_active': debug_log_active,
        'device_settings': device_settings,
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

    # ── Screenshot ack: flip the pre-issued File row to uploaded/failed.
    # We trust the file_id the tablet echoes back only after re-verifying
    # it was the row we created for THIS command (related_entity_id =
    # device_id + file_type = iot_screenshot + still in pending status).
    # That stops a misbehaving tablet from acking somebody else's file.
    if command_type == 'capture_screenshot' and isinstance(result_payload, dict):
        try:
            file_id_raw = result_payload.get('file_id')
            file_id = int(file_id_raw) if file_id_raw is not None else None
        except Exception:
            file_id = None
        if file_id:
            if status == 'succeeded':
                size_raw = result_payload.get('file_size')
                file_size = None
                if isinstance(size_raw, (int, float)) and size_raw > 0:
                    file_size = int(size_raw)
                db_session.execute(text(
                    "UPDATE files SET "
                    "  status = 'uploaded', "
                    "  upload_completed_at = EXTRACT(EPOCH FROM NOW())::BIGINT, "
                    "  file_size = COALESCE(:file_size, file_size), "
                    "  updated_date = NOW() "
                    "WHERE id = :file_id "
                    "  AND file_type = 'iot_screenshot' "
                    "  AND related_entity_type = 'iot_device' "
                    "  AND related_entity_id = :device_id "
                    "  AND status = 'pending'"
                ), {
                    'file_id': file_id,
                    'device_id': device_id,
                    'file_size': file_size,
                })
            else:
                err = result_payload.get('error') or 'tablet reported failure'
                db_session.execute(text(
                    "UPDATE files SET "
                    "  status = 'failed', "
                    "  processing_error = :err, "
                    "  updated_date = NOW() "
                    "WHERE id = :file_id "
                    "  AND file_type = 'iot_screenshot' "
                    "  AND related_entity_type = 'iot_device' "
                    "  AND related_entity_id = :device_id "
                    "  AND status = 'pending'"
                ), {
                    'file_id': file_id,
                    'device_id': device_id,
                    'err': str(err)[:500],
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
    
    # Check organization match between device and user (if user is present).
    # Column-only SELECT — we only need `organization_id`, not the full
    # IoTDevice ORM hydration. This check runs on every authenticated
    # /api/iot-devices/* call (every sync, every record post, every
    # membership fetch), so the trim is worth it.
    if current_user and current_user.get('user_id'):
        device_id = current_device.get('device_id')
        row = db_session.query(IoTDevice.organization_id).filter(
            IoTDevice.id == device_id,
            IoTDevice.is_active == True,
        ).first()

        if not row:
            raise NotFoundException('Device not found')

        user_organization_id = current_user.get('organization_id')
        device_organization_id = row[0]

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

        # ── Debug-log ingest. Tablet POSTs captured [Error]/[Warn] lines
        # here while admin has the device's debug-log mode active. Server
        # double-checks the mode flag and drops the batch if mode is off.
        if path == '/api/iot-devices/debug-logs':
            if method != 'POST':
                raise APIException('Method not allowed', status_code=405, error_code='INVALID_METHOD')
            from GEPPPlatform.services.admin.admin_service import AdminService
            return AdminService(db_session).ingest_iot_debug_logs(
                current_device or {}, data or {}
            )

        if path == '/api/iot-devices/my-memberships':
            # Use UserService for membership-based location lookup
            user_service = UserService(db_session)
            return handle_get_locations_by_membership(user_service, query_params, current_user, db_session)
        if path == '/api/iot-devices/records':
            request_body = data or {}
            data = request_body.get('data')
            if not data or not isinstance(data, dict):
                raise ValidationException('Data is required')
            if not current_user or not current_user.get('user_id'):
                raise UnauthorizedException('Valid user_token is required for record submission')
            if not current_user.get('organization_id'):
                raise UnauthorizedException('User organization is required for record submission')

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
            user_id = data.get('user_id')

            if not user_id:
                raise ValidationException('user_id is required')

            # Column-only SELECT instead of full ORM hydration. The
            # previous `query(UserLocation).filter_by(...)` materialised
            # all ~30 columns + property setup on a row we only use 4
            # fields from. Returns a lightweight tuple — same query plan
            # (PK lookup on user_locations) but ~10× less Python work.
            row = db_session.query(
                UserLocation.id,
                UserLocation.organization_id,
                UserLocation.email,
                UserLocation.display_name,
            ).filter(
                UserLocation.id == user_id,
                UserLocation.is_active == True,
            ).first()

            if not row:
                raise UnauthorizedException('Invalid user_id')

            u_id, u_org_id, u_email, u_display = row
            tokens = auth_handler.generate_jwt_tokens(u_id, u_org_id, u_email)

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 60 minutes in seconds
                'user': {
                    'id': u_id,
                    'email': u_email or '',
                    'displayName': u_display or '',
                    'organization_id': u_org_id or 0,
                },
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
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )
