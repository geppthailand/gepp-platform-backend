"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

from typing import Dict, Any, Optional, Tuple
import csv
import os
import json
import ast
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import boto3

from .reports_service import ReportsService
from ..transactions.presigned_url_service import TransactionPresignedUrlService
from ....exceptions import APIException, ValidationException, NotFoundException
from GEPPPlatform.models.cores.references import MainMaterial, MaterialCategory
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.transactions.transactions import TransactionStatus

# ========== HELPER FUNCTIONS ==========

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

    # Clamp date range constraints globally:
    # - date_to must not be in the future
    # - date range must not exceed 3 years (by day count)
    try:
        MAX_DAYS = 365 * 3
        now_utc = datetime.now(timezone.utc)
        end_of_today = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)

        dt_from = _parse_datetime(filters.get('date_from')) if filters.get('date_from') else None
        dt_to = _parse_datetime(filters.get('date_to')) if filters.get('date_to') else None

        # If only date_from is provided, set date_to to today (clamped later)
        if dt_from and not dt_to:
            dt_to = end_of_today
            filters['date_to'] = dt_to.isoformat()

        # If only date_to is provided, compute date_from as at most 3 years before
        if dt_to and not dt_from:
            if dt_to > end_of_today:
                dt_to = end_of_today
                filters['date_to'] = dt_to.isoformat()
            dt_from = dt_to - timedelta(days=MAX_DAYS)
            filters['date_from'] = dt_from.isoformat()

        # Clamp date_to to today if provided
        if dt_to and dt_to > end_of_today:
            dt_to = end_of_today
            filters['date_to'] = dt_to.isoformat()

        # Enforce max window if both bounds present
        if dt_from and dt_to:
            delta_days = (dt_to - dt_from).days
            if delta_days > MAX_DAYS:
                dt_from = dt_to - timedelta(days=MAX_DAYS)
                filters['date_from'] = dt_from.isoformat()
    except Exception:
        # Best-effort clamp; ignore parsing issues
        pass

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
    """Split 'Waste to Energy' out of General Waste in a material_map keyed by category name.

    Any record under category_id=4 whose main_material_id != GENERAL_WASTE main_material
    is reclassified as 'Waste to Energy'.

    Args:
        material_map: {category_name: weight} dict (mutated in place and returned)
        cat_mm_map: {(category_id, main_material_id): weight} tracking dict
        general_waste_mm_id: the main_material_id for GENERAL_WASTE (from DB or fallback)
        category_names: {category_id: name} mapping

    Returns:
        The updated material_map with Waste to Energy split out.
    """
    if general_waste_mm_id is None:
        # Fallback: pick the main_material with the most weight under category 4
        cat4_pairs = {mm_id: w for (c, mm_id), w in cat_mm_map.items() if c == _GENERAL_WASTE_CAT_ID}
        if cat4_pairs:
            general_waste_mm_id = max(cat4_pairs, key=cat4_pairs.get)
        else:
            return material_map

    wte_weight = 0.0
    for (cat_id, mm_id), weight in cat_mm_map.items():
        if cat_id == _GENERAL_WASTE_CAT_ID and mm_id != general_waste_mm_id and weight > 0:
            wte_weight += weight

    if wte_weight > 0:
        # Subtract from General Waste entry
        gw_name = category_names.get(_GENERAL_WASTE_CAT_ID, 'General Waste')
        if gw_name in material_map:
            material_map[gw_name] = material_map[gw_name] - wte_weight
            if material_map[gw_name] <= 0:
                del material_map[gw_name]
        # Add Waste to Energy entry
        material_map['Waste to Energy'] = material_map.get('Waste to Energy', 0.0) + wte_weight

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
        
        return {
            dest_id: (display_name or name_en or name_th or f"Location {dest_id}")
            for dest_id, display_name, name_en, name_th in destinations
        }
    except Exception:
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
        current_user_id=current_user_id
    )
    rows = result.get('rows', [])

    # Tuple indices from query:
    # 0: origin_quantity, 1: transaction_date, 2: created_transaction_id,
    # 3: origin_id, 4: status, 5: unit_weight, 6: calc_ghg,
    # 7: material_category_id, 8: material_main_material_id, 9: material_tags,
    # 10: origin_weight_kg, 11: record_category_id, 12: record_main_material_id

    # Aggregate in single pass
    ghg_reduction = 0.0
    total_waste = 0.0
    recyclable_waste = 0.0
    plastic_saved = 0.0
    recyclable_ghg_reduction = 0.0
    origin_waste_map = {}
    category_waste_map = {}
    cat_mm_waste_map = {}   # (cat_id, main_mat_id) -> weight for split-out detection
    month_totals_by_year = {}
    tx_ids = set()
    tx_approved = set()

    for row in rows:
        origin_qty = float(row[0] or 0)
        tx_date = row[1]
        tx_id = row[2]
        origin_id = row[3]
        status = row[4]
        unit_weight = float(row[5] or 0)
        calc_ghg = float(row[6] or 0)
        origin_weight_kg = float(row[10] or 0)

        # Use Material category/main_material as primary source (matches old reportUtils logic).
        # Fallback to TransactionRecord fields when Material is missing.
        cat_id = row[7] or row[11]           # material_category_id || record_category_id
        main_mat_id = row[8] or row[12]      # material_main_material_id || record_main_material_id

        # Track transactions
        tx_ids.add(tx_id)
        if status == TransactionStatus.approved:
            tx_approved.add(tx_id)

        # Use origin_qty * unit_weight when Material exists, fallback to origin_weight_kg
        weight = origin_qty * unit_weight if unit_weight > 0 else origin_weight_kg
        record_ghg = weight * calc_ghg

        total_waste += weight
        ghg_reduction += record_ghg

        # Monthly aggregation
        if tx_date:
            try:
                dt = tx_date if isinstance(tx_date, datetime) else datetime.fromisoformat(str(tx_date))
                y, m = dt.year, dt.month
                if y not in month_totals_by_year:
                    month_totals_by_year[y] = {}
                month_totals_by_year[y][m] = month_totals_by_year[y].get(m, 0.0) + weight
            except Exception:
                pass

        # Plastic saved (main_material_id=1 AND category_id=1)
        if main_mat_id == 1 and cat_id == 1:
            plastic_saved += weight

        # Recyclable waste (category_id in {1, 3})
        if cat_id in (1, 3):
            recyclable_waste += weight
            recyclable_ghg_reduction += record_ghg
            if origin_id is not None:
                origin_waste_map[origin_id] = origin_waste_map.get(origin_id, 0.0) + weight

        # Category proportions
        if cat_id is not None:
            category_waste_map[cat_id] = category_waste_map.get(cat_id, 0.0) + weight
            if main_mat_id is not None:
                key = (cat_id, main_mat_id)
                cat_mm_waste_map[key] = cat_mm_waste_map.get(key, 0.0) + weight

    recycle_rate = ((recyclable_waste / total_waste) * 100) if total_waste > 0 else 0.0

    # Top 5 recyclable origins — fetch origin names with member filtering
    top_origin_ids = sorted(origin_waste_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_recyclables = []
    if top_origin_ids:
        try:
            origins_result = reports_service.get_origin_by_organization(organization_id=organization_id, current_user_id=current_user_id)
            origin_names_map = {}
            origin_path_map = {}
            for o in origins_result.get('data', []):
                oid = o.get('origin_id')
                if oid is not None:
                    if oid not in origin_names_map:
                        origin_names_map[oid] = o.get('display_name') or o.get('name_en') or o.get('name_th') or o.get('name')
                    if oid not in origin_path_map:
                        origin_path_map[oid] = o.get('path') or ''
        except Exception:
            origin_names_map = {}
            origin_path_map = {}
        top_recyclables = [
            {'origin_id': oid, 'origin_name': origin_names_map.get(oid), 'path': origin_path_map.get(oid, ''), 'total_waste': w}
            for oid, w in top_origin_ids
        ]

    # Chart data by year/month
    chart_data = {}
    for year in sorted(month_totals_by_year.keys()):
        monthly = month_totals_by_year[year]
        chart_data[str(year)] = [
            {'month': datetime(2000, m, 1).strftime('%b'), 'value': round(monthly[m], 2)}
            for m in sorted(monthly.keys())
        ]

    # Split "Waste to Energy" out of General Waste (category_id=4).
    # In the old DB, "Waste to Energy" was its own material_category. In the new DB, those
    # materials were merged under General Waste. We identify them by: any record under
    # category_id=4 whose main_material_id is NOT the "General Waste" main_material (GENERAL_WASTE).
    _general_waste_mm_id = _get_general_waste_mm_id(reports_service.db)

    # Fallback: if query fails, try to detect from data (most weight under cat=4)
    if _general_waste_mm_id is None:
        cat4_pairs = {mm_id: w for (c, mm_id), w in cat_mm_waste_map.items() if c == _GENERAL_WASTE_CAT_ID}
        if cat4_pairs:
            _general_waste_mm_id = max(cat4_pairs, key=cat4_pairs.get)

    # Accumulate waste-to-energy weight: everything under General Waste category
    # that does NOT belong to the "General Waste" main_material
    wte_weight = 0.0
    if _general_waste_mm_id is not None:
        for (cat_id, mm_id), weight in cat_mm_waste_map.items():
            if cat_id == _GENERAL_WASTE_CAT_ID and mm_id != _general_waste_mm_id and weight > 0:
                wte_weight += weight

    # Subtract waste-to-energy from General Waste category
    if wte_weight > 0:
        category_waste_map[_GENERAL_WASTE_CAT_ID] = category_waste_map.get(_GENERAL_WASTE_CAT_ID, 0.0) - wte_weight

    # Remove zero/negative category entries
    category_waste_map = {k: v for k, v in category_waste_map.items() if v > 0}

    # Category proportions
    category_names_map = _fetch_category_names(reports_service.db, set(category_waste_map.keys()))
    waste_type_proportions = [
        {
            'category_id': cid,
            'category_name': category_names_map.get(cid, f"Category {cid}"),
            'total_waste': total,
            'proportion_percent': (total / total_waste * 100) if total_waste > 0 else 0.0,
        }
        for cid, total in category_waste_map.items()
    ]
    # Add "Waste to Energy" as a separate entry if it has weight
    if wte_weight > 0:
        waste_type_proportions.append({
            'category_id': None,
            'category_name': 'Waste to Energy',
            'total_waste': wte_weight,
            'proportion_percent': (wte_weight / total_waste * 100) if total_waste > 0 else 0.0,
        })
    waste_type_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

    return {
        'transactions_total': len(tx_ids),
        'transactions_approved': len(tx_approved),
        'key_indicators': {
            'total_waste': total_waste,
            'recycle_rate': recycle_rate,
            'ghg_reduction': ghg_reduction,
        },
        'top_recyclables': top_recyclables,
        'overall_charts': {
            'chart_stat_data': [
                {'title': 'Total Recyclables', 'value': recyclable_waste},
                {'title': 'Number of Trees', 'value': (recyclable_ghg_reduction / 9.5 * 100) if recyclable_ghg_reduction > 0 else 0.0},
                {'title': 'Plastic Saved', 'value': plastic_saved},
            ],
            'chart_data': chart_data
        },
        'waste_type_proportions': waste_type_proportions,
        'material_summary': []
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

    # Single pass: aggregate by main material AND sub material
    main_material_agg_map: Dict[int, Dict[str, float]] = {}
    sub_material_agg_map: Dict[int, Dict[str, Any]] = {}
    total_waste_main = 0.0
    sub_total_waste = 0.0

    for row in rows:
        origin_qty = float(row[0] or 0)
        status = row[4]
        unit_weight = float(row[5] or 0)
        calc_ghg = float(row[6] or 0)
        origin_weight_kg = float(row[10] or 0)
        main_id = row[8] or row[12]  # mat_main_material_id || record_main_material_id
        material_id = row[13]
        mat_name_en = row[14]
        mat_name_th = row[15]

        if status == TransactionStatus.rejected:
            continue

        weight = origin_qty * unit_weight if unit_weight > 0 else origin_weight_kg
        ghg = weight * calc_ghg

        # Aggregate by main material
        if main_id is not None:
            try:
                main_id_int = int(main_id)
            except Exception:
                continue
            total_waste_main += weight
            if main_id_int not in main_material_agg_map:
                main_material_agg_map[main_id_int] = {'total_waste': 0.0, 'ghg_reduction': 0.0}
            main_material_agg_map[main_id_int]['total_waste'] += weight
            main_material_agg_map[main_id_int]['ghg_reduction'] += ghg

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
                        'main_material_id': main_id_int,
                        'total_waste': 0.0,
                        'ghg_reduction': 0.0,
                    }
                sub_material_agg_map[mat_id_int]['total_waste'] += weight
                sub_material_agg_map[mat_id_int]['ghg_reduction'] += ghg

    # Fetch main material names
    name_map = _fetch_main_material_names(reports_service.db, set(main_material_agg_map.keys()))

    # Build proportions for main materials
    proportions = [
        {
            'main_material_id': mid,
            'main_material_name': name_map.get(mid),
            'total_waste': agg['total_waste'],
            'ghg_reduction': agg['ghg_reduction'],
            'proportion_percent': (agg['total_waste'] / total_waste_main * 100) if total_waste_main > 0 else 0.0,
        }
        for mid, agg in sorted(
            main_material_agg_map.items(),
            key=lambda kv: kv[1]['total_waste'],
            reverse=True
        )
    ]

    # Build sub proportions
    sub_proportions = []
    for item in sub_material_agg_map.values():
        item['proportion_percent'] = (item['total_waste'] / sub_total_waste * 100) if sub_total_waste > 0 else 0.0
        sub_proportions.append(item)
    sub_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

    # Group sub materials by main material name
    grouped_by_main: Dict[str, list] = {}
    for item in sub_proportions:
        main_id = item.get('main_material_id')
        main_name = name_map.get(main_id) if main_id is not None else None
        key_name = main_name or f"Material {main_id}" if main_id is not None else "Unknown"
        if key_name not in grouped_by_main:
            grouped_by_main[key_name] = []
        grouped_by_main[key_name].append({
            'material_id': item.get('material_id'),
            'material_name': item.get('material_name'),
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
    """Handle /api/reports/diversion endpoint — optimized single-query path"""

    current_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    # Use optimized single-query path (returns lightweight tuples)
    result = reports_service.get_overview_data(
        organization_id=organization_id,
        filters=filters if filters else None,
        current_user_id=current_user_id
    )
    rows = result.get('rows', [])

    # Tuple indices from get_overview_data:
    # 0: origin_quantity, 1: transaction_date, 2: created_transaction_id,
    # 3: origin_id, 4: txn_status, 5: unit_weight, 6: calc_ghg,
    # 7: mat_category_id, 8: mat_main_material_id, 9: material_tags,
    # 10: origin_weight_kg, 11: record_category_id, 12: record_main_material_id,
    # 13: material_id, 14: material_name_en, 15: material_name_th,
    # 16: disposal_method, 17: record_status

    unique_origins = set()
    transaction_map: Dict[int, Dict] = {}
    sankey_map: Dict[tuple, float] = {}
    material_table_map: Dict[int, Dict] = {}
    main_material_ids: set = set()
    category_ids: set = set()
    category_to_main_map: Dict[int, set] = {}

    for row in rows:
        origin_qty = float(row[0] or 0)
        txn_date = row[1]
        txn_id = row[2]
        origin_id = row[3]
        unit_weight = float(row[5] or 0)
        origin_weight_kg = float(row[10] or 0)
        cat_id = row[7] or row[11]
        mm_id = row[8] or row[12]
        disposal_method = (row[16] or '').strip() or None
        record_status = (row[17] or '').lower()

        # Weight: prefer qty * unit_weight, fall back to origin_weight_kg
        weight = origin_qty * unit_weight if unit_weight > 0 else origin_weight_kg
        if weight <= 0 and origin_weight_kg > 0:
            weight = origin_weight_kg

        # Track category → main_material mapping
        if cat_id is not None:
            try:
                cid_int = int(cat_id)
                category_ids.add(cid_int)
                if mm_id is not None:
                    mm_id_int = int(mm_id)
                    if cid_int not in category_to_main_map:
                        category_to_main_map[cid_int] = set()
                    category_to_main_map[cid_int].add(mm_id_int)
            except Exception:
                pass

        # Track unique origins
        if origin_id is not None:
            unique_origins.add(origin_id)

        # Group by transaction for completion tracking
        if txn_id is not None:
            if txn_id not in transaction_map:
                transaction_map[txn_id] = {'records': [], 'total_weight': 0.0}
            transaction_map[txn_id]['records'].append({'status': record_status, 'weight': weight})
            transaction_map[txn_id]['total_weight'] += weight

        # Resolve main_material_id as int
        main_material_id = None
        if mm_id is not None:
            try:
                main_material_id = int(mm_id)
            except Exception:
                pass

        # Build sankey data (MainMaterial → DisposalMethod flows)
        if main_material_id is not None and disposal_method:
            main_material_ids.add(main_material_id)
            key = (main_material_id, disposal_method)
            sankey_map[key] = sankey_map.get(key, 0.0) + weight

        # Build material_table data
        if main_material_id is not None:
            main_material_ids.add(main_material_id)

            if main_material_id not in material_table_map:
                material_table_map[main_material_id] = {
                    'monthly_data': {},
                    'transactions': {},
                    'destinations': set()
                }

            entry = material_table_map[main_material_id]

            # Aggregate by month
            if txn_date is not None:
                dt = txn_date if isinstance(txn_date, datetime) else _parse_datetime(str(txn_date))
                if dt:
                    month = dt.month
                    entry['monthly_data'][month] = entry['monthly_data'].get(month, 0.0) + weight

            # Track transaction statuses
            if txn_id is not None:
                if txn_id not in entry['transactions']:
                    entry['transactions'][txn_id] = []
                entry['transactions'][txn_id].append(record_status)

            # Track disposal methods
            if disposal_method:
                entry['destinations'].add(disposal_method)

    # Calculate completion metrics
    total_transactions, completed_transactions, complete_transfer = _check_transaction_completion(transaction_map)
    completed_rate = (completed_transactions / total_transactions * 100) if total_transactions > 0 else 0.0
    processing_transfer = 100.0 - completed_rate

    # Fetch main material names
    main_material_names = _fetch_main_material_names(reports_service.db, main_material_ids)

    # Build sankey_data array
    sankey_data = [["From", "To", "Weight"]]
    for (mm_id_key, method), w in sankey_map.items():
        from_name = main_material_names.get(mm_id_key, f"Material {mm_id_key}")
        to_name = method or "Unknown Disposal"
        sankey_data.append([from_name, to_name, w])

    # Build material_table
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    material_table = []

    for mid, entry in material_table_map.items():
        monthly_data = [
            {'month': month_names[m - 1], 'value': entry['monthly_data'][m]}
            for m in range(1, 13)
            if m in entry['monthly_data']
        ]

        all_completed = all(
            all(s == 'completed' for s in statuses)
            for statuses in entry['transactions'].values()
        )
        status = 'Completed' if all_completed else 'Processing'

        material_table.append({
            'key': mid,
            'materials': main_material_names.get(mid, f"Material {mid}"),
            'data': monthly_data,
            'status': status,
            'destination': list(entry['destinations'])
        })

    # Build materials_data: Dangerous (categories 5,6) vs Non-Dangerous
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
            {"id": mid, "name": main_material_names.get(mid, f"Material {mid}")}
            for mid in sorted(mm_ids)
        ]

    materials_data = [
        {"category_name": "Dangerous Waste", "main_materials": build_main_children(dangerous_main_ids)},
        {"category_name": "Non-Dangerous Waste", "main_materials": build_main_children(non_dangerous_main_ids)},
    ]

    return {
        "card_data": {
            "total_origin": len(unique_origins),
            "complete_transfer": complete_transfer,
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
    if not setup_data or not setup_data.get('root_nodes'):
        return {
            'success': True,
            'data': [],
            'message': 'No organization setup found'
        }

    root_nodes = setup_data.get('root_nodes', [])

    # Use optimized single-query path (same as overview)
    result = reports_service.get_overview_data(
        organization_id=organization_id,
        filters=filters if filters else None,
        current_user_id=current_user_id
    )
    rows = result.get('rows', [])

    # Collect all category IDs from rows and fetch names
    all_category_ids = set()
    # Build location ID → list of (origin_quantity, unit_weight, category_id, main_material_id) tuples
    location_records_map: Dict[int, list] = {}
    for row in rows:
        # Unpack all 18 columns from get_overview_data query
        (origin_qty, txn_date, txn_id, origin_id, status,
         unit_weight, calc_ghg, mat_category_id, mat_main_material_id, material_tags,
         origin_weight_kg, record_category_id, record_main_material_id,
         _mat_id, _mat_name_en, _mat_name_th,
         _disposal_method, _record_status) = row

        # Use Material category as primary source (matches old reportUtils logic)
        category_id = mat_category_id or record_category_id
        main_material_id = mat_main_material_id or record_main_material_id

        if status == TransactionStatus.rejected:
            continue
        if origin_id:
            if origin_id not in location_records_map:
                location_records_map[origin_id] = []
            location_records_map[origin_id].append((
                float(origin_qty or 0),
                float(unit_weight or 0),
                int(category_id) if category_id is not None else None,
                int(main_material_id) if main_material_id is not None else None
            ))
        if category_id is not None:
            try:
                all_category_ids.add(int(category_id))
            except Exception:
                pass

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

    # Helper to calculate metrics from lightweight tuples
    def calculate_metrics(records):
        """records: list of (origin_qty, unit_weight, category_id, main_material_id) tuples"""
        material_metrics: Dict[str, float] = {}
        cat_mm_map: Dict[Tuple[int, int], float] = {}
        total_weight = 0.0
        recyclable_weight = 0.0
        general_weight = 0.0

        for origin_qty, unit_weight, cat_id, mm_id in records:
            weight = origin_qty * unit_weight
            total_weight += weight

            if cat_id is not None:
                material_name = category_names.get(cat_id, f"Category {cat_id}")
                material_metrics[material_name] = material_metrics.get(material_name, 0.0) + weight
                # Track (cat_id, mm_id) for waste-to-energy splitting
                if mm_id is not None:
                    key = (cat_id, mm_id)
                    cat_mm_map[key] = cat_mm_map.get(key, 0.0) + weight

            if cat_id in (1, 3):
                recyclable_weight += weight
            if cat_id == _GENERAL_WASTE_CAT_ID:
                general_weight += weight

        # Split Waste to Energy out of General Waste
        _split_waste_to_energy(material_metrics, cat_mm_map, _perf_gw_mm_id, category_names)

        recycling_rate = (recyclable_weight / total_weight * 100) if total_weight > 0 else 0.0
        return {
            'metrics': {k: round(v, 2) for k, v in material_metrics.items() if v > 0},
            'totalWasteKg': round(total_weight, 2),
            'recyclingRatePercent': round(recycling_rate, 2),
            'recyclable_weight': round(recyclable_weight, 2),
            'general_weight': round(general_weight, 2)
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
        start_index = max(0, 3 - total_depth)
        configs = []
        for i in range(total_depth + 1):
            seq_index = start_index + i
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
            if child_items and children_key:
                item[children_key] = child_items

            result.append(item)

        return result

    performance_data = build_hierarchy(root_nodes)

    return {
        'success': True,
        'data': performance_data,
        'message': 'Performance report generated successfully'
    }

def _handle_comparison_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any],
    current_user: Optional[Dict[str, Any]] = None,
    client_timezone: Optional[str] = None
) -> Dict[str, Any]:
    """Handle /api/reports/comparison endpoint
    
    Uses date_from and date_to from filters to define the period.
    Left side: same period but in the previous year (last_year)
    Right side: the selected period (date_from to date_to)
    The period will never exceed 1 year and will never cross years.
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
    
    # Validate period doesn't exceed 1 year
    delta_days = (to_date - from_date).days
    if delta_days > 365:
        raise ValidationException("Comparison period cannot exceed 1 year")
    
    # Check if dates are in the same calendar year (in client timezone)
    if from_date.year != to_date.year:
        raise ValidationException("Comparison period cannot cross years")
    
    # Calculate left period: same period but in the previous year
    # Handle leap year edge cases:
    #   - Feb 29 in leap year -> Feb 28 in non-leap year
    #   - Feb 28 (end of Feb in non-leap year) -> Feb 29 if previous year is leap year
    import calendar

    def subtract_year(dt: datetime, is_end_date: bool = False) -> datetime:
        prev_year = dt.year - 1
        if dt.month == 2 and dt.day == 29:
            # Current is leap year Feb 29 -> previous non-leap year Feb 28
            return dt.replace(year=prev_year, day=28)
        if is_end_date and dt.month == 2 and dt.day == 28 and not calendar.isleap(dt.year) and calendar.isleap(prev_year):
            # Current is non-leap year Feb 28 (end of Feb) -> previous leap year Feb 29
            return dt.replace(year=prev_year, day=29)
        return dt.replace(year=prev_year)

    left_from_dt = subtract_year(right_from_dt)
    left_to_dt = subtract_year(right_to_dt, is_end_date=True)
    
    # Ensure timezone is UTC for left dates
    if left_from_dt.tzinfo is None:
        left_from_dt = left_from_dt.replace(tzinfo=timezone.utc)
    else:
        left_from_dt = left_from_dt.astimezone(timezone.utc)
    if left_to_dt.tzinfo is None:
        left_to_dt = left_to_dt.replace(tzinfo=timezone.utc)
    else:
        left_to_dt = left_to_dt.astimezone(timezone.utc)
    
    # Convert back to ISO strings in consistent UTC format (+00:00)
    left_from = left_from_dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + '+00:00'
    left_to = left_to_dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + '+00:00'
    # Right dates should already be in UTC format from filters, but ensure consistency
    right_from = date_from
    right_to = date_to

    _comparison_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    def fetch_side_fast(side_date_from: str, side_date_to: str) -> Dict[str, Any]:
        """Fetch one side using the lightweight get_overview_data query."""
        side_filters: Dict[str, Any] = {
            'date_from': side_date_from,
            'date_to': side_date_to,
        }
        if filters.get('material_ids'):
            side_filters['material_ids'] = filters['material_ids']
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
        )

    left_result = fetch_side_fast(left_from, left_to)
    right_result = fetch_side_fast(right_from, right_to)

    # Look up GENERAL_WASTE main_material_id once for waste-to-energy splitting
    _gw_mm_id = _get_general_waste_mm_id(reports_service.db)

    def _month_labels_in_range(start_iso: Optional[str], end_iso: Optional[str]) -> Optional[list]:
        start_dt = _parse_datetime(start_iso)
        end_dt = _parse_datetime(end_iso)
        if not start_dt or not end_dt:
            return None
        labels = []
        y, m = start_dt.year, start_dt.month
        while (y < end_dt.year) or (y == end_dt.year and m <= end_dt.month):
            labels.append(datetime(2000, m, 1).strftime('%b'))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return labels

    def build_grouped_fast(result: Dict[str, Any], start_iso: Optional[str], end_iso: Optional[str]) -> Dict[str, Any]:
        """Aggregate lightweight tuples from get_overview_data into comparison grouped data."""
        rows = result.get('rows', [])

        material_map: Dict[str, float] = {}
        month_map: Dict[str, float] = {}
        cat_mm_map: Dict[Tuple[int, int], float] = {}
        total_waste = 0.0
        category_ids: set = set()

        # Single pass: aggregate weights and collect category IDs
        for row in rows:
            # Tuple: (origin_qty, txn_date, txn_id, origin_id, status,
            #         unit_weight, calc_ghg, mat_cat_id, mat_mm_id, material_tags,
            #         origin_weight_kg, rec_cat_id, rec_mm_id, material_id,
            #         material_name_en, material_name_th, disposal_method, record_status)
            origin_qty = float(row[0] or 0)
            txn_date = row[1]
            status = row[4]
            unit_weight = float(row[5] or 0)
            origin_weight_kg = float(row[10] or 0)
            cat_id = row[7] or row[11]
            mm_id = row[8] or row[12]

            if status == TransactionStatus.rejected:
                continue

            weight = origin_qty * unit_weight if unit_weight > 0 else origin_weight_kg
            if not txn_date:
                continue

            dt = txn_date if isinstance(txn_date, datetime) else _parse_datetime(str(txn_date))
            if not dt:
                continue

            if cat_id is not None:
                try:
                    cat_id_int = int(cat_id)
                except Exception:
                    continue
                category_ids.add(cat_id_int)

                month_label = datetime(2000, dt.month, 1).strftime('%b')
                total_waste += weight
                month_map[month_label] = month_map.get(month_label, 0.0) + weight

                # Will be resolved to name below
                material_map[cat_id_int] = material_map.get(cat_id_int, 0.0) + weight

                if mm_id is not None:
                    try:
                        key = (cat_id_int, int(mm_id))
                        cat_mm_map[key] = cat_mm_map.get(key, 0.0) + weight
                    except Exception:
                        pass

        # Fetch category names and resolve material_map keys to names
        category_names = _fetch_category_names(reports_service.db, category_ids)
        named_map: Dict[str, float] = {}
        for cid, w in material_map.items():
            name = category_names.get(cid, f"Category {cid}")
            named_map[name] = named_map.get(name, 0.0) + w

        # Split Waste to Energy out of General Waste
        _split_waste_to_energy(named_map, cat_mm_map, _gw_mm_id, category_names)

        # Order months chronologically
        ordered_month_map: Dict[str, float] = {}
        month_labels = _month_labels_in_range(start_iso, end_iso)
        if month_labels is None:
            for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']:
                if m in month_map:
                    ordered_month_map[m] = month_map[m]
        else:
            for m in month_labels:
                ordered_month_map[m] = month_map.get(m, 0.0)

        # Sort materials desc
        ordered_material_map: Dict[str, float] = dict(sorted(named_map.items(), key=lambda kv: kv[1], reverse=True))

        # Round values
        EPS = 1e-6
        def clamp_round(x: float) -> float:
            return 0.0 if -EPS < x < EPS else round(x, 2)

        ordered_material_map = {k: clamp_round(v) for k, v in ordered_material_map.items()}
        ordered_month_map = {k: clamp_round(v) for k, v in ordered_month_map.items()}
        total_waste = clamp_round(total_waste)

        return {
            'material': ordered_material_map,
            'month': ordered_month_map,
            'total_waste_kg': total_waste,
        }

    left_grouped = build_grouped_fast(left_result, left_from, left_to)
    right_grouped = build_grouped_fast(right_result, right_from, right_to)

    # === Compute comparison scores from CSV (c = current/right, l = last/left) ===
    def _sum_categories(material_map: Dict[str, float], patterns: list[str]) -> float:
        if not material_map:
            return 0.0
        total = 0.0
        for name, val in material_map.items():
            n = (name or "").lower()
            for p in patterns:
                if p in n:
                    total += float(val or 0)
                    break
        return total

    def _build_variables(left_map: Dict[str, float], right_map: Dict[str, float]) -> Dict[str, float]:
        # Define category match patterns (case-insensitive substrings)
        patterns = {
            'recyclable': ['recycl'],
            'general': ['general'],
            'hazardous': ['hazardous'],
            'bio_hazardous': ['bio-hazard', 'biohazard', 'bio_hazard'],
            'organic': ['organic'],
            'waste_to_energy': ['waste to energy', 'waste-to-energy', 'waste_to_energy'],
            'construction': ['construction'],
            'electronic': ['electronic', 'e-waste', 'ewaste']
        }
        # Ensure hazardous doesn't double-count bio-hazardous
        # We will subtract bio-hazardous portion from hazardous if both match
        def compute_side(side_map: Dict[str, float]) -> Dict[str, float]:
            vals: Dict[str, float] = {}
            for key, pats in patterns.items():
                vals[key] = _sum_categories(side_map, pats)
            # Adjust hazardous to exclude bio_hazardous if both were matched
            if vals['hazardous'] and vals['bio_hazardous']:
                # Try to exclude if names overlap; conservative approach keeps as-is to avoid over-subtraction
                pass
            return vals

        l_vals = compute_side(left_map or {})
        c_vals = compute_side(right_map or {})

        variables: Dict[str, float] = {}
        for k, v in l_vals.items():
            variables[f'l_{k}'] = float(v or 0)
        for k, v in c_vals.items():
            variables[f'c_{k}'] = float(v or 0)
        return variables

    def _safe_eval_formula(formula: str, variables: Dict[str, float]) -> float:
        # Allow only names, numbers, + - * / ( ) and unary +/-
        allowed_nodes = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.Name,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Load,
            ast.Call  # disallow; we'll block below
        )

        class SafeVisitor(ast.NodeVisitor):
            def visit(self, node):
                if not isinstance(node, allowed_nodes):
                    raise ValueError('Disallowed expression in formula')
                # Disallow any function calls explicitly
                if isinstance(node, ast.Call):
                    raise ValueError('Function calls are not allowed in formula')
                # Only permit variable names present in variables map
                if isinstance(node, ast.Name) and node.id not in variables:
                    # Treat unknown names as zero to make formulas resilient
                    # Alternatively, raise ValueError
                    pass
                self.generic_visit(node)

        try:
            tree = ast.parse(formula, mode='eval')
            SafeVisitor().visit(tree)
            code = compile(tree, '<formula>', 'eval')
            # Unknown names default to 0 via dict subclass
            class ZeroDict(dict):
                def __missing__(self, key):
                    return 0.0
            return float(eval(code, {"__builtins__": {}}, ZeroDict(variables)))
        except Exception:
            return 0.0

    def _load_scores_csv() -> list[Dict[str, Any]]:
        # Resolve CSV path relative to project root
        base_dir = os.path.dirname(__file__)  # .../GEPPPlatform/services/cores/reports
        csv_candidates = [
            os.path.normpath(os.path.join(base_dir, '../../../../GEPPCriteria/compairingScore.csv')),
            os.path.normpath(os.path.join(base_dir, '../../../GEPPCriteria/compairingScore.csv')),
            'GEPPCriteria/compairingScore.csv'
        ]
        path = None
        for p in csv_candidates:
            if os.path.exists(p):
                path = p
                break
        rows: list[Dict[str, Any]] = []
        if not path:
            return rows
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)
        except Exception:
            return []
        return rows

    variables = _build_variables(left_grouped.get('material'), right_grouped.get('material'))
    score_rows = _load_scores_csv()
    computed_scores: list[Dict[str, Any]] = []
    raw_computations: list[Dict[str, Any]] = []

    # Build a lookup from score_name -> set of material categories referenced in its formula
    def _extract_categories_from_formula(formula: str) -> set[str]:
        try:
            tree = ast.parse(formula or '0', mode='eval')
        except Exception:
            return set()
        categories: set[str] = set()
        allowed_keys = {
            'recyclable', 'general', 'hazardous', 'bio_hazardous',
            'organic', 'waste_to_energy', 'construction', 'electronic'
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id or ''
                # Expect variables like l_recyclable, c_general, etc.
                if name.startswith('l_') or name.startswith('c_'):
                    base = name.split('_', 1)[1] if '_' in name else ''
                    if base in allowed_keys:
                        categories.add(base)
        return categories

    score_to_categories: Dict[str, set[str]] = {}

    # Evaluate all formulas first so we can normalize using dataset-aware scaling.
    for r in score_rows:
        try:
            score_id = int(r.get('id') or 0)
        except Exception:
            score_id = 0
        score_name = (r.get('score_name') or '').strip()
        description = (r.get('description') or '').strip()
        reason = (r.get('reason') or '').strip()
        formula = (r.get('formula') or '').strip()
        value = _safe_eval_formula(formula, variables)
        try:
            raw_value = float(value)
        except Exception:
            raw_value = 0.0
        raw_computations.append({
            'id': score_id,
            'score_name': score_name,
            'description': description,
            'formula': formula,
            'raw_value': raw_value,
            'reason': reason
        })
        if score_name:
            score_to_categories[score_name] = _extract_categories_from_formula(formula)

    finite_raw_values = [v['raw_value'] for v in raw_computations if math.isfinite(v['raw_value'])]
    min_raw_value = min(finite_raw_values) if finite_raw_values else 0.0
    max_raw_value = max(finite_raw_values) if finite_raw_values else 0.0

    # Hyperbolic/Logistic normalization with range awareness mapping to [0..10]
    def _normalize_score_to_ten(
        raw_value: float,
        min_value: float,
        max_value: float,
        *,
        method: str = 'tanh',
        steepness: float = 3.0
    ) -> float:
        if not math.isfinite(raw_value):
            return 5.0
        if not math.isfinite(min_value):
            min_value = raw_value
        if not math.isfinite(max_value):
            max_value = raw_value
        if max_value <= min_value:
            return 5.0

        span = max_value - min_value
        scaled = (raw_value - min_value) / span  # may exceed 0..1 if value is outside observed range
        centered = (scaled - 0.5) * 2.0
        factor = max(min(steepness * centered, 60.0), -60.0)

        if method == 'sigmoid':
            transformed = 1.0 / (1.0 + math.exp(-factor))
            normalized = transformed * 10.0
        else:
            transformed = math.tanh(factor)
            normalized = (transformed + 1.0) * 5.0

        return round(normalized, 2)

    for entry in raw_computations:
        raw_value = entry['raw_value']
        normalized_value = _normalize_score_to_ten(raw_value, min_raw_value, max_raw_value)
        computed_scores.append({
            'id': entry['id'],
            'score_name': entry['score_name'],
            'description': entry['description'],
            'formula': entry['formula'],
            # Use normalized 0..10 scale for 'value' (lower is worse)
            'value': normalized_value,
            # Preserve raw value for debugging/analytics
            'raw_value': round(float(raw_value), 2) if math.isfinite(raw_value) else 0.0,
            'reason': entry['reason']
        })

    # Prepare score values for recommendation evaluation
    # Use RAW values (0..1000) for conditions in recommendation CSVs
    score_values: Dict[str, float] = { (s.get('score_name') or '').strip(): float(s.get('raw_value') or 0.0) for s in computed_scores }

    # Evaluate recommendations from CSVs (opportunity, quickwin, riskAssessment)
    def _safe_eval_condition(expr: str, values: Dict[str, float]) -> bool:
        normalized = (expr or '').replace('AND', 'and').replace('OR', 'or')
        allowed_nodes = (
            ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
            ast.Name, ast.Load, ast.Constant, ast.Num,
            ast.And, ast.Or,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
            ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq
        )

        class SafeVisitor(ast.NodeVisitor):
            def visit(self, node):
                if not isinstance(node, allowed_nodes):
                    raise ValueError('Disallowed expression in condition')
                if isinstance(node, ast.Name) and node.id not in values:
                    # Unknown names default to 0 at eval-time
                    pass
                self.generic_visit(node)

        try:
            tree = ast.parse(normalized, mode='eval')
            SafeVisitor().visit(tree)
            code = compile(tree, '<condition>', 'eval')
            class ZeroDict(dict):
                def __missing__(self, key):
                    return 0.0
            return bool(eval(code, {"__builtins__": {}}, ZeroDict(values)))
        except Exception:
            return False

    def _load_recommendations_csv(file_name: str) -> list[Dict[str, Any]]:
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.normpath(os.path.join(base_dir, '../../../../GEPPCriteria/recommendations/' + file_name)),
            os.path.normpath(os.path.join(base_dir, '../../../GEPPCriteria/recommendations/' + file_name)),
            'GEPPCriteria/recommendations/' + file_name
        ]
        path = None
        for p in candidates:
            if os.path.exists(p):
                path = p
                break
        rows: list[Dict[str, Any]] = []
        if not path:
            return rows
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)
        except Exception:
            return []
        return rows

    def _evaluate_recommendations(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        # Compute a numeric urgency score for matched conditions, based on how far
        # actual values exceed their threshold(s) within the condition expression.
        # Higher score = more urgent.
        def _eval_numeric_node(node: ast.AST, values: Dict[str, float]) -> float:
            if isinstance(node, (ast.Num, ast.Constant)):
                try:
                    return float(getattr(node, 'n', getattr(node, 'value', 0.0)) or 0.0)
                except Exception:
                    return 0.0
            if isinstance(node, ast.Name):
                try:
                    return float(values.get(node.id, 0.0))
                except Exception:
                    return 0.0
            if isinstance(node, ast.UnaryOp):
                operand_val = _eval_numeric_node(node.operand, values)
                if isinstance(node.op, ast.USub):
                    return -operand_val
                if isinstance(node.op, ast.UAdd):
                    return +operand_val
                return 0.0
            if isinstance(node, ast.BinOp):
                left_val = _eval_numeric_node(node.left, values)
                right_val = _eval_numeric_node(node.right, values)
                if isinstance(node.op, ast.Add):
                    return left_val + right_val
                if isinstance(node.op, ast.Sub):
                    return left_val - right_val
                if isinstance(node.op, ast.Mult):
                    return left_val * right_val
                if isinstance(node.op, ast.Div):
                    try:
                        return left_val / right_val if right_val != 0 else 0.0
                    except Exception:
                        return 0.0
                return 0.0
            return 0.0

        def _compare_severity(left_val: float, op: ast.AST, right_val: float) -> float:
            # Distance beyond threshold when the comparison is true
            try:
                if isinstance(op, ast.Gt):
                    return max(0.0, left_val - right_val)
                if isinstance(op, ast.GtE):
                    return max(0.0, left_val - right_val)
                if isinstance(op, ast.Lt):
                    return max(0.0, right_val - left_val)
                if isinstance(op, ast.LtE):
                    return max(0.0, right_val - left_val)
                if isinstance(op, ast.Eq):
                    # Exact match implies no urgency
                    return 0.0
                if isinstance(op, ast.NotEq):
                    # Not equal matched; minimal urgency unit
                    return 1.0
            except Exception:
                return 0.0
            return 0.0

        def _severity_from_ast(node: ast.AST, values: Dict[str, float]) -> float:
            # AND: sum severities; OR: max severities
            if isinstance(node, ast.BoolOp):
                child_severities = [_severity_from_ast(v, values) for v in node.values]
                if isinstance(node.op, ast.And):
                    return sum(child_severities)
                if isinstance(node.op, ast.Or):
                    return max(child_severities) if child_severities else 0.0
                return 0.0
            if isinstance(node, ast.Compare):
                # Handle chained comparisons: a < b < c
                total = 0.0
                left_val = _eval_numeric_node(node.left, values)
                for op, comp in zip(node.ops, node.comparators):
                    right_val = _eval_numeric_node(comp, values)
                    total += _compare_severity(left_val, op, right_val)
                    left_val = right_val
                return total
            # Allow nested expressions
            if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Name, ast.Num, ast.Constant)):
                # Not a comparison by itself -> severity 0
                return 0.0
            return 0.0

        def _compute_condition_severity(expr: str, values: Dict[str, float]) -> float:
            try:
                normalized = (expr or '').replace('AND', 'and').replace('OR', 'or')
                tree = ast.parse(normalized, mode='eval')
                return float(_severity_from_ast(tree.body, values))
            except Exception:
                return 0.0

        results: list[Dict[str, Any]] = []
        for r in rows:
            criterior = (r.get('criterior') or '').strip()
            if not criterior:
                continue
            # Collect variables used in the criterior for transparency
            used_vars: set[str] = set()
            try:
                expr_tree = ast.parse(criterior.replace('AND', 'and').replace('OR', 'or'), mode='eval')
                for node in ast.walk(expr_tree):
                    if isinstance(node, ast.Name):
                        used_vars.add(node.id)
            except Exception:
                used_vars = set()

            var_values: Dict[str, float] = {name: float(score_values.get(name, 0.0)) for name in used_vars}
            matched = _safe_eval_condition(criterior, score_values)
            urgency_score = _compute_condition_severity(criterior, score_values) if matched else 0.0
            try:
                rid = int(r.get('id') or 0)
            except Exception:
                rid = 0
            # Determine which material categories are involved based on referenced scores in the criterior
            materials_used: list[str] = sorted({
                cat
                for var in used_vars
                for cat in (score_to_categories.get(var) or set())
            })
            results.append({
                'id': rid,
                'condition_name': (r.get('condition_name') or '').strip(),
                'criterior': criterior,
                'matched': bool(matched),
                'urgency_score': round(float(urgency_score), 2),
                'variables': var_values,
                'materials_used': materials_used,
                'risk_problems': (r.get('risk_problems') or '').strip(),
                'recommendation': (r.get('recommendation') or '').strip()
            })
        # Sort: matched first, then by urgency_score desc, stable otherwise
        results.sort(key=lambda x: (not x.get('matched', False), -float(x.get('urgency_score', 0.0))))
        return results

    opportunity_rows = _load_recommendations_csv('opportunity.csv')
    quickwin_rows = _load_recommendations_csv('quickwin.csv')
    risk_rows = _load_recommendations_csv('riskAssessment.csv')

    opportunities = _evaluate_recommendations(opportunity_rows)
    quickwins = _evaluate_recommendations(quickwin_rows)
    risks = _evaluate_recommendations(risk_rows)

    # Normalize urgency across categories so they are directly comparable
    def _normalize_global_urgency() -> None:
        # Optional category weights if needed in future customizations
        category_weights: Dict[str, float] = {
            'opportunities': 1.0,
            'quickwins': 1.0,
            'risks': 1.0
        }
        grouped = [
            ('opportunities', opportunities),
            ('quickwins', quickwins),
            ('risks', risks)
        ]
        # Compute weighted urgency (currently equal weights)
        for cat_name, items in grouped:
            weight = float(category_weights.get(cat_name, 1.0))
            for it in items:
                base = float(it.get('urgency_score', 0.0))
                it['weighted_urgency'] = base * weight if it.get('matched') else 0.0
        # Find global max among matched items for normalization
        try:
            global_max = max(
                (float(it.get('weighted_urgency', 0.0)) for cat, items in grouped for it in items if it.get('matched')),
                default=0.0
            )
        except Exception:
            global_max = 0.0
        # Assign normalized urgency [0..100] and priority bands
        for _, items in grouped:
            for it in items:
                wu = float(it.get('weighted_urgency', 0.0))
                norm = (wu / global_max * 100.0) if global_max > 0 else 0.0
                it['urgency_normalized'] = round(norm, 2)
                s = it['urgency_normalized']
                if s >= 80.0:
                    priority = 'high'
                elif s >= 50.0:
                    priority = 'medium'
                elif s >= 20.0:
                    priority = 'low'
                else:
                    priority = 'info'
                it['priority'] = priority
        # Re-sort each list by matched first, then normalized urgency desc
        for _, items in grouped:
            items.sort(key=lambda x: (not x.get('matched', False), -float(x.get('urgency_normalized', 0.0))))
            # Return only the top 2 items by urgency_normalized
            items[:] = items[:2]

    _normalize_global_urgency()

    return {
        'success': True,
        'left': left_grouped,
        'right': right_grouped,
        'scores': {
            'metrics': computed_scores,
            'opportunities': opportunities,
            'quickwins': quickwins,
            'risks': risks
        },
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
            # Remove origin filters - only use material filters for origins endpoint
            filters.pop('origin_ids', None)
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
            return _handle_export_pdf_report(reports_service, organization_id, filters, current_user)
    
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
    current_user: Dict[str, Any]
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
    
    # 1) Pull data from the existing handlers/services
    overview = _handle_overview_report(reports_service, organization_id, filters, current_user)
    performance = _handle_performance_report(reports_service, organization_id, filters, current_user)
    materials = _handle_materials_report(reports_service, organization_id, filters, current_user)
    
    # Get diversion and comparison data if not already set with error
    if diversion is None:
        try:
            diversion = _handle_diversion_report(reports_service, organization_id, filters, current_user)
        except ValidationException as e:
            diversion = {'error': 'Please select valid date range. The date range must be within a single year and not exceed 365 days'}
    
    export_tz = current_user.get('timezone') or 'Asia/Bangkok'
    if comparison is None:
        try:
            comparison = _handle_comparison_report(reports_service, organization_id, filters, current_user=current_user, client_timezone=export_tz)
        except ValidationException as e:
            comparison = {'error': 'Please select valid date range. The date range must be within a single year and not exceed 365 days'}

    # 2) Format display dates like "01 Jan 2025" in client timezone
    def _fmt_display_date_tz(iso_str: Optional[str], tz_name: Optional[str]) -> str:
        dt = _parse_datetime(iso_str)
        if not dt:
            return str(iso_str or "")
        try:
            # Determine client timezone (fallback Asia/Bangkok)
            tz = ZoneInfo(tz_name or current_user.get('timezone') or 'Asia/Bangkok')
            # Convert to client timezone for display
            local_dt = dt.astimezone(tz)
            return local_dt.strftime("%d %b %Y")
        except Exception:
            return dt.isoformat()

    client_tz_name = (current_user.get('timezone') or 'Asia/Bangkok')
    date_from_disp = _fmt_display_date_tz(filters.get('date_from'), client_tz_name)
    date_to_disp = _fmt_display_date_tz(filters.get('date_to'), client_tz_name)

    # 3) Resolve display user name from UserLocation (by current user id)
    def _display_user_name_from_db(user: Dict[str, Any]) -> str:
        try:
            user_id = user.get('id') or user.get('user_id') or user.get('uid')
            if user_id:
                row = reports_service.db.query(UserLocation).get(int(user_id))
                if row:
                    for key in ('display_name', 'name_en', 'name_th', 'username', 'email'):
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

    # 4) Resolve location names from origin_ids filter; fallback to "all"
    _current_user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')
    def _resolve_locations_from_filters(_filters: Dict[str, Any]) -> list[str] | str:
        origin_ids = _filters.get('origin_ids') or []
        if not origin_ids:
            return "all"
        try:
            origins_result = reports_service.get_origin_by_organization(organization_id=organization_id, current_user_id=_current_user_id)
            name_map = {}
            for o in origins_result.get('data', []):
                oid = o.get('origin_id')
                name = o.get('display_name') or o.get('name_en') or o.get('name_th') or o.get('name')
                if oid is not None and oid not in name_map:
                    name_map[oid] = name
            names = [name_map.get(oid, f"Location {oid}") for oid in origin_ids]
            names = [n for n in names if n]
            return names or "all"
        except Exception:
            return "all"

    location_disp = _resolve_locations_from_filters(filters or {})

    # 5) Map materials handler keys to the generator's expected keys
    main_materials_data = {
        # keep original typo 'porportions' to match generator
        'porportions': (materials.get('main_material') or {}).get('porportions', []),
        'total_waste': (materials.get('main_material') or {}).get('total_waste', 0.0),
    }
    sub_materials_data = {
        'porportions': (materials.get('sub_material') or {}).get('porportions', []),
        'porportions_grouped': (materials.get('sub_material') or {}).get('porportions_grouped', {}),
        'total_waste': (materials.get('sub_material') or {}).get('total_waste', 0.0),
    }

    # 6) Build the unified payload
    # Handle comparison data - check for errors first
    if comparison.get('error'):
        # If there's an error, create error structure for PDF rendering
        comparison_data = {
            'error': comparison.get('error'),
            'left': {},
            'right': {},
            'scores': {}
        }
    else:
        # Build comparison data with date ranges instead of periods
        _left_dict = comparison.get('left', {}) or {}
        _right_dict = comparison.get('right', {}) or {}
        
        # Calculate date ranges for left (last year) and right (current period)
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        
        # Format date ranges for display
        if date_from and date_to:
            right_from_dt = _parse_datetime(date_from)
            right_to_dt = _parse_datetime(date_to)
            
            if right_from_dt and right_to_dt:
                # Convert to client timezone for display
                export_tz = current_user.get('timezone') or 'Asia/Bangkok'
                try:
                    client_tz = ZoneInfo(export_tz)
                except Exception:
                    client_tz = ZoneInfo('UTC')
                
                # Right period dates (current)
                right_from_local = right_from_dt.astimezone(client_tz)
                right_to_local = right_to_dt.astimezone(client_tz)
                _right_period = f"{right_from_local.strftime('%d %b %Y')} - {right_to_local.strftime('%d %b %Y')}"
                
                # Left period dates (last year - same calendar dates)
                left_from_dt = right_from_dt.replace(year=right_from_dt.year - 1)
                left_to_dt = right_to_dt.replace(year=right_to_dt.year - 1)
                left_from_local = left_from_dt.astimezone(client_tz)
                left_to_local = left_to_dt.astimezone(client_tz)
                _left_period = f"{left_from_local.strftime('%d %b %Y')} - {left_to_local.strftime('%d %b %Y')}"
            else:
                _left_period = "Last Year"
                _right_period = "Current Period"
        else:
            _left_period = "Last Year"
            _right_period = "Current Period"
        
        _left_with_period = dict(_left_dict, period=_left_period)
        _right_with_period = dict(_right_dict, period=_right_period)
        comparison_data = {
            'left': _left_with_period,
            'right': _right_with_period,
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
        diversion_data = {
            'card_data': diversion.get('card_data', {}),
            'sankey_data': diversion.get('sankey_data', []),
            'material_table': diversion.get('material_table', []),
            'materials_data': diversion.get('materials_data', []),
        }

    data: Dict[str, Any] = {
        # Header data
        'users': user_display,
        'profile_img': profile_img_view_url,
        'location': location_disp,
        'date_from': date_from_disp,
        'date_to': date_to_disp,

        # Overview
        'overview_data': {
            'transactions_total': overview.get('transactions_total', 0),
            'transactions_approved': overview.get('transactions_approved', 0),
            'key_indicators': overview.get('key_indicators', {}),
            'top_recyclables': overview.get('top_recyclables', []),
            'overall_charts': overview.get('overall_charts', {}),
        },
        # Optional, not strictly required by renderer but present in example
        'waste_type_proportions': overview.get('waste_type_proportions', []),
        'material_summary': [],

        # Performance (hierarchical org performance list)
        'performance_data': performance.get('data', []),

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
