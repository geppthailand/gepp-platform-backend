"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

from typing import Dict, Any, Optional, Tuple
import csv
import os
import json
import ast
import logging
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import boto3

from .reports_service import ReportsService

logger = logging.getLogger(__name__)
from .ghg_equivalents import kg_co2_to_trees, kg_co2_to_forest_rai
from ..transactions.presigned_url_service import TransactionPresignedUrlService
from ....exceptions import APIException, ValidationException, NotFoundException
from GEPPPlatform.models.cores.references import MainMaterial, MaterialCategory
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.transactions.transactions import TransactionStatus

# ========== HELPER FUNCTIONS ==========

def resolve_rate_presentation(
    outcome_scope: bool,
    scope_touches_tank: bool,
    measured: float,
    estimate: float,
) -> Tuple[Optional[float], str, Optional[float]]:
    """Which recycling rate a scope gets to see, and what it must be called.

    Returns (rate | None, basis, toggle_estimate | None).

    The rule is one sentence: a rate is suppressed ONLY where the tank model
    actually bites. Everything else keeps a number — labelled, so nobody
    mistakes an estimate for a measurement.

      • scope never meets a tank → the pre-tank ESTIMATE, exactly the number
        every report showed before collection points existed. This covers every
        pre-scale organization in every view, and the filtered corners of a
        scale site its tanks never touch. (measured == estimate here anyway:
        with nothing delivered, the supersede is a no-op.)
      • org-wide scope of a tank site → the MEASURED rate ('outcome'), plus the
        estimate for a view-only toggle — people who watched the old number for
        years deserve to see both and understand the drop, without a switch
        that changes the official figure.
      • narrowed scope that touches a tank → None ('unavailable'). One tenant's
        deliveries measured against a shared room's outcomes is a wrong number,
        not a conservative one; the UI leads with separation quality and the
        kilograms still sitting in the room instead.

    Pure function — all four inputs are already computed by the overview
    handler — so the whole presentation policy is testable without a database.
    """
    if not scope_touches_tank:
        return estimate, 'estimate', None
    if outcome_scope:
        return measured, 'outcome', estimate
    return None, 'unavailable', None


def _validate_organization_id(current_user: Dict[str, Any]) -> int:
    """Validate and extract organization_id from current_user"""
    organization_id = current_user.get('organization_id')
    if not organization_id:
        raise ValidationException("Organization ID is required")
    return organization_id


def _build_filters_from_query_params(query_params: Dict[str, Any], timezone_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Build filters dictionary from query parameters
    Supports comma-separated values for material_id and origin_id
    Example: ?material_id=1,2,3&origin_id=10,20
    
    Date handling:
    - If the incoming value includes a time (ISO with or without timezone), respect it.
    - If only a date is provided, interpret it in the provided timezone (timezone_name or Asia/Bangkok),
      setting date_from to start-of-day and date_to to end-of-day in that timezone.
    - All stored filter values are normalized to UTC ISO strings.
    """
    filters = {}
    # Resolve timezone for date-only inputs
    try:
        tz = ZoneInfo(timezone_name or 'Asia/Bangkok')
    except Exception:
        tz = timezone.utc
    
    # Handle material_id (comma-separated)
    if query_params.get('material_id'):
        material_ids_str = query_params['material_id']
        if ',' in material_ids_str:
            # Multiple IDs
            filters['material_ids'] = [int(mid.strip()) for mid in material_ids_str.split(',') if mid.strip()]
        else:
            # Single ID
            filters['material_ids'] = [int(material_ids_str)]
    
    # Handle origin_id (comma-separated, or composite "origin_id|tag_id|tenant_id", or multiple composites "2507||1,2507|46|")
    if query_params.get('origin_id'):
        origin_ids_str = query_params['origin_id'].strip()
        if ',' in origin_ids_str and '|' in origin_ids_str:
            # Multiple composites: "2507||1,2507|46|" -> [(2507, None, 1), (2507, 46, None)]
            try:
                combos = []
                for segment in origin_ids_str.split(','):
                    segment = segment.strip()
                    if not segment:
                        continue
                    if '|' in segment:
                        parts = segment.split('|')
                        oid = int(parts[0]) if parts[0] else None
                        tag_id = int(parts[1]) if len(parts) > 1 and parts[1] and str(parts[1]).strip() else None
                        tenant_id = int(parts[2]) if len(parts) > 2 and parts[2] and str(parts[2]).strip() else None
                        if oid is not None:
                            combos.append((oid, tag_id, tenant_id))
                    else:
                        oid = int(segment)
                        combos.append((oid, None, None))
                if combos:
                    filters['origin_combos'] = combos
                    filters.pop('origin_ids', None)
                    filters.pop('location_tag_id', None)
                    filters.pop('tenant_id', None)
            except (ValueError, TypeError):
                pass
        elif '|' in origin_ids_str:
            # Single composite: origin_id|tag_id|tenant_id (e.g. "2507|46|1" or "3878||")
            try:
                parts = origin_ids_str.split('|')
                oid = int(parts[0]) if parts[0] else None
                tag_id = int(parts[1]) if len(parts) > 1 and parts[1] and str(parts[1]).strip() else None
                tenant_id = int(parts[2]) if len(parts) > 2 and parts[2] and str(parts[2]).strip() else None
                if oid is not None:
                    filters['origin_ids'] = [oid]
                if tag_id is not None:
                    filters['location_tag_id'] = tag_id
                else:
                    filters.pop('location_tag_id', None)
                if tenant_id is not None:
                    filters['tenant_id'] = tenant_id
                else:
                    filters.pop('tenant_id', None)
            except (ValueError, TypeError):
                pass
        elif ',' in origin_ids_str:
            # Multiple origin IDs (no composite)
            filters['origin_ids'] = [int(oid.strip()) for oid in origin_ids_str.split(',') if oid.strip()]
        else:
            try:
                filters['origin_ids'] = [int(origin_ids_str)]
            except (ValueError, TypeError):
                pass
    
    # Handle new multi-select location filters: location_ids, tag_ids, tenant_ids (comma-separated)
    location_ids_raw = query_params.get('location_ids')
    if location_ids_raw:
        filters['location_ids'] = [int(x) for x in location_ids_raw.split(',') if x.strip()]
    tag_ids_raw = query_params.get('tag_ids')
    if tag_ids_raw:
        filters['filter_tag_ids'] = [int(x) for x in tag_ids_raw.split(',') if x.strip()]
    tenant_ids_raw = query_params.get('tenant_ids')
    if tenant_ids_raw:
        filters['filter_tenant_ids'] = [int(x) for x in tenant_ids_raw.split(',') if x.strip()]

    # Destination filter ("สถานที่รับขยะ"): filter by per-record destination_id.
    # Combines with the origin filter as AND (transaction origin ∈ origins AND
    # record destination ∈ destinations). Applies across every report tab.
    destination_ids_raw = query_params.get('destination_ids')
    if destination_ids_raw:
        filters['destination_ids'] = [int(x) for x in destination_ids_raw.split(',') if x.strip()]

    # Handle date filters (preserve provided times; apply local day bounds for date-only)
    date_from_input = query_params.get('date_from') or query_params.get('datefrom')
    if date_from_input:
        date_from_str = date_from_input
        try:
            if 'T' in date_from_str or ' ' in date_from_str:
                # Has time component: parse full ISO, respect provided tz if any; if naive, assume tz
                try:
                    dt = datetime.fromisoformat(date_from_str.replace('Z', '+00:00'))
                except Exception:
                    dt = datetime.fromisoformat(date_from_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                filters['date_from'] = dt.astimezone(timezone.utc).isoformat()
            else:
                # Date only: interpret as start of day in specified timezone
                y, m, d = map(int, date_from_str.split('-'))
                local_dt = datetime(y, m, d, 0, 0, 0, 0, tzinfo=tz)
                filters['date_from'] = local_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            # Fallback to original value if parsing fails
            filters['date_from'] = date_from_str

    date_to_input = query_params.get('date_to') or query_params.get('dateto')
    if date_to_input:
        date_to_str = date_to_input
        try:
            if 'T' in date_to_str or ' ' in date_to_str:
                # Has time component: parse full ISO, respect provided tz if any; if naive, assume tz
                try:
                    dt = datetime.fromisoformat(date_to_str.replace('Z', '+00:00'))
                except Exception:
                    dt = datetime.fromisoformat(date_to_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                filters['date_to'] = dt.astimezone(timezone.utc).isoformat()
            else:
                # Date only: interpret as end of day in specified timezone
                y, m, d = map(int, date_to_str.split('-'))
                local_dt = datetime(y, m, d, 23, 59, 59, 999999, tzinfo=tz)
                filters['date_to'] = local_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            # Fallback to original value if parsing fails
            filters['date_to'] = date_to_str

    # Default YTD if no explicit dates provided (first day of current year -> end of today)
    if not filters.get('date_from') and not filters.get('date_to'):
        now_utc = datetime.now(timezone.utc)
        start_of_year_utc = datetime(now_utc.year, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
        end_of_today_utc = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)
        filters['date_from'] = start_of_year_utc.isoformat()
        filters['date_to'] = end_of_today_utc.isoformat()

    # If only date_from is provided, set date_to to end of today as a default
    try:
        dt_from = _parse_datetime(filters.get('date_from')) if filters.get('date_from') else None
        dt_to = _parse_datetime(filters.get('date_to')) if filters.get('date_to') else None
        if dt_from and not dt_to:
            now_utc = datetime.now(timezone.utc)
            filters['date_to'] = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    except Exception:
        pass

    # Report presentation settings (not data filters): only whitelisted values pass.
    if query_params.get('report_mode') in REPORT_MODES:
        filters['report_mode'] = query_params['report_mode']
    if query_params.get('overview_chart') in ('yearly', 'monthly', 'daily'):
        filters['overview_chart'] = query_params['overview_chart']
    if query_params.get('compare_mode') in ('yearly', 'monthly'):
        filters['compare_mode'] = query_params['compare_mode']
    if is_overview_breakdown(query_params.get('overview_breakdown')):
        filters['overview_breakdown'] = query_params['overview_breakdown']

    return filters


def _parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse datetime string with fallback for timezone handling"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        try:
            if isinstance(date_str, str):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            pass
    return None


def _calculate_weight(record: Dict[str, Any], material: Dict[str, Any]) -> float:
    """Calculate weight from quantity and unit_weight; fall back to origin_weight_kg when derived weight is 0 (e.g. tag/tenant records)."""
    quantity = float(record.get('origin_quantity') or 0)
    material_dict = material or {}
    unit_weight = float(material_dict.get('unit_weight') or 0)
    weight = quantity * unit_weight
    if weight <= 0:
        origin_kg = float(record.get('origin_weight_kg') or 0)
        if origin_kg > 0:
            return origin_kg
    return weight


_GENERAL_WASTE_CAT_ID = 4  # Material category ID for General Waste
_WASTE_TO_ENERGY_CAT_ID = 9  # Material category ID for Waste To Energy

# Report modes: the same report regrouped by location (default), tag (event / tagged
# area) or tenant. Rows from get_overview_data carry location_tag_id at 20, tenant_id at 21.
REPORT_MODES = ('location', 'tag', 'tenant')
from ..users.user_preferences_service import is_overview_breakdown  # noqa: E402
_GROUP_ROW_INDEX = {'tag': 20, 'tenant': 21}


def _report_mode(filters: Optional[Dict[str, Any]]) -> str:
    mode = (filters or {}).get('report_mode') or 'location'
    return mode if mode in REPORT_MODES else 'location'


def _row_group_id(row, mode: str) -> Optional[int]:
    idx = _GROUP_ROW_INDEX.get(mode)
    if idx is None or len(row) <= idx:
        return None
    return row[idx]


def _comparison_out_of_range(filters: Dict[str, Any], tz_name: str) -> Dict[str, Any]:
    """Why the selected range can't be compared, plus ranges that can, for the PDF page.

    Suggestions stay inside what the user picked: yearly → the selected days of the end
    date's year; monthly → the selected days of the end date's month. `yearly_ok` says
    whether the same range would work in the other mode, so the page can offer the switch.
    """
    from .report_insights import range_label
    try:
        tz = ZoneInfo(tz_name or 'Asia/Bangkok')
    except Exception:
        tz = ZoneInfo('Asia/Bangkok')
    mode = filters.get('compare_mode') if filters.get('compare_mode') in ('yearly', 'monthly') else 'yearly'
    out: Dict[str, Any] = {'compare_mode': mode}
    f_dt = _parse_datetime(filters.get('date_from')) if filters.get('date_from') else None
    t_dt = _parse_datetime(filters.get('date_to')) if filters.get('date_to') else None
    if not f_dt or not t_dt:
        return out
    f = (f_dt if f_dt.tzinfo else f_dt.replace(tzinfo=timezone.utc)).astimezone(tz).date()
    t = (t_dt if t_dt.tzinfo else t_dt.replace(tzinfo=timezone.utc)).astimezone(tz).date()
    month_from = max(f, t.replace(day=1))
    year_from = max(f, t.replace(month=1, day=1))
    s_from = month_from if mode == 'monthly' else year_from
    out.update({
        'from': f.isoformat(), 'to': t.isoformat(),
        'selected_th': range_label(f, t, 'th'), 'selected_en': range_label(f, t, 'en'),
        'suggest_th': range_label(s_from, t, 'th'), 'suggest_en': range_label(s_from, t, 'en'),
        'suggest_month_th': range_label(month_from, t, 'th'), 'suggest_month_en': range_label(month_from, t, 'en'),
        'yearly_ok': f.year == t.year and (t - f).days <= 365,
    })
    return out


def _fetch_group_names(db_session, mode: str, ids: set) -> Dict[int, str]:
    """Tag or tenant names by id (inactive/deleted ones still resolve, so old data keeps a name).

    Ids missing from the result don't point at a tag/tenant at all — some older transactions
    carry a user_locations id in location_tag_id — so callers treat them as "no tag"."""
    if not ids or mode not in _GROUP_ROW_INDEX:
        return {}
    try:
        from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
        model = UserLocationTag if mode == 'tag' else UserTenant
        rows = db_session.query(model.id, model.name).filter(model.id.in_(list(ids))).all()
        prefix = 'Tag' if mode == 'tag' else 'Tenant'
        return {rid: (name or f"{prefix} {rid}") for rid, name in rows}
    except Exception as e:  # names are decoration; the numbers must still render
        logger.warning("[reports] group name lookup failed: %s", e)
        return {}


def _get_general_waste_mm_id(db) -> Optional[int]:
    """Look up the main_material_id for 'General Waste' (code=GENERAL_WASTE).
    Returns None if the lookup fails."""
    try:
        gw_row = db.query(MainMaterial.id).filter(
            MainMaterial.code == 'GENERAL_WASTE'
        ).first()
        if gw_row:
            return gw_row[0]
    except Exception:
        pass
    return None


def _split_waste_to_energy(material_map: Dict[str, float], cat_mm_map: Dict[Tuple[int, int], float],
                           general_waste_mm_id: Optional[int], category_names: Dict[int, str]) -> Dict[str, float]:
    """Normalize 'Waste to Energy' category name in material_map.

    Ensures the Waste To Energy category (id=9) uses a consistent display name.
    Materials under General Waste (cat_id=4) are kept as-is to match legacy report behavior.

    Args:
        material_map: {category_name: weight} dict (mutated in place and returned)
        cat_mm_map: {(category_id, main_material_id): weight} tracking dict
        general_waste_mm_id: the main_material_id for GENERAL_WASTE (unused, kept for API compat)
        category_names: {category_id: name} mapping

    Returns:
        The updated material_map.
    """
    # Normalize Waste To Energy category name from DB to consistent display name
    wte_db_name = category_names.get(_WASTE_TO_ENERGY_CAT_ID, 'Waste To Energy')
    if wte_db_name in material_map and wte_db_name != 'Waste To Energy':
        material_map['Waste To Energy'] = material_map.pop(wte_db_name)

    return material_map


def _extract_destination_id(notes: str) -> Optional[int]:
    """Extract destination ID from notes field (format: 'Destination: {id}')"""
    if not notes or 'Destination:' not in notes:
        return None
    try:
        dest_part = notes.split('Destination:')[1].strip()
        return int(dest_part.split()[0])
    except (IndexError, ValueError):
        return None


def _fetch_main_material_names(db_session, material_ids: set) -> Dict[int, str]:
    """Fetch main material names from database"""
    if not material_ids:
        return {}
    try:
        rows = db_session.query(
            MainMaterial.id, MainMaterial.name_en, MainMaterial.name_th
        ).filter(MainMaterial.id.in_(material_ids)).all()

        return {
            mm_id: (name_en or name_th or f"Material {mm_id}")
            for mm_id, name_en, name_th in rows
        }
    except Exception:
        return {}


def _fetch_main_material_names_bilingual(db_session, material_ids: set) -> Dict[int, Dict[str, str]]:
    """Fetch main material names (both TH and EN) from database"""
    if not material_ids:
        return {}
    try:
        rows = db_session.query(
            MainMaterial.id, MainMaterial.name_en, MainMaterial.name_th
        ).filter(MainMaterial.id.in_(material_ids)).all()
        return {
            mm_id: {"name_en": name_en or f"Material {mm_id}", "name_th": name_th or name_en or f"Material {mm_id}"}
            for mm_id, name_en, name_th in rows
        }
    except Exception:
        return {}


def _fetch_destination_names(db_session, destination_ids: set) -> Dict[int, str]:
    """Fetch destination location names from database"""
    if not destination_ids:
        return {}
    try:
        destinations = db_session.query(
            UserLocation.id,
            UserLocation.display_name,
            UserLocation.name_en,
            UserLocation.name_th
        ).filter(UserLocation.id.in_(destination_ids)).all()

        result = {
            dest_id: (display_name or name_en or name_th or f"Location {dest_id}")
            for dest_id, display_name, name_en, name_th in destinations
        }

        # Log for debugging
        print(f"[DEBUG] _fetch_destination_names: Fetched {len(result)} names for {len(destination_ids)} IDs")
        if len(result) != len(destination_ids):
            missing = destination_ids - set(result.keys())
            print(f"[DEBUG] Missing location names for IDs: {missing}")

        return result
    except Exception as e:
        print(f"[ERROR] _fetch_destination_names failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def _fetch_category_names(db_session, category_ids: set) -> Dict[int, str]:
    """Fetch material category names from database"""
    if not category_ids:
        return {}
    try:
        rows = db_session.query(
            MaterialCategory.id, MaterialCategory.name_en, MaterialCategory.name_th
        ).filter(MaterialCategory.id.in_(category_ids)).all()
        return {
            cid: (name_en or name_th or f"Category {cid}")
            for cid, name_en, name_th in rows
        }
    except Exception:
        return {}


def _fetch_category_names_bilingual(db_session, category_ids: set) -> Dict[int, Dict[str, str]]:
    """Fetch material category names (both TH and EN) from database"""
    if not category_ids:
        return {}
    try:
        rows = db_session.query(
            MaterialCategory.id, MaterialCategory.name_en, MaterialCategory.name_th
        ).filter(MaterialCategory.id.in_(category_ids)).all()
        return {
            cid: {"name_en": name_en or f"Category {cid}", "name_th": name_th or name_en or f"Category {cid}"}
            for cid, name_en, name_th in rows
        }
    except Exception:
        return {}


def _check_transaction_completion(transaction_map: Dict[int, Dict]) -> Tuple[int, int, float]:
    """
    Check which transactions are fully completed
    Returns: (total_transactions, completed_transactions, complete_transfer_weight)
    """
    total_transactions = len(transaction_map)
    completed_transactions = 0
    complete_transfer = 0.0
    
    for transaction_id, data in transaction_map.items():
        all_completed = all(
            record['status'] == 'completed' 
            for record in data['records']
        )
        if all_completed:
            completed_transactions += 1
            complete_transfer += data['total_weight']
    
    return total_transactions, completed_transactions, complete_transfer


# ========== ROUTE HANDLERS ==========

def _resolve_per_capita_scope(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Headcount denominator and the origins whose waste may enter the numerator.

    Waste and people have to be paired per subtree — see `resolve_headcount_scope`. A plain
    "sum all headcounts, divide all waste" would drag in waste from branches that have no
    headcount at all, with nothing on the other side of the division to match it.

    Returns {'total': int|None, 'covered_ids': set[int]}; `total` is None when nothing in
    scope has a headcount, and the card then shows N/A instead of dividing.

    With no location filter the scope is the whole org tree. The dashboard sends
    `location_ids`, legacy callers `origin_ids`, composite selections `origin_combos`.
    """
    from ..users.user_service import resolve_headcount_scope
    from ....models.subscriptions.organizations import OrganizationSetup
    from ....models.users.user_location import UserLocation

    setup = reports_service.db.query(OrganizationSetup).filter(
        OrganizationSetup.organization_id == organization_id,
        OrganizationSetup.is_active == True,
        OrganizationSetup.deleted_date.is_(None),
    ).order_by(OrganizationSetup.created_date.desc()).first()
    root_nodes = (setup.root_nodes if setup else None) or []
    if not isinstance(root_nodes, list):
        root_nodes = [root_nodes] if root_nodes else []

    rows = reports_service.db.query(UserLocation.id, UserLocation.headcount).filter(
        UserLocation.organization_id == organization_id,
        UserLocation.is_location == True,
        UserLocation.deleted_date.is_(None),
    ).all()
    headcount_by_id = {r.id: r.headcount for r in rows}

    selected: set = set()
    for key in ('location_ids', 'origin_ids'):
        for raw in (filters or {}).get(key) or []:
            try:
                selected.add(int(raw))
            except (TypeError, ValueError):
                continue
    # Composite `origin|tag|tenant` selections replace origin_ids with origin_combos
    # (the parser pops origin_ids). Missing this reads as "no filter" and would quietly
    # divide by the whole organisation's headcount.
    for combo in (filters or {}).get('origin_combos') or []:
        try:
            selected.add(int(combo[0]))
        except (TypeError, ValueError, IndexError):
            continue

    if not selected:
        # No location filter → every root, i.e. the whole organisation.
        for node in root_nodes:
            if isinstance(node, dict):
                try:
                    selected.add(int(node.get('nodeId', 0)))
                except (TypeError, ValueError):
                    continue
        if not selected:
            selected = {rid for rid in headcount_by_id}

    return resolve_headcount_scope(root_nodes, selected, headcount_by_id)


def _handle_overview_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Handle /api/reports/overview endpoint.

    Optimized: uses get_overview_data() which selects only needed columns
    in a single SQL query with JOINs (no N+1, no full ORM loading).
    """

    # Fast path: single SQL query returning lightweight tuples
    current_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')
    result = reports_service.get_overview_data(
        organization_id=organization_id,
        filters=filters if filters else None,
        current_user_id=current_user_id,
        include_internal_rows=True,
    )
    rows = result.get('rows', [])
    internal_rows = result.get('internal_rows') or []
    collection_markers = result.get('collection_markers') or {}

    # ── Scope predicate for the OUTCOME-based rate ─────────────────────────
    # The outcome rate compares what a site GENERATED against what its
    # collection points actually SHIPPED. That comparison is only sound when
    # both halves describe the same material. Any narrowing of the generation
    # half — a request filter, or invisible member scoping — breaks it: one
    # tenant's deliveries would be measured against the whole building's
    # outcomes, and a filter on the waste room itself would show ~0 generated
    # beside every outcome in the org. So narrowing switches the page to
    # composition reporting (what was handed over, how well it was separated)
    # and reports the outcome rate as unavailable rather than as a wrong number.
    _scope_filter_keys = (
        'origin_ids', 'origin_combos', 'location_ids', 'destination_ids',
        'filter_tag_ids', 'filter_tenant_ids', 'location_tag_id', 'tenant_id',
        'material_ids',
    )
    _has_scope_filter = bool(filters) and any(
        filters.get(k) is not None for k in _scope_filter_keys
    )
    outcome_scope = (
        not _has_scope_filter
        and reports_service.visibility_is_unrestricted(current_user_id, organization_id)
    )

    # Tuple indices from query:
    # 0: origin_quantity, 1: transaction_date, 2: created_transaction_id,
    # 3: origin_id, 4: status, 5: unit_weight, 6: calc_ghg,
    # 7: material_category_id, 8: material_main_material_id, 9: material_tags,
    # 10: origin_weight_kg, 11: record_category_id, 12: record_main_material_id

    # Aggregate in single pass
    from .recycling_rate_helper import compute_recycling_rate, fetch_group_leaf_data, is_record_recyclable

    ghg_reduction = 0.0
    total_waste = 0.0
    plastic_saved = 0.0
    category_waste_map = {}
    month_totals_by_year = {}
    # kg per category per month / per day, for the chart's "by category" views
    month_cat_by_year: Dict[int, Dict[int, Dict[int, float]]] = {}
    day_cat: Dict[str, Dict[int, float]] = {}
    tx_ids = set()
    tx_approved = set()

    # Collect per-record data for 3-tier recycling rate calculation
    record_weights = []  # (weight, calc_ghg, cat_id, group_id)
    record_tx_ids = []   # parallel to record_weights: the weighing each came from
    record_months = []   # parallel to record_weights: (year, month) in Bangkok, or None
    record_days = []     # parallel to record_weights: 'YYYY-MM-DD' in Bangkok, or None
    record_groups = []   # parallel to record_weights: tag/tenant id for the report mode
    report_mode = _report_mode(filters)
    record_origins = []  # (origin_id, weight, calc_ghg, cat_id, group_id) for origin_waste_map
    all_record_ids = []  # collect record IDs for group mapping

    group_ids = set()

    for row in rows:
        origin_qty = float(row[0] or 0)
        tx_date = row[1]
        tx_id = row[2]
        origin_id = row[3]
        status = row[4]
        unit_weight = float(row[5] or 0)
        calc_ghg = float(row[6] or 0)

        # Use Material category/main_material as primary source (matches old reportUtils logic).
        # Fallback to TransactionRecord fields when Material is missing.
        cat_id = row[7] or row[11]           # material_category_id || record_category_id
        main_mat_id = row[8] or row[12]      # material_main_material_id || record_main_material_id
        record_id = row[19]                  # TransactionRecord.id

        # Track transactions
        tx_ids.add(tx_id)
        if status == TransactionStatus.approved:
            tx_approved.add(tx_id)

        # Use origin_qty * unit_weight (matches old version - no fallback)
        weight = origin_qty * unit_weight
        record_ghg = weight * calc_ghg

        total_waste += weight
        ghg_reduction += record_ghg

        # Monthly aggregation — bucket by the user's local timezone (Bangkok),
        # not UTC. Without this, a tx stored as e.g. 2025-10-31 18:00 UTC
        # (= 2025-11-01 01:00 Bangkok) lands in October here while the SQL
        # date-range filter (converted to Bangkok) includes it in November,
        # causing an Oct/Nov split on the chart.
        record_ym = None
        record_day = None
        if tx_date:
            try:
                dt = tx_date if isinstance(tx_date, datetime) else datetime.fromisoformat(str(tx_date))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_local = dt.astimezone(ZoneInfo('Asia/Bangkok'))
                y, m = dt_local.year, dt_local.month
                record_ym = (y, m)
                record_day = dt_local.strftime('%Y-%m-%d')
                if y not in month_totals_by_year:
                    month_totals_by_year[y] = {}
                month_totals_by_year[y][m] = month_totals_by_year[y].get(m, 0.0) + weight
                if cat_id is not None:
                    mc = month_cat_by_year.setdefault(y, {}).setdefault(m, {})
                    mc[cat_id] = mc.get(cat_id, 0.0) + weight
                    dc = day_cat.setdefault(record_day, {})
                    dc[cat_id] = dc.get(cat_id, 0.0) + weight
            except Exception:
                pass

        # Plastic saved (main_material_id=1 AND category_id=1)
        if main_mat_id == 1 and cat_id == 1:
            plastic_saved += weight

        # Temporarily store with record_id; group_id will be resolved below
        record_weights.append((weight, calc_ghg, cat_id, record_id))
        # Parallel to record_weights: which weighing each record came from, so
        # the collection-point markers (keyed by transaction) can be attributed
        # back to individual records.
        record_tx_ids.append(tx_id)
        record_months.append(record_ym)
        record_days.append(record_day)
        record_groups.append(_row_group_id(row, report_mode))
        if origin_id is not None:
            record_origins.append((origin_id, weight, calc_ghg, cat_id, record_id))
        all_record_ids.append(record_id)

        # Category proportions
        if cat_id is not None:
            category_waste_map[cat_id] = category_waste_map.get(cat_id, 0.0) + weight

    # Build record_id → group_id mapping from TraceabilityTransactionGroup.transaction_record_id arrays
    # This is the source of truth — does not depend on the reverse pointer (traceability_group_id column)
    from ....models.transactions.traceability_transaction_group import TraceabilityTransactionGroup
    record_to_group = {}
    if all_record_ids or internal_rows:
        groups = reports_service.db.query(
            TraceabilityTransactionGroup.id,
            TraceabilityTransactionGroup.transaction_record_id,
        ).filter(
            TraceabilityTransactionGroup.organization_id == organization_id,
            TraceabilityTransactionGroup.is_active == True,
            TraceabilityTransactionGroup.deleted_date.is_(None),
        ).all()
        for gid, rec_ids in groups:
            if rec_ids:
                for rid in rec_ids:
                    record_to_group[rid] = gid

    # Resolve group_id for each record using the mapping
    record_weights = [
        (w, ghg, cat, record_to_group.get(rid))
        for w, ghg, cat, rid in record_weights
    ]
    record_origins = [
        (oid, w, ghg, cat, record_to_group.get(rid))
        for oid, w, ghg, cat, rid in record_origins
    ]
    group_ids = {gid for _, _, _, gid in record_weights if gid is not None}

    # ── Two-scope rate assembly ────────────────────────────────────────────
    # GENERATION set (record_weights, built above from `rows`) answers "how much
    # waste did this site produce" — unchanged, and every card that reports
    # tonnage keeps reading it.
    #
    # RATE set = the generation set MINUS material handed over to a collection
    # point, PLUS that point's own weigh-outs. Those weigh-outs are the only
    # records that say what actually happened to the material: someone opened
    # the pile, sorted it, and shipped each stream to a real destination.
    # Without them a scale-run site reports its outcomes as a guess from
    # material category; with them, and without the supersede, it reports the
    # same kilograms twice.
    rate_record_weights = list(record_weights)
    # Material weighed in AT a collection point that never left it: no legs to
    # trace, so the leaf-based supersede cannot see it. Attribute the marker's
    # hopless remainder across that transaction's records by weight. Built in
    # EVERY scope: a narrowed scope does not report an outcome rate, but it must
    # still be able to say how much of its material is waiting in a sorting room.
    superseded_by_record: Dict[int, float] = {}
    marker_rows: Dict[int, list] = {}
    for _idx, _tx_id in enumerate(record_tx_ids):
        if _tx_id in collection_markers:
            marker_rows.setdefault(_tx_id, []).append(_idx)
    for _tx_id, _idxs in marker_rows.items():
        hopless = float(collection_markers[_tx_id].get('hopless_kg') or 0)
        if hopless <= 0:
            continue
        tx_total = sum(rate_record_weights[i][0] for i in _idxs)
        if tx_total <= 0:
            continue
        for i in _idxs:
            share = rate_record_weights[i][0] / tx_total
            superseded_by_record[i] = hopless * share

    if outcome_scope:
        # The weigh-outs join the rate set. Ones whose approve-time hook failed
        # have no traceability group: excluded rather than category-guessed,
        # because a groupless weigh-out would replace a real measurement with
        # exactly the guess this whole mechanism exists to remove.
        for irow in internal_rows:
            _rid = irow[19]
            _gid = record_to_group.get(_rid)
            if _gid is None:
                logger.warning(
                    "[overview] internal transfer record %s has no traceability group; "
                    "excluded from the recycling rate", _rid,
                )
                continue
            _w = float(irow[0] or 0) * float(irow[5] or 0)
            rate_record_weights.append((_w, float(irow[6] or 0), irow[7] or irow[11], _gid))
        group_ids = group_ids | {
            gid for _, _, _, gid in rate_record_weights if gid is not None
        }

    # 3-tier recycling rate calculation using traceability data
    group_leaf_data, group_completion = fetch_group_leaf_data(reports_service.db, group_ids)
    recyclable_waste, recyclable_ghg_reduction, _, traceability_fully_managed, rate_total = compute_recycling_rate(
        rate_record_weights, group_leaf_data, group_completion,
        supersede_delivered=outcome_scope,
        superseded_by_record=superseded_by_record if outcome_scope else None,
    )
    recycle_rate = ((recyclable_waste / rate_total) * 100) if rate_total > 0 else 0.0

    # Does THIS scope's material ever meet a tank? This one signal decides how
    # the rate is presented. Suppressing the rate is only honest where the tank
    # model actually bites — material handed into a shared room, so a narrowed
    # generation set can no longer be matched against outcomes. Everywhere else
    # (every pre-scale organization, and any filtered corner of a scale site the
    # tanks never touch) the pre-tank estimate is exactly as valid as it was the
    # day before this feature shipped, and hiding it there just breaks reports
    # people already rely on. Both inputs are already in hand — no extra query.
    scope_touches_tank = bool(superseded_by_record) or any(
        leaf.get('delivered')
        for leaves in group_leaf_data.values()
        for leaf in leaves
    )

    # The pre-tank number: generation set only, no supersede — byte-for-byte
    # what every report showed before collection points existed. Serves two
    # jobs: the primary rate wherever the scope never meets a tank, and the
    # "ประมาณการ" side of the org-scope toggle so the UI can flip views without
    # a second request. Same in-memory data, no extra query.
    _est_recyclable, _est_ghg, _, _, _est_total = compute_recycling_rate(
        record_weights, group_leaf_data, group_completion,
    )
    recycle_rate_estimate = ((_est_recyclable / _est_total) * 100) if _est_total > 0 else 0.0

    recycle_rate_out, recycle_rate_basis, recycle_rate_toggle = resolve_rate_presentation(
        outcome_scope, scope_touches_tank, recycle_rate, recycle_rate_estimate
    )

    # How much of THIS scope's material is sitting in a sorting room waiting for
    # an outcome. In a narrowed scope this is the only honest thing to say about
    # the missing rate, so it has to be measured even though the rate itself is
    # not reported — the supersede pass above ran with the flag OFF there, and
    # would have returned zero. Measured over the generation set alone: the
    # weigh-outs are somebody else's scope by definition.
    _, _, _gen_total, _, _gen_rate_total = compute_recycling_rate(
        record_weights, group_leaf_data, group_completion,
        supersede_delivered=True,
        superseded_by_record=superseded_by_record,
    )
    superseded_kg = round(max(0.0, _gen_total - _gen_rate_total), 2)

    # Build origin_waste_map using 3-tier recyclable logic
    origin_waste_map = {}
    for origin_id, weight, calc_ghg, cat_id, group_id in record_origins:
        recyclable_w = is_record_recyclable(weight, cat_id, group_id, group_leaf_data, group_completion)
        if recyclable_w > 0:
            origin_waste_map[origin_id] = origin_waste_map.get(origin_id, 0.0) + recyclable_w

    # Top 5 recyclable origins — fetch origin names with member filtering.
    # Tag / tenant mode ranks those groups instead (records without one are left out: the
    # list answers "which event / which tenant recycles most", and "none" is neither).
    top_origin_ids = sorted(origin_waste_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_recyclables = []
    if report_mode != 'location':
        group_names = _fetch_group_names(reports_service.db, report_mode, {g for g in record_groups if g is not None})
        group_waste_map: Dict[int, float] = {}
        for (w, _ghg, cat, gid), grp in zip(record_weights, record_groups):
            if grp is None or grp not in group_names:
                continue
            rw = is_record_recyclable(w, cat, gid, group_leaf_data, group_completion)
            if rw > 0:
                group_waste_map[grp] = group_waste_map.get(grp, 0.0) + rw
        top_groups = sorted(group_waste_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_recyclables = [
            {'origin_id': g, 'origin_name': group_names.get(g, str(g)), 'path': '', 'total_waste': w}
            for g, w in top_groups
        ]
        top_origin_ids = []
    if top_origin_ids:
        origin_names_map = {}
        origin_path_map = {}
        try:
            origins_result = reports_service.get_origin_by_organization(organization_id=organization_id, current_user_id=current_user_id)
            location_data = (origins_result.get('data') or {}).get('location') or {}
            for level_key in ('branches', 'buildings', 'floors', 'rooms'):
                for o in location_data.get(level_key, []) or []:
                    oid = o.get('id')
                    if oid is None:
                        continue
                    if oid not in origin_names_map:
                        origin_names_map[oid] = o.get('name')
                    if oid not in origin_path_map:
                        origin_path_map[oid] = o.get('path') or ''
        except Exception:
            pass
        top_recyclables = [
            {'origin_id': oid, 'origin_name': origin_names_map.get(oid), 'path': origin_path_map.get(oid, ''), 'total_waste': w}
            for oid, w in top_origin_ids
        ]

    # Recycled kg per month, for the stacked "recycled vs the rest" chart. Same
    # per-record basis as top_recyclables (the generation set, traced outcome where a
    # chain exists, category otherwise); the headline rate may be outcome-measured at
    # org scope, so the monthly split is an honest breakdown, not a second rate.
    month_recycled_by_year: Dict[int, Dict[int, float]] = {}
    for (w, _ghg, cat, gid), ym in zip(record_weights, record_months):
        if ym is None:
            continue
        rw = is_record_recyclable(w, cat, gid, group_leaf_data, group_completion)
        if rw > 0:
            yb = month_recycled_by_year.setdefault(ym[0], {})
            yb[ym[1]] = yb.get(ym[1], 0.0) + rw

    # Per-day totals for the "daily" chart granularity (same recycled basis as monthly).
    day_totals: Dict[str, list] = {}
    for (w, _ghg, cat, gid), day in zip(record_weights, record_days):
        if day is None:
            continue
        bucket = day_totals.setdefault(day, [0.0, 0.0])
        bucket[0] += w
        rw = is_record_recyclable(w, cat, gid, group_leaf_data, group_completion)
        if rw > 0:
            bucket[1] += rw
    def _cat_kg(m: Dict[int, float]) -> Dict[str, float]:
        return {str(c): round(kg, 2) for c, kg in (m or {}).items() if kg > 0}

    daily_data = [
        {'date': d, 'value': round(v[0], 2), 'recycled': round(min(v[1], v[0]), 2),
         'by_category': _cat_kg(day_cat.get(d))}
        for d, v in sorted(day_totals.items())
    ]

    # Chart data by year/month
    chart_data = {}
    for year in sorted(month_totals_by_year.keys()):
        monthly = month_totals_by_year[year]
        recycled = month_recycled_by_year.get(year, {})
        chart_data[str(year)] = [
            {
                'month': datetime(2000, m, 1).strftime('%b'),
                'value': round(monthly[m], 2),
                'recycled': round(min(recycled.get(m, 0.0), monthly[m]), 2),
                'by_category': _cat_kg(month_cat_by_year.get(year, {}).get(m)),
            }
            for m in sorted(monthly.keys())
        ]

    # Keep category assignments as-is (matching legacy report behavior).
    # Waste To Energy materials already have their own category_id=9.
    # Remove zero/negative category entries
    category_waste_map = {k: v for k, v in category_waste_map.items() if v > 0}

    # Category proportions
    category_names_map = _fetch_category_names(reports_service.db, set(category_waste_map.keys()))
    waste_type_proportions = [
        {
            'category_id': cid,
            'category_name': category_names_map.get(cid, f"Category {cid}"),
            'total_waste': round(total * 100) / 100,
            'proportion_percent': (total / total_waste * 100) if total_waste > 0 else 0.0,
        }
        for cid, total in category_waste_map.items()
    ]
    waste_type_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

    # Waste per head — total waste over the headcount, paired per subtree so only the
    # locations that actually have a headcount contribute to BOTH sides of the division.
    # Note the numerator is NOT `total_waste`: waste recorded under a branch nobody gave a
    # headcount for is excluded, otherwise it would be divided by people who don't cover it.
    # None when nothing in scope has a headcount → the card shows N/A plus a CTA.
    per_capita = _resolve_per_capita_scope(reports_service, organization_id, filters or {})
    headcount = per_capita['total']
    covered_origin_ids = per_capita['covered_ids']
    per_capita_waste = sum(
        w for (oid, w, _ghg, _cat, _group) in record_origins if oid in covered_origin_ids
    )
    waste_per_head = (
        round(per_capita_waste / headcount * 100) / 100
        if headcount and headcount > 0 else None
    )

    # ── Separation quality ("ฝีมือคัดแยก") ─────────────────────────────────
    # What a tenant CAN be measured on. Their material's final fate is decided
    # in a shared sorting room and cannot honestly be attributed back to them —
    # but how cleanly they handed it over is entirely theirs, differs between
    # good and careless tenants, and moves in the right direction when they
    # improve. This is the number a filtered (per-tenant) view leads with.
    # Same category set the rate's own fallback tier uses — imported, not
    # retyped, so the two can never drift apart.
    from .recycling_rate_helper import _RECYCLABLE_CATEGORIES
    separation_recyclable = sum(
        w for w, _ghg, cat, _g in record_weights if cat in _RECYCLABLE_CATEGORIES
    )
    separation_rate = (
        round(separation_recyclable / total_waste * 10000) / 100
        if total_waste > 0 else 0.0
    )

    # Material still sitting in collection points, in this scope. Org scope: the
    # sum of every tank's balance. Narrowed scope: what this scope handed over
    # and is still awaiting an outcome for. Either way it explains the gap
    # between "generated" and "accounted for" instead of leaving it unexplained.
    collection_shortfall_kg = 0.0
    collection_points_negative = 0
    if outcome_scope:
        try:
            from ..traceability.traceability_service import TraceabilityService
            _tsvc = TraceabilityService(reports_service.db)
            # Cumulative to the END of the VIEWED window, not to today: the card
            # sits beside date-filtered totals, and "what is still in the rooms"
            # next to January's tonnage has to mean January. date_to is stored as
            # a UTC ISO string; the ledger buckets by Bangkok months like the
            # board does, so convert before taking year/month.
            _as_of = datetime.now(ZoneInfo('Asia/Bangkok'))
            _date_to_raw = (filters or {}).get('date_to')
            if _date_to_raw:
                try:
                    _dt = datetime.fromisoformat(str(_date_to_raw).replace('Z', '+00:00'))
                    if _dt.tzinfo is None:
                        _dt = _dt.replace(tzinfo=timezone.utc)
                    _as_of = _dt.astimezone(ZoneInfo('Asia/Bangkok'))
                except (ValueError, TypeError):
                    pass
            _cps = _tsvc._collection_point_balances(organization_id, _as_of.year, _as_of.month)
            # Same roll-up the board uses, so the two screens can never disagree:
            # stock and shortfall stay separate rather than cancelling out.
            _summary = _tsvc.summarise_collection_balances(_cps)
            in_collection_kg = _summary['in_collection_kg']
            collection_shortfall_kg = _summary['shortfall_kg']
            collection_points_negative = _summary['negative_points']
        except Exception as _cp_err:  # noqa: BLE001
            logger.warning("[overview] collection balance read failed: %s", _cp_err)
            in_collection_kg = superseded_kg
    else:
        # A narrowed scope reports what IT handed over and is still waiting on;
        # a shortfall belongs to the room, which is org-level by nature.
        in_collection_kg = superseded_kg

    return {
        'transactions_total': len(tx_ids),
        'transactions_approved': len(tx_approved),
        'key_indicators': {
            'total_waste': round(total_waste * 100) / 100,
            # See resolve_rate_presentation for the whole policy. None (not 0)
            # only where an answer would be wrong — a narrowed scope whose
            # material meets a tank; the UI shows "อยู่ระหว่างจัดการโดยจุดรวม"
            # with in_collection_kg there instead. recycle_rate_estimate is the
            # pre-tank number, non-null only when it rides along as the
            # view-toggle counterpart of a measured rate.
            'recycle_rate': recycle_rate_out,
            'recycle_rate_basis': recycle_rate_basis,
            'recycle_rate_estimate': recycle_rate_toggle,
            # GHG saved is derived from what counts as recycled, so it belongs to
            # the SAME basis as the rate. Without this the view toggle moved the
            # rate while the GHG figure sat still, quietly mixing a measured
            # number with an estimated one on the same card.
            'ghg_reduction_estimate': (
                round(_est_ghg * 100) / 100 if recycle_rate_toggle is not None else None
            ),
            'separation_rate': separation_rate,
            'in_collection_kg': in_collection_kg,
            # More has left the collection points than ever arrived there —
            # waste reaching a room without passing the scale, or a bad
            # weighing. Positive number; 0 means every room balances.
            'collection_shortfall_kg': collection_shortfall_kg,
            'collection_points_negative': collection_points_negative,
            'ghg_reduction': round(recyclable_ghg_reduction * 100) / 100,
            'total_ghg_generated': round(ghg_reduction * 100) / 100,
        },
        'top_recyclables': top_recyclables,
        'overall_charts': {
            # `unit` is a language-independent key, not a label: the title is already
            # translated by the time the PDF sees it, so keying the unit off the title
            # would break the moment the language changes.
            'chart_stat_data': [
                {'title': 'Total Recyclables', 'value': round(recyclable_waste * 100) / 100, 'unit': 'kg'},
                {'title': 'Number of Trees', 'value': int(round(kg_co2_to_trees(recyclable_ghg_reduction) * 100 / 100)), 'unit': 'trees'},
                # {'title': 'Forest (rai)', 'value': round(kg_co2_to_forest_rai(recyclable_ghg_reduction) * 100) / 100},
                {'title': 'Plastic Saved', 'value': round(plastic_saved * 100) / 100, 'unit': 'kg'},
                # headcount travels with the card so the UI can print the denominator —
                # a bare kg/head number is unreadable without knowing what it divided by.
                # Its unit lives in the title ("(kg)"), so the sub-line carries the
                # denominator instead of repeating it.
                {'title': 'Waste per Head', 'value': waste_per_head, 'headcount': headcount},
            ],
            'chart_data': chart_data,
            'daily_data': daily_data,
        },
        'report_mode': report_mode,
        'waste_type_proportions': waste_type_proportions,
        'material_summary': [],
        'traceability_fully_managed': traceability_fully_managed,
    }


def _handle_materials_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Handle /api/reports/materials endpoint — optimized lightweight query path"""
    current_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    # Use optimized single-query path (returns lightweight tuples)
    result = reports_service.get_overview_data(
        organization_id=organization_id,
        filters=filters if filters else None,
        current_user_id=current_user_id
    )
    rows = result.get('rows', [])

    # Tuple indices from get_overview_data query:
    # 0: origin_quantity, 1: transaction_date, 2: created_transaction_id,
    # 3: origin_id, 4: status, 5: unit_weight, 6: calc_ghg,
    # 7: mat_category_id, 8: mat_main_material_id, 9: material_tags,
    # 10: origin_weight_kg, 11: record_category_id, 12: record_main_material_id,
    # 13: material_id, 14: material_name_en, 15: material_name_th,
    # 16: disposal_method, 17: record_status

    # Single pass: aggregate by main material AND sub material.
    # Group keys are EITHER an int main_material_id OR the sentinel string
    # WTE_KEY for waste-to-energy items. WTE items share main_material_id
    # with their disposal-route source (e.g. CDs and dirty plastic bags
    # carry main_material_id=Plastic), but they're *not* recyclable plastic
    # and grouping them under "พลาสติก" reads as a data error. Split them
    # into their own group keyed by category instead.
    WTE_KEY = '__wte__'

    main_material_agg_map: Dict[Any, Dict[str, float]] = {}
    sub_material_agg_map: Dict[int, Dict[str, Any]] = {}
    total_waste_main = 0.0
    sub_total_waste = 0.0

    for row in rows:
        origin_qty = float(row[0] or 0)
        status = row[4]
        unit_weight = float(row[5] or 0)
        calc_ghg = float(row[6] or 0)
        cat_id = row[7] or row[11]   # mat_category_id || record_category_id
        main_id = row[8] or row[12]  # mat_main_material_id || record_main_material_id
        material_id = row[13]
        mat_name_en = row[14]
        mat_name_th = row[15]

        if status == TransactionStatus.rejected:
            continue

        weight = origin_qty * unit_weight
        ghg = weight * calc_ghg

        try:
            cat_id_int = int(cat_id) if cat_id is not None else None
        except Exception:
            cat_id_int = None
        is_wte = cat_id_int == _WASTE_TO_ENERGY_CAT_ID

        # Resolve the effective group key: WTE items get their own bucket,
        # everyone else groups by their main_material_id as before.
        if is_wte:
            effective_key: Any = WTE_KEY
            try:
                main_id_int = int(main_id) if main_id is not None else None
            except Exception:
                main_id_int = None
        else:
            if main_id is None:
                continue
            try:
                main_id_int = int(main_id)
            except Exception:
                continue
            effective_key = main_id_int

        # Aggregate by group (main material or WTE)
        total_waste_main += weight
        if effective_key not in main_material_agg_map:
            main_material_agg_map[effective_key] = {'total_waste': 0.0, 'ghg_reduction': 0.0}
        main_material_agg_map[effective_key]['total_waste'] += weight
        main_material_agg_map[effective_key]['ghg_reduction'] += ghg

        # Aggregate by sub material (material_id)
        if material_id is not None:
            try:
                mat_id_int = int(material_id)
            except Exception:
                continue
            sub_total_waste += weight
            if mat_id_int not in sub_material_agg_map:
                sub_material_agg_map[mat_id_int] = {
                    'material_id': mat_id_int,
                    'material_name': mat_name_en or mat_name_th,
                    'material_name_en': mat_name_en,
                    'material_name_th': mat_name_th,
                    'main_material_id': main_id_int,
                    'category_id': cat_id_int,
                    'effective_key': effective_key,
                    'total_waste': 0.0,
                    'ghg_reduction': 0.0,
                }
            sub_material_agg_map[mat_id_int]['total_waste'] += weight
            sub_material_agg_map[mat_id_int]['ghg_reduction'] += ghg

    # Fetch main material names (bilingual) — only for real int keys
    real_main_ids = {k for k in main_material_agg_map.keys() if isinstance(k, int)}
    name_map = _fetch_main_material_names_bilingual(reports_service.db, real_main_ids)

    # Fetch the WTE category's bilingual display name so the synthetic group
    # surface area in the response carries proper Thai + English labels.
    wte_names = _fetch_category_names_bilingual(
        reports_service.db, {_WASTE_TO_ENERGY_CAT_ID}
    ).get(_WASTE_TO_ENERGY_CAT_ID, {}) if WTE_KEY in main_material_agg_map else {}
    wte_name_en = wte_names.get('name_en') or 'Waste To Energy'
    wte_name_th = wte_names.get('name_th') or 'ขยะเพื่อพลังงาน'

    def _group_labels(key: Any) -> Dict[str, Optional[str]]:
        """Return the bilingual display labels for a group key."""
        if key == WTE_KEY:
            return {'name_en': wte_name_en, 'name_th': wte_name_th}
        if isinstance(key, int):
            return name_map.get(key) or {'name_en': None, 'name_th': None}
        return {'name_en': None, 'name_th': None}

    # Build proportions for main material rollup (incl. WTE as its own row)
    proportions = []
    for key, agg in sorted(
        main_material_agg_map.items(),
        key=lambda kv: kv[1]['total_waste'],
        reverse=True,
    ):
        labels = _group_labels(key)
        proportions.append({
            'main_material_id': key if isinstance(key, int) else None,
            'main_material_name': labels.get('name_en') or labels.get('name_th'),
            'main_material_name_en': labels.get('name_en'),
            'main_material_name_th': labels.get('name_th'),
            'is_waste_to_energy': key == WTE_KEY,
            'total_waste': agg['total_waste'],
            'ghg_reduction': agg['ghg_reduction'],
            'proportion_percent': (agg['total_waste'] / total_waste_main * 100) if total_waste_main > 0 else 0.0,
        })

    # Build sub proportions
    sub_proportions = []
    for item in sub_material_agg_map.values():
        item['proportion_percent'] = (item['total_waste'] / sub_total_waste * 100) if sub_total_waste > 0 else 0.0
        sub_proportions.append(item)
    sub_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

    # Group sub materials by effective key (main material or WTE bucket)
    grouped_by_main: Dict[str, list] = {}
    for item in sub_proportions:
        key = item.get('effective_key')
        labels = _group_labels(key)
        key_name = (
            labels.get('name_en')
            or labels.get('name_th')
            or (f"Material {key}" if isinstance(key, int) else "Unknown")
        )
        if key_name not in grouped_by_main:
            grouped_by_main[key_name] = []
        grouped_by_main[key_name].append({
            'material_id': item.get('material_id'),
            'material_name': item.get('material_name'),
            'material_name_en': item.get('material_name_en'),
            'material_name_th': item.get('material_name_th'),
            'total_waste': item.get('total_waste'),
            'ghg_reduction': item.get('ghg_reduction'),
            'proportion_percent': item.get('proportion_percent'),
        })
    for k in grouped_by_main:
        grouped_by_main[k].sort(key=lambda x: x['total_waste'], reverse=True)

    return {
        'main_material': {
            'porportions': proportions,
            'total_waste': total_waste_main,
        },
        'sub_material': {
            'porportions': sub_proportions,
            'porportions_grouped': grouped_by_main,
            'total_waste': sub_total_waste,
        }
    }


def _handle_diversion_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Handle /api/reports/diversion endpoint — uses traceability hierarchy data."""

    from ..traceability.traceability_service import TraceabilityService
    traceability_service = TraceabilityService(reports_service.db)

    # --- Resolve date range into individual (year, month) pairs ---
    date_from_str = filters.get("date_from")
    date_to_str = filters.get("date_to")
    months_to_query: list = []
    if date_from_str and date_to_str:
        try:
            tz = ZoneInfo("Asia/Bangkok")
            dt_from = datetime.fromisoformat(str(date_from_str).replace("Z", "+00:00"))
            dt_to = datetime.fromisoformat(str(date_to_str).replace("Z", "+00:00"))
            if dt_from.tzinfo is None:
                dt_from = dt_from.replace(tzinfo=timezone.utc)
            if dt_to.tzinfo is None:
                dt_to = dt_to.replace(tzinfo=timezone.utc)
            local_from = dt_from.astimezone(tz)
            local_to = dt_to.astimezone(tz)
            y, m = local_from.year, local_from.month
            while (y, m) <= (local_to.year, local_to.month):
                months_to_query.append((y, m))
                m += 1
                if m > 12:
                    m = 1
                    y += 1
        except Exception:
            pass

    if not months_to_query:
        return {
            "card_data": {"total_origin": 0, "complete_transfer": 0.0, "processing_transfer": 0.0, "completed_rate": 0.0},
            "sankey_data": [["From", "To", "Weight"]],
            "material_table": [],
            "materials_data": [],
        }

    # --- Build kwargs for traceability hierarchy (full report filter set) ---
    # Historically only material + a single origin were honored here, so the report
    # filter bar (cascading location levels, tag, tenant, destination) silently did
    # nothing on the diversion tab. We now thread the whole filter set through.
    hierarchy_kwargs: Dict[str, Any] = {}
    mat_ids = filters.get("material_ids")
    if mat_ids:
        hierarchy_kwargs["material_id"] = ",".join(str(m) for m in mat_ids)

    # Origin-side: prefer the new-style multi-select location_ids (expanded to
    # descendants, same as the other tabs), else fall back to the legacy origin composite.
    location_ids = filters.get("location_ids")
    if location_ids:
        expanded_origin_ids = reports_service._resolve_descendant_ids(organization_id, location_ids)
        if expanded_origin_ids:
            hierarchy_kwargs["origin_ids"] = ",".join(str(x) for x in expanded_origin_ids)
    else:
        origin_combos = filters.get("origin_combos")
        origin_ids = filters.get("origin_ids")
        if origin_combos:
            # Use first combo for per-month query; multi-origin handled below via post-filter
            combo = origin_combos[0]
            hierarchy_kwargs["origin_id"] = "|".join(str(v) if v is not None else "" for v in combo)
        elif origin_ids:
            hierarchy_kwargs["origin_id"] = str(origin_ids[0])

    # Tag / tenant multi-select (AND). Destination filter ("สถานที่รับขยะ"). Member gate.
    if filters.get("filter_tag_ids"):
        hierarchy_kwargs["tag_ids"] = ",".join(str(x) for x in filters["filter_tag_ids"])
    if filters.get("filter_tenant_ids"):
        hierarchy_kwargs["tenant_ids"] = ",".join(str(x) for x in filters["filter_tenant_ids"])
    if filters.get("destination_ids"):
        hierarchy_kwargs["destination_ids"] = ",".join(str(x) for x in filters["destination_ids"])
    cu_id = (current_user or {}).get("user_id")
    if cu_id:
        hierarchy_kwargs["current_user_id"] = cu_id

    # --- Collect hierarchy data across all months ---
    all_hierarchy: list = []
    for year, month in months_to_query:
        first_day = datetime(year, month, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
        kw = dict(hierarchy_kwargs)
        kw["date_from"] = first_day.astimezone(timezone.utc).isoformat()
        kw["date_to"] = first_day.astimezone(timezone.utc).isoformat()  # same month
        result = traceability_service.get_traceability_hierarchy(organization_id, _exclude_idle=True, **kw)
        hierarchy_data = result.get("data") or []
        all_hierarchy.extend(hierarchy_data)

    # --- Walk hierarchy to compute card_data, sankey, material_table, materials_data ---
    _DIVERTED = {
        "Preparation for reuse", "Recycling (Own)",
        "Other recover operation", "Recycle",
    }
    _DIRECTED = {
        "Composted by municipality", "Municipality receive",
        "Incineration without energy", "Incineration with energy",
    }

    unique_origins: set = set()
    complete_transfer = 0.0
    total_group_weight = 0.0  # sum of all group weights (for weighted avg)
    completed_weight = 0.0    # sum of group_weight * group_completed_pct / 100
    sankey_map: Dict[tuple, float] = {}
    material_table_map: Dict[int, Dict] = {}
    material_ids_set: set = set()
    category_to_main_map: Dict[int, set] = {}

    def _get_leaves(nodes: list) -> list:
        """Collect all leaf transport nodes."""
        leaves = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            children = n.get("children") or []
            if children:
                leaves.extend(_get_leaves(children))
            else:
                leaves.append(n)
        return leaves

    def _collect_subtree_consolidated_weight(node: dict) -> float:
        total = 0.0

        def walk(n: dict) -> None:
            nonlocal total
            if not isinstance(n, dict):
                return
            sources = n.get("consolidation_sources")
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        total += float(source.get("contributed_weight") or 0)
            for child in n.get("children") or []:
                walk(child)

        walk(node)
        return round(total, 2)

    def _add_consolidation_source_origins(node: dict) -> None:
        if not isinstance(node, dict):
            return
        sources = node.get("consolidation_sources")
        if isinstance(sources, list):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                origin = source.get("source_origin") or {}
                origin_id = origin.get("id") if isinstance(origin, dict) else None
                if origin_id is not None:
                    unique_origins.add(origin_id)
        for child in node.get("children") or []:
            _add_consolidation_source_origins(child)

    for origin_node in all_hierarchy:
        if not isinstance(origin_node, dict):
            continue
        origin_id = origin_node.get("origin_id")
        group_children = origin_node.get("children") or []
        if group_children and origin_id is not None:
            unique_origins.add(origin_id)

        for group_node in group_children:
            if not isinstance(group_node, dict):
                continue
            consolidated_weight = _collect_subtree_consolidated_weight(group_node)
            group_weight = consolidated_weight if consolidated_weight > 0 else float(group_node.get("weight") or group_node.get("total_weight_kg") or 0)
            group_month = group_node.get("transaction_month")
            # Use the group's (original) material for sankey / material_table
            group_mat_info = group_node.get("material") or {}
            main_material_id = group_mat_info.get("main_material_id")
            category_id = group_mat_info.get("category_id")
            leaves = _get_leaves(group_node.get("children") or [])
            _add_consolidation_source_origins(group_node)

            # Track category -> main_material mapping once per group
            if main_material_id is not None and category_id is not None:
                try:
                    cid = int(category_id)
                    mid = int(main_material_id)
                    category_to_main_map.setdefault(cid, set()).add(mid)
                except (ValueError, TypeError):
                    pass

            group_completed_pct = 0.0  # sum of percentage_of_group for arrived+method leaves in this group
            total_group_weight += group_weight

            for leaf in leaves:
                status = leaf.get("status") or ""
                method = (leaf.get("disposal_method") or "").strip() or None
                leaf_weight = float(leaf.get("weight") or 0)
                leaf_pct = float(leaf.get("percentage_of_group") or 0)

                # complete_transfer: sum weight of leafest nodes that have a disposal method and arrived
                if status == "arrived" and method:
                    complete_transfer += leaf_weight
                    group_completed_pct += leaf_pct

                # sankey: group material -> disposal method
                if main_material_id is not None and method:
                    material_ids_set.add(main_material_id)
                    key = (main_material_id, method)
                    sankey_map[key] = sankey_map.get(key, 0.0) + leaf_weight

                # material_table: aggregate by group's main_material_id and month
                if main_material_id is not None:
                    material_ids_set.add(main_material_id)
                    if main_material_id not in material_table_map:
                        material_table_map[main_material_id] = {
                            "monthly_data": {},
                            "destinations": set(),
                            "has_incomplete": False,
                        }
                    entry = material_table_map[main_material_id]
                    if group_month:
                        entry["monthly_data"][group_month] = entry["monthly_data"].get(group_month, 0.0) + leaf_weight
                    if method:
                        entry["destinations"].add(method)
                    if status != "arrived" or not method:
                        entry["has_incomplete"] = True

            # Weighted contribution of this group's completion rate
            completed_weight += group_weight * group_completed_pct / 100

    # --- Card data ---
    completed_rate = round((completed_weight / total_group_weight * 100) if total_group_weight > 0 else 0.0, 2)
    processing_transfer = round(100.0 - completed_rate, 2)

    # --- Fetch main material names ---
    main_material_names = _fetch_main_material_names(reports_service.db, material_ids_set)
    main_material_names_bilingual = _fetch_main_material_names_bilingual(reports_service.db, material_ids_set)

    # --- Sankey ---
    sankey_data = [["From", "From_TH", "To", "Weight"]]
    for (mm_id_key, method), w in sankey_map.items():
        names = main_material_names_bilingual.get(mm_id_key, {"name_en": f"Material {mm_id_key}", "name_th": f"Material {mm_id_key}"})
        from_name_en = names["name_en"]
        from_name_th = names["name_th"]
        to_name = method or "Unknown Disposal"
        sankey_data.append([from_name_en, from_name_th, to_name, w])

    # --- Material table ---
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    material_table = []
    for mid, entry in material_table_map.items():
        monthly_data = [
            {"month": month_names[m - 1], "value": entry["monthly_data"][m]}
            for m in range(1, 13)
            if m in entry["monthly_data"]
        ]
        status = "Processing" if entry["has_incomplete"] else "Completed"
        names = main_material_names_bilingual.get(mid, {"name_en": f"Material {mid}", "name_th": f"Material {mid}"})
        material_table.append({
            "key": mid,
            "materials": names["name_en"],
            "materials_th": names["name_th"],
            "materials_en": names["name_en"],
            "data": monthly_data,
            "status": status,
            "destination": list(entry["destinations"]),
        })

    # --- Materials data (Dangerous vs Non-Dangerous) ---
    danger_cids = {5, 6}
    dangerous_main_ids: set = set()
    non_dangerous_main_ids: set = set()
    for cid, mm_set in category_to_main_map.items():
        if cid in danger_cids:
            dangerous_main_ids.update(mm_set)
        else:
            non_dangerous_main_ids.update(mm_set)

    def build_main_children(mm_ids: set) -> list:
        return [
            {
                "id": mid,
                "name": main_material_names.get(mid, f"Material {mid}"),
                "name_en": main_material_names_bilingual.get(mid, {}).get("name_en", f"Material {mid}"),
                "name_th": main_material_names_bilingual.get(mid, {}).get("name_th", f"Material {mid}"),
            }
            for mid in sorted(mm_ids)
        ]

    materials_data = [
        {"category_name": "Dangerous Waste", "main_materials": build_main_children(dangerous_main_ids)},
        {"category_name": "Non-Dangerous Waste", "main_materials": build_main_children(non_dangerous_main_ids)},
    ]

    return {
        "card_data": {
            "total_origin": len(unique_origins),
            "complete_transfer": round(complete_transfer, 2),
            "processing_transfer": processing_transfer,
            "completed_rate": completed_rate,
        },
        "sankey_data": sankey_data,
        "material_table": material_table,
        "materials_data": materials_data,
    }

def _handle_performance_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Handle /api/reports/performance endpoint — optimized single-query path"""
    current_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    # Get organization setup with active root_nodes
    organization_setup = reports_service.get_organization_setup(
        organization_id=organization_id
    )

    setup_data = organization_setup.get('data')
    report_mode = _report_mode(filters)
    # Tag / tenant mode groups by those ids, not by the location tree, so it doesn't need one.
    if report_mode == 'location' and (not setup_data or not setup_data.get('root_nodes')):
        return {
            'success': True,
            'data': [],
            'message': 'No organization setup found'
        }

    root_nodes = (setup_data or {}).get('root_nodes', [])

    # Use optimized single-query path (same as overview)
    result = reports_service.get_overview_data(
        organization_id=organization_id,
        filters=filters if filters else None,
        current_user_id=current_user_id
    )
    rows = result.get('rows', [])
    group_records_map: Dict[Any, list] = {}   # tag/tenant id (None = unassigned) → record tuples

    from .recycling_rate_helper import compute_recycling_rate, fetch_group_leaf_data

    # Collect all category IDs from rows and fetch names
    all_category_ids = set()
    # Build location ID → list of (origin_quantity, unit_weight, category_id, main_material_id, calc_ghg, group_id) tuples
    location_records_map: Dict[int, list] = {}
    perf_record_ids = []
    for row in rows:
        # Unpack the first 20 columns from get_overview_data (20/21 = tag/tenant ids)
        (origin_qty, txn_date, txn_id, origin_id, status,
         unit_weight, calc_ghg, mat_category_id, mat_main_material_id, material_tags,
         origin_weight_kg, record_category_id, record_main_material_id,
         _mat_id, _mat_name_en, _mat_name_th,
         _disposal_method, _record_status, _traceability_group_id, record_id) = row[:20]

        # Use Material category as primary source (matches old reportUtils logic)
        category_id = mat_category_id or record_category_id
        main_material_id = mat_main_material_id or record_main_material_id

        if status == TransactionStatus.rejected:
            continue
        if report_mode != 'location':
            group_records_map.setdefault(_row_group_id(row, report_mode), []).append((
                float(origin_qty or 0),
                float(unit_weight or 0),
                int(category_id) if category_id is not None else None,
                int(main_material_id) if main_material_id is not None else None,
                float(calc_ghg or 0),
                record_id,
            ))
            perf_record_ids.append(record_id)
        if origin_id:
            if origin_id not in location_records_map:
                location_records_map[origin_id] = []
            location_records_map[origin_id].append((
                float(origin_qty or 0),
                float(unit_weight or 0),
                int(category_id) if category_id is not None else None,
                int(main_material_id) if main_material_id is not None else None,
                float(calc_ghg or 0),
                record_id,  # temporarily store record_id; resolve to group_id below
            ))
            perf_record_ids.append(record_id)
        if category_id is not None:
            try:
                all_category_ids.add(int(category_id))
            except Exception:
                pass

    # Build record_id → group_id mapping from TraceabilityTransactionGroup.transaction_record_id arrays
    from ....models.transactions.traceability_transaction_group import TraceabilityTransactionGroup as PerfTTG
    perf_record_to_group = {}
    if perf_record_ids:
        perf_groups = reports_service.db.query(
            PerfTTG.id, PerfTTG.transaction_record_id,
        ).filter(
            PerfTTG.organization_id == organization_id,
            PerfTTG.is_active == True,
            PerfTTG.deleted_date.is_(None),
        ).all()
        for gid, rec_ids in perf_groups:
            if rec_ids:
                for rid in rec_ids:
                    perf_record_to_group[rid] = gid

    # Replace record_id with group_id in location_records_map
    for loc_id in location_records_map:
        location_records_map[loc_id] = [
            (qty, uw, cat, mm, ghg, perf_record_to_group.get(rid))
            for qty, uw, cat, mm, ghg, rid in location_records_map[loc_id]
        ]
    for grp in group_records_map:
        group_records_map[grp] = [
            (qty, uw, cat, mm, ghg, perf_record_to_group.get(rid))
            for qty, uw, cat, mm, ghg, rid in group_records_map[grp]
        ]
    all_group_ids = {
        group_id
        for records in list(location_records_map.values()) + list(group_records_map.values())
        for *_prefix, group_id in records
        if group_id is not None
    }

    # Pre-fetch traceability leaf data for all groups across all locations (single query)
    perf_group_leaf_data, perf_group_completion = fetch_group_leaf_data(reports_service.db, all_group_ids)

    # Collect all location IDs from hierarchy and fetch names
    location_ids = set()

    def collect_location_ids(nodes):
        for node in nodes:
            node_id = node.get('nodeId')
            if node_id:
                try:
                    location_ids.add(int(node_id))
                except (ValueError, TypeError):
                    pass
            children = node.get('children', [])
            if children:
                collect_location_ids(children)

    collect_location_ids(root_nodes)
    location_names = _fetch_destination_names(reports_service.db, location_ids)
    category_names = _fetch_category_names(reports_service.db, all_category_ids)

    # Look up GENERAL_WASTE main_material_id once for waste-to-energy splitting
    _perf_gw_mm_id = _get_general_waste_mm_id(reports_service.db)

    # Track if all nodes are fully traced for disclaimer flag
    perf_all_fully_traced = True

    # Helper to calculate metrics from lightweight tuples
    def calculate_metrics(records):
        """records: list of (origin_qty, unit_weight, category_id, main_material_id, calc_ghg, group_id) tuples"""
        nonlocal perf_all_fully_traced
        material_metrics: Dict[str, float] = {}
        cat_mm_map: Dict[Tuple[int, int], float] = {}
        total_weight = 0.0
        general_weight = 0.0

        # Build record_weights for 3-tier recycling rate
        node_record_weights = []

        for origin_qty, unit_weight, cat_id, mm_id, calc_ghg, group_id in records:
            weight = origin_qty * unit_weight
            total_weight += weight

            if cat_id is not None:
                material_name = category_names.get(cat_id, f"Category {cat_id}")
                material_metrics[material_name] = material_metrics.get(material_name, 0.0) + weight
                # Track (cat_id, mm_id) for waste-to-energy splitting
                if mm_id is not None:
                    key = (cat_id, mm_id)
                    cat_mm_map[key] = cat_mm_map.get(key, 0.0) + weight

            if cat_id == _GENERAL_WASTE_CAT_ID:
                general_weight += weight

            node_record_weights.append((weight, calc_ghg, cat_id, group_id))

        # Split Waste to Energy out of General Waste
        _split_waste_to_energy(material_metrics, cat_mm_map, _perf_gw_mm_id, category_names)

        # 3-tier recycling rate using pre-fetched traceability data.
        # supersede_delivered stays OFF here: this report answers "what did each
        # node hand over, by composition" — the two-scope outcome arithmetic is
        # the overview's job, and switching it on would zero out every tenant
        # node while the local denominator kept their full weight.
        recyclable_weight, _, _, node_fully_traced, _ = compute_recycling_rate(
            node_record_weights, perf_group_leaf_data, perf_group_completion
        )
        if not node_fully_traced:
            perf_all_fully_traced = False

        recycling_rate = (recyclable_weight / total_weight * 100) if total_weight > 0 else 0.0
        return {
            'metrics': {k: round(v, 2) for k, v in material_metrics.items() if v > 0},
            'totalWasteKg': round(total_weight, 2),
            'recyclingRatePercent': round(recycling_rate, 2),
            'recyclable_weight': round(recyclable_weight, 2),
            'general_weight': round(general_weight, 2)
        }

    if report_mode != 'location':
        # One summary row for the whole scope + one row per tag/tenant, in the same shape
        # the location view uses (branch with `buildings`), so the web tab and the PDF
        # render it with the same components. Unassigned records stay in as their own row
        # (flagged) so the rows add up to the summary.
        names = _fetch_group_names(reports_service.db, report_mode, {g for g in group_records_map if g is not None})
        for gid in [g for g in group_records_map if g is not None and g not in names]:
            group_records_map.setdefault(None, []).extend(group_records_map.pop(gid))
        groups = []
        for gid, recs in group_records_map.items():
            calc = calculate_metrics(recs)
            if calc['totalWasteKg'] == 0:
                continue
            groups.append({
                'id': str(gid) if gid is not None else 'none',
                'unassigned': gid is None,
                'buildingName': names.get(gid, str(gid)) if gid is not None else None,
                'branchName': names.get(gid, str(gid)) if gid is not None else None,
                'totalWasteKg': calc['totalWasteKg'],
                'metrics': calc['metrics'],
                'recyclingRatePercent': calc['recyclingRatePercent'],
                'recyclable_weight': calc['recyclable_weight'],
                'general_weight': calc['general_weight'],
            })
        groups.sort(key=lambda g: (g['unassigned'], -g['totalWasteKg']))
        summary = calculate_metrics([r for recs in group_records_map.values() for r in recs])
        data = []
        if summary['totalWasteKg'] > 0:
            data = [{
                'id': 'all',
                'branchName': None,          # label comes from the mode ("all tenants" / "all tags")
                'totalWasteKg': summary['totalWasteKg'],
                'metrics': summary['metrics'],
                'recyclingRatePercent': summary['recyclingRatePercent'],
                'recyclable_weight': summary['recyclable_weight'],
                'general_weight': summary['general_weight'],
                'buildings': groups,
            }]
        return {
            'success': True,
            'data': data,
            'groups': groups,
            'report_mode': report_mode,
            'message': 'Performance report generated successfully',
            'traceability_fully_managed': perf_all_fully_traced,
        }

    # Determine the maximum depth of the hierarchy
    def get_max_depth(nodes, current_depth=0):
        if not nodes:
            return current_depth
        max_child_depth = current_depth
        for node in nodes:
            children = node.get('children', [])
            if children:
                child_depth = get_max_depth(children, current_depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth

    max_depth = get_max_depth(root_nodes)

    # Define the standard hierarchy sequence
    HIERARCHY_SEQUENCE = [
        ('branchName', 'buildings'),
        ('buildingName', 'floors'),
        ('floorName', 'rooms'),
        ('roomName', 'items'),
        ('itemName', 'items'),
    ]

    def get_level_config(total_depth):
        # ALWAYS start with branchName for level 0 (root nodes)
        # Then map subsequent levels based on actual depth
        configs = []
        for i in range(total_depth + 1):
            if i == 0:
                # Level 0 is always branchName
                name_key = 'branchName'
                children_key = 'buildings' if total_depth > 0 else None
                configs.append((name_key, children_key))
            else:
                # For deeper levels, map based on depth
                # depth 1 → building, depth 2 → floor, depth 3 → room, etc.
                seq_index = i
                if seq_index < len(HIERARCHY_SEQUENCE):
                    name_key, children_key = HIERARCHY_SEQUENCE[seq_index]
                    if i == total_depth:
                        configs.append((name_key, None))
                    else:
                        configs.append((name_key, children_key))
                else:
                    if i == total_depth:
                        configs.append(('itemName', None))
                    else:
                        configs.append(('itemName', 'items'))
        return configs

    level_configs = get_level_config(max_depth)

    # Recursive function to build hierarchy
    def build_hierarchy(nodes, level=0):
        result = []

        for node in nodes:
            node_id_str = node.get('nodeId')
            if not node_id_str:
                continue
            try:
                node_id = int(node_id_str)
            except (ValueError, TypeError):
                continue

            # Get records for this location
            node_records = location_records_map.get(node_id, [])
            children = node.get('children', [])
            child_items = build_hierarchy(children, level + 1) if children else []

            # Aggregate all records from this node and all descendants
            all_records = list(node_records)

            def collect_descendant_records(items):
                collected = []
                for item in items:
                    item_id = int(item['id'])
                    collected.extend(location_records_map.get(item_id, []))
                    for child_key in ['buildings', 'floors', 'rooms', 'items']:
                        if child_key in item:
                            for child in item[child_key]:
                                collected.extend(collect_descendant_records([child]))
                return collected

            if child_items:
                all_records.extend(collect_descendant_records(child_items))

            calc = calculate_metrics(all_records)
            if calc['totalWasteKg'] == 0:
                continue

            location_name = location_names.get(node_id, f"Location {node_id}")
            item = {
                'id': str(node_id),
                'totalWasteKg': calc['totalWasteKg'],
                'metrics': calc['metrics'],
            }

            if level == 0:
                item['recyclingRatePercent'] = calc['recyclingRatePercent']
                item['recyclable_weight'] = calc['recyclable_weight']
                item['general_weight'] = calc['general_weight']

            if level < len(level_configs):
                name_key, children_key = level_configs[level]
            else:
                name_key, children_key = ('itemName', 'items' if children else None)

            item[name_key] = location_name

            # Debug logging for root level nodes
            if level == 0:
                print(f"[DEBUG] Level {level}: node_id={node_id}, name_key={name_key}, location_name=\"{location_name}\"")
            if child_items and children_key:
                item[children_key] = child_items

            result.append(item)

        return result

    performance_data = build_hierarchy(root_nodes)

    return {
        'success': True,
        'data': performance_data,
        'report_mode': 'location',
        'message': 'Performance report generated successfully',
        'traceability_fully_managed': perf_all_fully_traced,
    }

def _handle_comparison_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None,
    client_timezone: Optional[str] = None
) -> Dict[str, Any]:
    """Handle /api/reports/comparison endpoint

    compare_mode "yearly": the selected range vs the same range one year earlier
    (range within one calendar year, ≤ 365 days). compare_mode "monthly": the selected
    days vs the same days one month earlier (range within one month). Both sides are
    clamped to today. left = the earlier period, right = the selected one. Also returns
    the Risks / Opportunities / Quick wins cards for the report mode (report_rules.json).
    """
    
    # Get date range from filters (required for comparison)
    date_from = filters.get('date_from')
    date_to = filters.get('date_to')
    
    if not date_from or not date_to:
        raise ValidationException("date_from and date_to are required for comparison report")
    
    # Parse dates (these are already in UTC format from filter builder)
    right_from_dt = _parse_datetime(date_from)
    right_to_dt = _parse_datetime(date_to)
    
    if not right_from_dt or not right_to_dt:
        raise ValidationException("Invalid date_from or date_to format")
    
    # Ensure dates are timezone-aware (convert to UTC if needed)
    if right_from_dt.tzinfo is None:
        right_from_dt = right_from_dt.replace(tzinfo=timezone.utc)
    else:
        right_from_dt = right_from_dt.astimezone(timezone.utc)
    if right_to_dt.tzinfo is None:
        right_to_dt = right_to_dt.replace(tzinfo=timezone.utc)
    else:
        right_to_dt = right_to_dt.astimezone(timezone.utc)
    
    # For validation, we need to check the calendar dates as the user intended them
    # Convert UTC dates back to client timezone to get the actual calendar dates
    client_tz_name = client_timezone or 'Asia/Bangkok'
    try:
        client_tz = ZoneInfo(client_tz_name)
    except Exception:
        client_tz = ZoneInfo('UTC')
        client_tz_name = 'UTC'
    
    # Convert to client timezone to check calendar dates
    from_local = right_from_dt.astimezone(client_tz)
    to_local = right_to_dt.astimezone(client_tz)
    
    # Extract date portion (YYYY-MM-DD) from client timezone
    from_date = from_local.date()
    to_date = to_local.date()
    
    compare_mode = filters.get('compare_mode') if filters.get('compare_mode') in ('yearly', 'monthly') else 'yearly'
    report_mode = _report_mode(filters)

    if compare_mode == 'monthly':
        # Same days one month earlier, so the range has to sit inside one calendar month.
        if (from_date.year, from_date.month) != (to_date.year, to_date.month):
            raise ValidationException("Monthly comparison needs a date range within one month")
    else:
        # Validate period doesn't exceed 1 year
        delta_days = (to_date - from_date).days
        if delta_days > 365:
            raise ValidationException("Comparison period cannot exceed 1 year")
        # Check if dates are in the same calendar year (in client timezone)
        if from_date.year != to_date.year:
            raise ValidationException("Comparison period cannot cross years")

    from .report_insights import build_report_insights, comparison_periods, range_label, MONTHS_EN, MONTHS_TH

    # Both periods are clamped to today: "this year so far" against the same days last
    # year, never against the whole previous year.
    today_local = datetime.now(client_tz).date()
    cur_start, cur_end, prev_start, prev_end = comparison_periods(from_date, to_date, today_local, compare_mode)

    def _utc_bounds(start, end):
        s = datetime(start.year, start.month, start.day, tzinfo=client_tz).astimezone(timezone.utc)
        e = datetime(end.year, end.month, end.day, 23, 59, 59, 999000, tzinfo=client_tz).astimezone(timezone.utc)
        fmt = lambda d: d.strftime('%Y-%m-%dT%H:%M:%S.%f') + '+00:00'
        return fmt(s), fmt(e)

    _comparison_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    def fetch_rows(start, end):
        d_from, d_to = _utc_bounds(start, end)
        side_filters: Dict[str, Any] = {'date_from': d_from, 'date_to': d_to}
        # Same location/tag/tenant/material conventions as the other tabs.
        for key in ('material_ids', 'location_ids', 'filter_tag_ids', 'filter_tenant_ids', 'destination_ids'):
            if filters.get(key):
                side_filters[key] = filters[key]
        if filters.get('origin_combos'):
            side_filters['origin_combos'] = filters['origin_combos']
        elif filters.get('origin_ids'):
            side_filters['origin_ids'] = filters['origin_ids']
            if filters.get('location_tag_id') is not None:
                side_filters['location_tag_id'] = filters['location_tag_id']
            if filters.get('tenant_id') is not None:
                side_filters['tenant_id'] = filters['tenant_id']
        return reports_service.get_overview_data(
            organization_id=organization_id,
            filters=side_filters,
            current_user_id=_comparison_user_id,
            report_type='comparison'
        ).get('rows', [])

    cur_rows = fetch_rows(cur_start, cur_end)
    prev_rows = fetch_rows(prev_start, prev_end)

    # Tuple: (origin_qty, txn_date, txn_id, origin_id, status, unit_weight, calc_ghg,
    #         mat_cat_id, mat_mm_id, material_tags, origin_weight_kg, rec_cat_id,
    #         rec_mm_id, material_id, material_name_en, material_name_th, ..., tag_id, tenant_id)
    cat_ids: set = set()
    mm_ids: set = set()
    group_ids: set = set()
    for row in list(cur_rows) + list(prev_rows):
        if row[7] or row[11]:
            cat_ids.add(int(row[7] or row[11]))
        if row[8] or row[12]:
            mm_ids.add(int(row[8] or row[12]))
        gid = _row_group_id(row, report_mode)
        if gid is not None:
            group_ids.add(gid)
    cat_names = _fetch_category_names_bilingual(reports_service.db, cat_ids)
    mm_names = _fetch_main_material_names_bilingual(reports_service.db, mm_ids)
    group_names = _fetch_group_names(reports_service.db, report_mode, group_ids)

    def to_records(rows) -> list:
        out = []
        for row in rows:
            if row[4] == TransactionStatus.rejected:
                continue
            origin_qty = float(row[0] or 0)
            unit_weight = float(row[5] or 0)
            weight = origin_qty * unit_weight if unit_weight > 0 else float(row[10] or 0)
            txn_date = row[1]
            if not txn_date or weight <= 0:
                continue
            dt = txn_date if isinstance(txn_date, datetime) else _parse_datetime(str(txn_date))
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cat_id = row[7] or row[11]
            mm_id = row[8] or row[12]
            cat_en = (cat_names.get(int(cat_id)) or {}).get('name_en') if cat_id else None
            if cat_id and int(cat_id) == _WASTE_TO_ENERGY_CAT_ID:
                cat_en = 'Waste To Energy'   # one display name, whatever the DB row says
            gid = _row_group_id(row, report_mode)
            if gid not in group_names:
                gid = None
            out.append({
                'date': dt.astimezone(client_tz).date(),
                'kg': weight,
                'category_en': cat_en or 'Other',
                'main_material_en': (mm_names.get(int(mm_id)) or {}).get('name_en') if mm_id else '',
                'material_en': row[14] or '',
                'material_th': row[15] or '',
                'tx_id': row[2],
                'group_id': gid,
                'group_name': group_names.get(gid) if gid is not None else None,
            })
        return out

    cur_records = [r for r in to_records(cur_rows) if cur_start <= r['date'] <= cur_end]
    prev_records = [r for r in to_records(prev_rows) if prev_start <= r['date'] <= prev_end]

    # Buckets for the quantity chart / table, aligned between the two periods:
    # yearly → calendar months of the selected range; monthly → day numbers of the range.
    # Both stop at the clamped end, so a range running into the future has no empty columns.
    bucket_end = cur_end if cur_end >= from_date else to_date
    if compare_mode == 'yearly':
        bucket_keys = list(range(from_date.month, bucket_end.month + 1))
        key_of = lambda d: d.month
        bucket_label = lambda k, lang: (MONTHS_TH if lang == 'th' else MONTHS_EN)[k - 1]
    else:
        bucket_keys = list(range(from_date.day, bucket_end.day + 1))
        key_of = lambda d: d.day
        bucket_label = lambda k, lang: str(k)

    def side(records, start, end) -> Dict[str, Any]:
        material: Dict[str, float] = {}
        buckets = {k: 0.0 for k in bucket_keys}
        total = 0.0
        for r in records:
            material[r['category_en']] = material.get(r['category_en'], 0.0) + r['kg']
            k = key_of(r['date'])
            if k in buckets:
                buckets[k] += r['kg']
            total += r['kg']
        return {
            'from': start.isoformat(),
            'to': end.isoformat(),
            'label_th': range_label(start, end, 'th'),
            'label_en': range_label(start, end, 'en'),
            'year': start.year,
            'material': {k: round(v, 2) for k, v in sorted(material.items(), key=lambda kv: kv[1], reverse=True)},
            # Legacy key the month chart read ('Jan' → kg); day numbers in monthly mode.
            'month': {(MONTHS_EN[k - 1] if compare_mode == 'yearly' else str(k)): round(buckets[k], 2) for k in bucket_keys},
            'total_waste_kg': round(total, 2),
        }

    left = side(prev_records, prev_start, prev_end)
    right = side(cur_records, cur_start, cur_end)
    lb = left['month']
    rb = right['month']
    buckets_out = []
    for k in bucket_keys:
        key = MONTHS_EN[k - 1] if compare_mode == 'yearly' else str(k)
        lv, rv = lb.get(key, 0.0), rb.get(key, 0.0)
        buckets_out.append({
            'key': key,
            'label_th': bucket_label(k, 'th'),
            'label_en': bucket_label(k, 'en'),
            'left_kg': lv,
            'right_kg': rv,
            'change_kg': round(rv - lv, 2),
            'change_pct': round((rv - lv) / lv * 100.0, 2) if lv > 0 else None,
        })

    insights = build_report_insights(
        cur_records, prev_records, cur_start, cur_end, prev_start, prev_end,
        today_local, mode=report_mode, compare_mode=compare_mode,
    )

    # B5: keep what the advice engine saw (all metrics, every matched rule) so a like /
    # dislike on a card becomes a self-contained, comparable training sample.
    from .advice_feedback_service import save_snapshot, snapshot_filters
    scores_ = insights['scores']
    snapshot_id = save_snapshot(
        reports_service.db, organization_id,
        (current_user or {}).get('user_id') or (current_user or {}).get('id'),
        rules_version=scores_.get('rules_version') or '',
        report_mode=report_mode, compare_mode=compare_mode,
        periods={'cur_start': cur_start, 'cur_end': cur_end, 'prev_start': prev_start, 'prev_end': prev_end},
        filters=snapshot_filters(filters or {}),
        metrics=scores_.get('metrics') or {},
        labels=insights.get('txt') or {},
        evaluated=scores_.get('evaluated') or [],
    )

    return {
        'success': True,
        'mode': compare_mode,
        'compare_mode': compare_mode,
        'report_mode': report_mode,
        'clamped': cur_end < to_date,
        'left': left,
        'right': right,
        'buckets': buckets_out,
        'scores': insights['scores'],
        'insights_snapshot_id': snapshot_id,
        'message': 'Comparison report generated successfully'
    }

# ========== MAIN ROUTE HANDLER ==========

def handle_reports_routes(event: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all reports-related endpoints
    
    Routes:
    - GET /api/reports/overview - Overview report with key indicators
    - GET /api/reports/performance - Performance report with transaction records and org setup
    - GET /api/reports/materials - Material breakdown report
    - GET /api/reports/diversion - Waste diversion report
    - GET /api/reports/origins - List of origins for the organization
    """
    
    db_session = common_params.get('db_session')
    method = common_params.get('method', 'GET')
    query_params = common_params.get('query_params', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    
    try:
        # Initialize service
        reports_service = ReportsService(db_session)

        # B5: like / dislike + comment on advice cards (the only write route here)
        if path == '/api/reports/advice-feedback':
            from .advice_feedback_service import AdviceFeedbackService
            organization_id = _validate_organization_id(current_user)
            uid = current_user.get('user_id') or current_user.get('id')
            svc = AdviceFeedbackService(db_session)
            if method == 'GET':
                return {'items': svc.list_mine(int(uid), query_params.get('snapshot_id'),
                                               query_params.get('date_from'), query_params.get('date_to'))}
            if method in ('POST', 'PUT'):
                return svc.upsert(organization_id, int(uid), common_params.get('data') or {})
            raise APIException(f"Method {method} not supported", status_code=405, error_code="METHOD_NOT_ALLOWED")

        # Only handle GET requests
        if method != 'GET':
            raise APIException(
                f"Method {method} not supported. Only GET requests are available.",
                status_code=405,
                error_code="METHOD_NOT_ALLOWED"
            )
        
        # Validate organization ID for all routes
        organization_id = _validate_organization_id(current_user)
        
        # Route to appropriate handler
        # Determine timezone from query or current user (fallback Asia/Bangkok)
        tz_name = query_params.get('tz') or query_params.get('timezone') or current_user.get('timezone') or 'Asia/Bangkok'

        if path == '/api/reports/overview':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            return _handle_overview_report(reports_service, organization_id, filters, current_user)

        elif path == '/api/reports/performance':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            return _handle_performance_report(reports_service, organization_id, filters, current_user)
        
        elif path == '/api/reports/diversion':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            return _handle_diversion_report(reports_service, organization_id, filters, current_user)
        
        elif path == '/api/reports/filter/origins':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            # Remove origin/location filters - only use material filters for origins endpoint
            filters.pop('origin_ids', None)
            filters.pop('location_ids', None)
            filters.pop('filter_tag_ids', None)
            filters.pop('filter_tenant_ids', None)
            filters.pop('origin_combos', None)
            # Do not apply default YTD for filter endpoints; only use dates if explicitly provided
            has_date = any(k in query_params for k in ('date_from', 'date_to', 'datefrom', 'dateto'))
            if not has_date:
                filters.pop('date_from', None)
                filters.pop('date_to', None)
            current_user_id = current_user.get('user_id') or current_user.get('id')
            return reports_service.get_origin_by_organization(organization_id=organization_id, filters=filters, current_user_id=current_user_id)

        elif path == '/api/reports/filter/materials':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            # Remove material filters - only use origin filters for materials endpoint
            filters.pop('material_ids', None)
            # Do not apply default YTD for filter endpoints; only use dates if explicitly provided
            has_date = any(k in query_params for k in ('date_from', 'date_to', 'datefrom', 'dateto'))
            if not has_date:
                filters.pop('date_from', None)
                filters.pop('date_to', None)
            current_user_id = current_user.get('user_id') or current_user.get('id')
            return reports_service.get_material_by_organization(organization_id=organization_id, filters=filters, current_user_id=current_user_id)
        
        elif path == '/api/reports/comparison':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            return _handle_comparison_report(reports_service, organization_id, filters, current_user=current_user, client_timezone=tz_name)

        elif path == '/api/reports/materials':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            return _handle_materials_report(reports_service, organization_id, filters, current_user)

        elif path == '/api/reports/export/pdf':
            filters = _build_filters_from_query_params(query_params, timezone_name=tz_name)
            language = query_params.get('language', 'en') if query_params else 'en'
            return _handle_export_pdf_report(reports_service, organization_id, filters, current_user, language=language)
    
    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )

def _invoke_pdf_lambda(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke the PDF export Lambda with the aggregated payload.
    Returns a dict with at least {success: bool, pdf_base64?: str, filename?: str, error?: str}
    """
    fn_name = os.getenv("PDF_EXPORT_FUNCTION", "DEV-GEPPGenerateV3Report")
    client = boto3.client("lambda")
    resp = client.invoke(
        FunctionName=fn_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"data": payload}).encode("utf-8"),
    )
    raw = resp.get("Payload").read()
    try:
        out = json.loads(raw)
        # API Gateway proxy shape
        if isinstance(out, dict) and "statusCode" in out and "body" in out:
            return json.loads(out.get("body") or "{}")
        return out if isinstance(out, dict) else {"success": False, "error": "Unexpected Lambda response"}
    except Exception:
        return {"success": False, "error": "Invalid Lambda response"}

def _handle_export_pdf_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Dict[str, Any],
    language: str = 'en'
) -> Dict[str, Any]:
    """
    Aggregate data from all report handlers into a single structure
    compatible with scripts/generate_pdf_report.py.
    """
    # Validate date range for comparison and diversion reports
    date_from = filters.get('date_from')
    date_to = filters.get('date_to')
    
    if date_from and date_to:
        try:
            # Parse dates
            from_dt = _parse_datetime(date_from)
            to_dt = _parse_datetime(date_to)
            
            if from_dt and to_dt:
                # Ensure dates are timezone-aware
                if from_dt.tzinfo is None:
                    from_dt = from_dt.replace(tzinfo=timezone.utc)
                else:
                    from_dt = from_dt.astimezone(timezone.utc)
                if to_dt.tzinfo is None:
                    to_dt = to_dt.replace(tzinfo=timezone.utc)
                else:
                    to_dt = to_dt.astimezone(timezone.utc)
                
                # Convert to client timezone for validation
                export_tz = current_user.get('timezone') or 'Asia/Bangkok'
                try:
                    client_tz = ZoneInfo(export_tz)
                except Exception:
                    client_tz = ZoneInfo('UTC')
                
                from_local = from_dt.astimezone(client_tz)
                to_local = to_dt.astimezone(client_tz)
                
                from_date = from_local.date()
                to_date = to_local.date()
                
                # Validate period doesn't exceed 1 year
                delta_days = (to_date - from_date).days
                date_error = None
                if delta_days > 365:
                    date_error = 'Please select valid date range. The date range must be within a single year and not exceed 365 days'
                elif from_date.year != to_date.year:
                    # Check if dates are in the same calendar year
                    date_error = 'Please select valid date range. The date range must be within a single year and not exceed 365 days'
                
                if date_error:
                    # Set error flags to render error message in PDF
                    diversion = {'error': date_error}
                    comparison = {'error': date_error}
                else:
                    # Dates are valid, will fetch data below
                    diversion = None
                    comparison = None
            else:
                diversion = None
                comparison = None
        except Exception:
            # If validation fails, continue - let the handlers validate
            diversion = None
            comparison = None
    else:
        diversion = None
        comparison = None
    
    # 0) Report presentation settings: what the page sent, else the user's saved
    #    preferences (scheduled exports have no page), else the defaults.
    try:
        from ..users.user_preferences_service import UserPreferencesService
        _uid = (current_user or {}).get('id') or (current_user or {}).get('user_id')
        _prefs = UserPreferencesService(reports_service.db).get(_uid)['report_preferences'] if _uid else {}
    except Exception as e:  # preferences are a convenience; never fail an export over them
        logger.warning("[export] could not read report preferences: %s", e)
        _prefs = {}
    filters = dict(filters or {})
    filters.setdefault('report_mode', _prefs.get('mode', 'location'))
    filters.setdefault('overview_chart', _prefs.get('overview_chart', 'monthly'))
    filters.setdefault('compare_mode', _prefs.get('compare_mode', 'yearly'))
    filters.setdefault('overview_breakdown', _prefs.get('overview_breakdown', 'recycled'))
    report_mode = _report_mode(filters)

    # 1) Pull data from the existing handlers/services
    overview = _handle_overview_report(reports_service, organization_id, filters, current_user)
    performance = _handle_performance_report(reports_service, organization_id, filters, current_user)
    materials = _handle_materials_report(reports_service, organization_id, filters, current_user)

    # Impact figures read by title BEFORE the titles are translated below.
    _stats = (overview.get('overall_charts', {}) or {}).get('chart_stat_data', []) or []
    _stat_by_title = {st.get('title'): st.get('value') for st in _stats}
    _per_head = next((st for st in _stats if st.get('title') == 'Waste per Head'), {}) or {}
    overview_impact = {
        'recycled_kg': _stat_by_title.get('Total Recyclables') or 0,
        'trees': _stat_by_title.get('Number of Trees') or 0,
        'plastic_saved_kg': _stat_by_title.get('Plastic Saved') or 0,
        # None = nobody in scope has a headcount → "—", never a believable 0
        'waste_per_head': _per_head.get('value'),
        'headcount': _per_head.get('headcount'),
    }

    # Translate overview data based on language
    if language == 'th':
        _stat_title_map = {
            'Total Recyclables': 'วัสดุรีไซเคิลทั้งหมด',
            'Number of Trees': 'จำนวนต้นไม้',
            'Plastic Saved': 'พลาสติกที่นำกลับมาใช้ประโยชน์',
            'Waste per Head': 'ขยะต่อคน (กก.)',
        }
        for stat in (overview.get('overall_charts', {}) or {}).get('chart_stat_data', []):
            stat['title'] = _stat_title_map.get(stat.get('title'), stat.get('title'))

        # Build category name translation map (EN -> TH) for reuse
        wtp = overview.get('waste_type_proportions', [])
        cat_ids = {item.get('category_id') for item in wtp if item.get('category_id')} if wtp else set()
        # Also collect category IDs from performance metrics
        from GEPPPlatform.models.cores.references import MaterialCategory as _MC
        _all_cats = {}
        try:
            _cat_rows = reports_service.db.query(_MC.name_en, _MC.name_th).all()
            _all_cats = {r.name_en: (r.name_th or r.name_en) for r in _cat_rows if r.name_en}
        except Exception:
            pass

        # Translate waste_type_proportions category names for DISPLAY, but keep the English
        # name as `category_name_en` so the PDF can still resolve the pie color (MATERIAL_COLORS
        # is keyed by English). Without this, every TH row missed the palette → all slices blue.
        if wtp:
            for item in wtp:
                en_name = item.get('category_name', '')
                item['category_name_en'] = en_name
                if en_name in _all_cats:
                    item['category_name'] = _all_cats[en_name]

        # Note: performance metrics keys are kept in English because the PDF
        # code looks up specific keys like "General Waste", "Recyclable Waste".
        # Translation of metric labels happens at display time in pdf_export.py.
    
    # Get diversion and comparison data if not already set with error
    if diversion is None:
        try:
            diversion = _handle_diversion_report(reports_service, organization_id, filters, current_user)
        except ValidationException as e:
            diversion = {'error': 'Please select valid date range. The date range must be within a single year and not exceed 365 days'}
    
    export_tz = current_user.get('timezone') or 'Asia/Bangkok'
    if comparison is None or filters.get('compare_mode') == 'monthly':
        try:
            comparison = _handle_comparison_report(reports_service, organization_id, filters, current_user=current_user, client_timezone=export_tz)
        except ValidationException as e:
            # The export still goes out: the comparison pages explain that the range can't be
            # compared and suggest one that can (the other pages use the full range as usual).
            if filters.get('compare_mode') == 'monthly':
                comparison = {'error': ('โหมดเปรียบเทียบรายเดือน: กรุณาเลือกช่วงวันที่ภายในเดือนเดียวกัน'
                                        if language == 'th' else
                                        'Monthly comparison: please select a date range within one month')}
            else:
                comparison = {'error': 'Please select valid date range. The date range must be within a single year and not exceed 365 days'}
    if comparison.get('error') and not comparison.get('out_of_range'):
        # Whichever check rejected the range (the early year check above or the handler's
        # own), the comparison pages explain it and suggest a range that can be compared.
        comparison['out_of_range'] = _comparison_out_of_range(filters, export_tz)

    # 2) Format display dates like "01 Jan 2025" in client timezone
    _TH_MONTHS_SHORT = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

    def _local_dt(iso_str: Optional[str], tz_name: Optional[str]):
        dt = _parse_datetime(iso_str)
        if not dt:
            return None
        try:
            return dt.astimezone(ZoneInfo(tz_name or current_user.get('timezone') or 'Asia/Bangkok'))
        except Exception:
            return dt

    def _fmt_display_date_tz(iso_str: Optional[str], tz_name: Optional[str], with_time: bool = False) -> str:
        local_dt = _local_dt(iso_str, tz_name)
        if local_dt is None:
            return str(iso_str or "")
        try:
            if language == 'th':
                th_month = _TH_MONTHS_SHORT[local_dt.month - 1]
                be_year = local_dt.year + 543
                out = f"{local_dt.day:02d} {th_month} {be_year}"
            else:
                out = local_dt.strftime("%d %b %Y")
            return f"{out} {local_dt.strftime('%H:%M')}" if with_time else out
        except Exception:
            return local_dt.isoformat()

    client_tz_name = (current_user.get('timezone') or 'Asia/Bangkok')
    # A time of day is shown only when the user narrowed the range with one (the time
    # filter); whole-day ranges (00:00:00 → 23:59:59) keep the date-only header.
    _lf = _local_dt(filters.get('date_from'), client_tz_name)
    _lt = _local_dt(filters.get('date_to'), client_tz_name)
    _show_time = bool(
        _lf and _lt and ((_lf.hour, _lf.minute) != (0, 0) or (_lt.hour, _lt.minute) != (23, 59))
    )
    date_from_disp = _fmt_display_date_tz(filters.get('date_from'), client_tz_name, _show_time)
    date_to_disp = _fmt_display_date_tz(filters.get('date_to'), client_tz_name, _show_time)

    # 3) Resolve display user name from UserLocation (by current user id)
    def _display_user_name_from_db(user: Dict[str, Any]) -> str:
        try:
            user_id = user.get('id') or user.get('user_id') or user.get('uid')
            if user_id:
                row = reports_service.db.query(UserLocation).get(int(user_id))
                if row:
                    if language == 'th':
                        name_keys = ('display_name', 'name_th', 'name_en', 'username', 'email')
                    else:
                        name_keys = ('display_name', 'name_en', 'name_th', 'username', 'email')
                    for key in name_keys:
                        val = getattr(row, key, None)
                        if isinstance(val, str) and val.strip():
                            return val.strip()
        except Exception:
            pass

    user_display = _display_user_name_from_db(current_user or {})
    # Resolve profile image URL from UserLocation for header avatar
    def _profile_image_url_from_db(user: Dict[str, Any]) -> Optional[str]:
        try:
            user_id = user.get('id') or user.get('user_id') or user.get('uid')
            if user_id:
                row = reports_service.db.query(UserLocation).get(int(user_id))
                if row:
                    url = getattr(row, 'profile_image_url', None)
                    if isinstance(url, str) and url.strip():
                        return url.strip()
        except Exception:
            pass
        return None
    profile_img_url = _profile_image_url_from_db(current_user or {})
    # Generate a viewable URL (presigned if S3) for the profile image
    profile_img_view_url = None
    try:
        if profile_img_url:
            org_id = current_user.get('organization_id')
            user_id = current_user.get('id') or current_user.get('user_id') or current_user.get('uid')
            if org_id and user_id:
                try:
                    presigner = TransactionPresignedUrlService()
                    resp = presigner.get_transaction_file_view_presigned_urls(
                        file_urls=[profile_img_url],
                        organization_id=int(org_id),
                        user_id=int(user_id),
                        expiration_seconds=3600,
                        db=reports_service.db
                    )
                    if isinstance(resp, dict) and resp.get('success') and resp.get('presigned_urls'):
                        profile_img_view_url = resp['presigned_urls'][0].get('view_url') or profile_img_url
                    else:
                        profile_img_view_url = profile_img_url
                except Exception:
                    profile_img_view_url = profile_img_url
            else:
                profile_img_view_url = profile_img_url
    except Exception:
        profile_img_view_url = profile_img_url

    # 4) Resolve location names from the location filter; fallback to "all".
    # The dashboard sends the location filter as `location_ids` (branch/building/floor/room);
    # legacy callers use `origin_ids`. Consider BOTH, and resolve any level's name directly from
    # user_locations (get_origin_by_organization only covers leaf origins, so it would miss a
    # selected branch/building). Reading only origin_ids here was why the header showed "all"
    # even when the dashboard was filtered by a location.
    def _resolve_locations_from_filters(_filters: Dict[str, Any]) -> list[str] | str:
        _all_text = 'ทั้งหมด' if language == 'th' else 'all'
        raw_ids = list(_filters.get('origin_ids') or []) + list(_filters.get('location_ids') or [])
        seen: set = set()
        sel_ids = []
        for i in raw_ids:
            if i is not None and i not in seen:
                seen.add(i)
                sel_ids.append(i)
        if not sel_ids:
            return _all_text
        try:
            rows = reports_service.db.query(
                UserLocation.id, UserLocation.display_name,
                UserLocation.name_th, UserLocation.name_en,
            ).filter(UserLocation.id.in_(sel_ids)).all()
            name_map = {}
            for r in rows:
                name_map[r.id] = (r.display_name
                                  or (r.name_th if language == 'th' else r.name_en)
                                  or r.name_en or r.name_th or f"Location {r.id}")
            names = [name_map.get(i, f"Location {i}") for i in sel_ids]
            names = [n for n in names if n]
            return names or _all_text
        except Exception:
            return _all_text

    location_disp = _resolve_locations_from_filters(filters or {})

    # 4b) Tenant line for the header: exactly the tenant filter the user had on the Reports
    # page (the page pre-selects it for a single-tenant member), so the PDF says what the
    # screen said.
    def _resolve_tenant_names(_filters: Dict[str, Any]) -> list[str]:
        ids = list(_filters.get('filter_tenant_ids') or [])
        if _filters.get('tenant_id') is not None:
            ids.append(_filters['tenant_id'])
        if not ids:
            return []
        names = _fetch_group_names(reports_service.db, 'tenant', set(ids))
        return [names[i] for i in dict.fromkeys(ids) if names.get(i)]

    tenant_disp = _resolve_tenant_names(filters or {})

    # 5) Map materials handler keys to the generator's expected keys
    main_materials_data = {
        # keep original typo 'porportions' to match generator
        'porportions': (materials.get('main_material') or {}).get('porportions', []),
        'total_waste': (materials.get('main_material') or {}).get('total_waste', 0.0),
    }
    raw_grouped = (materials.get('sub_material') or {}).get('porportions_grouped', {})
    # Translate grouped keys (main material names) when language is Thai
    if language == 'th' and raw_grouped:
        main_mat_ids = set()
        for props in (materials.get('main_material') or {}).get('porportions', []):
            mid = props.get('main_material_id')
            if mid is not None:
                main_mat_ids.add(mid)
        mm_bilingual = _fetch_main_material_names_bilingual(reports_service.db, main_mat_ids)
        # Build EN->TH map from bilingual data
        _en_to_th = {}
        for mid, names in mm_bilingual.items():
            _en_to_th[names.get('name_en', '')] = names.get('name_th') or names.get('name_en', '')
        translated_grouped = {}
        for en_key, items in raw_grouped.items():
            th_key = _en_to_th.get(en_key, en_key)
            translated_grouped[th_key] = items
        raw_grouped = translated_grouped
    sub_materials_data = {
        'porportions': (materials.get('sub_material') or {}).get('porportions', []),
        'porportions_grouped': raw_grouped,
        'total_waste': (materials.get('sub_material') or {}).get('total_waste', 0.0),
    }

    # 6) Build the unified payload
    # Handle comparison data - check for errors first
    if comparison.get('error'):
        comparison_data = {
            'error': comparison.get('error'),
            'out_of_range': comparison.get('out_of_range'),
            'left': {},
            'right': {},
            'buckets': [],
            'compare_mode': filters.get('compare_mode', 'yearly'),
            'scores': {}
        }
    else:
        # Monthly: left = the month before the latest month with data, right = that month.
        _lbl = 'label_th' if language == 'th' else 'label_en'
        _left_dict = comparison.get('left', {}) or {}
        _right_dict = comparison.get('right', {}) or {}
        comparison_data = {
            'left': dict(_left_dict, period=_left_dict.get(_lbl, '')),
            'right': dict(_right_dict, period=_right_dict.get(_lbl, '')),
            'buckets': comparison.get('buckets', []) or [],
            'compare_mode': comparison.get('compare_mode', 'yearly'),
            'clamped': bool(comparison.get('clamped')),
            'scores': comparison.get('scores', {}),
        }

    # Handle diversion data - check for errors
    if diversion.get('error'):
        diversion_data = {
            'error': diversion.get('error'),
            'card_data': {},
            'sankey_data': [],
            'material_table': []
        }
    else:
        # Convert 4-column sankey [from_en, from_th, to, weight] to 3-column [from, to, weight]
        # based on language, for Lambda compatibility
        raw_sankey = diversion.get('sankey_data', [])
        if raw_sankey and len(raw_sankey) > 0 and len(raw_sankey[0]) >= 4:
            localized_sankey = [["From", "To", "Weight"]]
            for row in raw_sankey[1:] if raw_sankey[0][0] == "From" else raw_sankey:
                from_name = row[1] if language == 'th' else row[0]
                localized_sankey.append([from_name, row[2], row[3]])
        else:
            localized_sankey = raw_sankey

        # Localize material_table material names, status, and destination based on language
        raw_material_table = diversion.get('material_table', [])
        _status_map_th = {'Processing': 'กำลังดำเนินการ', 'Completed': 'เสร็จสิ้น'}
        _method_map_th = {
            'recycle': 'รีไซเคิล',
            'recycling own': 'รีไซเคิลเอง',
            'recycling (own)': 'รีไซเคิลเอง',
            'preparation for reuse': 'เตรียมเพื่อนำกลับมาใช้ใหม่',
            'other recover operation': 'การกู้คืนอื่นๆ',
            'composted by municipality': 'หมักปุ๋ยโดยเทศบาล',
            'municipality receive': 'เทศบาลรับ',
            'incineration without energy': 'เผาโดยไม่ผลิตพลังงาน',
            'incineration with energy': 'เผาเพื่อผลิตพลังงาน',
        }
        def _translate_method(m):
            if not m:
                return m
            return _method_map_th.get(m.lower().strip(), m)

        for mt_row in raw_material_table:
            lang_key = 'materials_th' if language == 'th' else 'materials_en'
            if mt_row.get(lang_key):
                mt_row['materials'] = mt_row[lang_key]
            if language == 'th':
                mt_row['status'] = _status_map_th.get(mt_row.get('status', ''), mt_row.get('status', ''))
                mt_row['destination'] = [_translate_method(d) for d in mt_row.get('destination', [])]

        # Also translate sankey "To" column (disposal methods)
        if language == 'th' and localized_sankey:
            for row in localized_sankey[1:] if localized_sankey[0][0] == "From" else localized_sankey:
                row[1] = _translate_method(row[1])

        diversion_data = {
            'card_data': diversion.get('card_data', {}),
            'sankey_data': localized_sankey,
            'material_table': raw_material_table,
            'materials_data': diversion.get('materials_data', []),
        }

    # Translated labels — SINGLE SOURCE in report_i18n.py (shared with pdf_export.py).
    from .report_i18n import LABELS as _LABELS

    labels = _LABELS.get(language, _LABELS['en'])
    # Add category name translation map for comparison chart
    if language == 'th':
        # Strip " Waste" suffix for display, map to Thai name (also stripped)
        _cat_display = {}
        for en_name, th_name in _all_cats.items():
            _cat_display[en_name] = th_name.replace(' Waste', '') if th_name else en_name.replace(' Waste', '')
        labels['_category_map'] = _cat_display

    data: Dict[str, Any] = {
        # Language and pre-translated labels
        'language': language,
        'labels': labels,
        # Header data
        'users': user_display,
        'profile_img': profile_img_view_url,
        'location': location_disp,
        'tenants': tenant_disp,
        # Presentation settings (report mode, chart granularity, comparison mode)
        'report_mode': report_mode,
        'overview_chart': filters.get('overview_chart', 'monthly'),
        'overview_breakdown': filters.get('overview_breakdown', 'recycled'),
        'compare_mode': filters.get('compare_mode', 'yearly'),
        'date_from': date_from_disp,
        'date_to': date_to_disp,

        # Overview
        'overview_data': {
            'transactions_total': overview.get('transactions_total', 0),
            'transactions_approved': overview.get('transactions_approved', 0),
            'key_indicators': overview.get('key_indicators', {}),
            'top_recyclables': overview.get('top_recyclables', []),
            'overall_charts': overview.get('overall_charts', {}),
            'impact': overview_impact,
        },
        # Performance: location hierarchy, or one summary row whose `buildings` are the
        # tags/tenants in those modes (plus the flat group list for the table page).
        'performance_data': performance.get('data', []),
        'performance_groups': performance.get('groups', []),
        # Optional, not strictly required by renderer but present in example
        'waste_type_proportions': overview.get('waste_type_proportions', []),
        'material_summary': [],

        # Comparison
        'comparison_data': comparison_data,

        # Materials breakdown pages
        'main_materials_data': main_materials_data,
        'sub_materials_data': sub_materials_data,

        # Diversion (sankey + materials monthly table)
        'diversion_data': diversion_data,
    }
    # Generate PDF via Lambda hub (routes to reports export function)
    from ..pdf_export_hub import generate_pdf_via_lambda
    return generate_pdf_via_lambda(data, export_type="reports", default_filename_prefix="report")
