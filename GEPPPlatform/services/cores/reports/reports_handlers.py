"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .reports_service import ReportsService
from ....exceptions import APIException, ValidationException, NotFoundException
from GEPPPlatform.models.cores.references import MainMaterial, MaterialCategory
from GEPPPlatform.models.users.user_location import UserLocation


# ========== HELPER FUNCTIONS ==========

def _validate_organization_id(current_user: Dict[str, Any]) -> int:
    """Validate and extract organization_id from current_user"""
    organization_id = current_user.get('organization_id')
    if not organization_id:
        raise ValidationException("Organization ID is required")
    return organization_id


def _build_filters_from_query_params(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build filters dictionary from query parameters
    Supports comma-separated values for material_id and origin_id
    Example: ?material_id=1,2,3&origin_id=10,20
    
    Date handling:
    - date_from: Set to 00:00:00 of that day
    - date_to: Set to 23:59:59.999999 of that day
    """
    filters = {}
    
    # Handle material_id (comma-separated)
    if query_params.get('material_id'):
        material_ids_str = query_params['material_id']
        if ',' in material_ids_str:
            # Multiple IDs
            filters['material_ids'] = [int(mid.strip()) for mid in material_ids_str.split(',') if mid.strip()]
        else:
            # Single ID
            filters['material_ids'] = [int(material_ids_str)]
    
    # Handle origin_id (comma-separated)
    if query_params.get('origin_id'):
        origin_ids_str = query_params['origin_id']
        if ',' in origin_ids_str:
            # Multiple IDs
            filters['origin_ids'] = [int(oid.strip()) for oid in origin_ids_str.split(',') if oid.strip()]
        else:
            # Single ID
            filters['origin_ids'] = [int(origin_ids_str)]
    
    # Handle date filters with time adjustments (also accept 'datefrom'/'dateto')
    date_from_input = query_params.get('date_from') or query_params.get('datefrom')
    if date_from_input:
        date_from_str = date_from_input
        try:
            # Parse the date and set to start of day (00:00:00)
            if 'T' in date_from_str or ' ' in date_from_str:
                # Already has time component, parse as-is then reset to start of day
                dt = datetime.fromisoformat(date_from_str.replace('Z', '+00:00'))
            else:
                # Date only, parse and set to start of day
                dt = datetime.fromisoformat(date_from_str)
            
            # Set to start of day (00:00:00)
            filters['date_from'] = dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        except Exception:
            # Fallback to original value if parsing fails
            filters['date_from'] = date_from_str

    date_to_input = query_params.get('date_to') or query_params.get('dateto')
    if date_to_input:
        date_to_str = date_to_input
        try:
            # Parse the date and set to end of day (23:59:59.999999)
            if 'T' in date_to_str or ' ' in date_to_str:
                # Already has time component, parse as-is then reset to end of day
                dt = datetime.fromisoformat(date_to_str.replace('Z', '+00:00'))
            else:
                # Date only, parse and set to end of day
                dt = datetime.fromisoformat(date_to_str)
            
            # Set to end of day (23:59:59.999999)
            filters['date_to'] = dt.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        except Exception:
            # Fallback to original value if parsing fails
            filters['date_to'] = date_to_str

    # For Comparison path
    if query_params.get('period'):
        filters['period'] = query_params['period']
    if query_params.get('leftSelection'):
        filters['leftSelection'] = query_params['leftSelection']
    if query_params.get('rightSelection'):
        filters['rightSelection'] = query_params['rightSelection']
    
    # Default YTD if no explicit dates provided (first day of current year -> end of today)
    if not filters.get('date_from') and not filters.get('date_to'):
        now = datetime.utcnow()
        start_of_year = datetime(now.year, 1, 1, 0, 0, 0, 0)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        filters['date_from'] = start_of_year.isoformat()
        filters['date_to'] = end_of_today.isoformat()

    # Clamp date range constraints globally:
    # - date_to must not be in the future
    # - date range must not exceed 3 years (by day count)
    try:
        MAX_DAYS = 365 * 3
        now = datetime.utcnow()
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

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


def _compute_period_range(period: Optional[str], selection: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Compute ISO date_from/date_to from period and selection.
    Supports quarters (Q1-Q4), halves (H1/H2 or First/Second Half), and year (YYYY).
    If year not present in selection, defaults to current year.
    """
    if not period or not selection:
        return None, None

    sel_lower = selection.strip().lower()
    now = datetime.utcnow()
    # Extract year if present
    year = None
    for token in selection.replace('-', ' ').replace('_', ' ').split():
        if token.isdigit() and len(token) == 4:
            try:
                year = int(token)
                break
            except ValueError:
                pass
    if year is None:
        year = now.year

    def month_range(y: int, m_start: int, m_end: int) -> Tuple[str, str]:
        start = datetime(y, m_start, 1, 0, 0, 0, 0)
        # compute end as last microsecond of end month
        if m_end == 12:
            end_boundary = datetime(y + 1, 1, 1)
        else:
            end_boundary = datetime(y, m_end + 1, 1)
        end = end_boundary - timedelta(microseconds=1)
        return start.isoformat(), end.isoformat()

    p = (period or '').strip().lower()
    # Quarter
    if p in ('3m'):
        if 'q1' in sel_lower:
            return month_range(year, 1, 3)
        if 'q2' in sel_lower:
            return month_range(year, 4, 6)
        if 'q3' in sel_lower:
            return month_range(year, 7, 9)
        if 'q4' in sel_lower:
            return month_range(year, 10, 12)
        return None, None

    # Half-year
    if p in ('6m'):
        if 'first' in sel_lower or 'h1' in sel_lower:
            return month_range(year, 1, 6)
        if 'second' in sel_lower or 'h2' in sel_lower:
            return month_range(year, 7, 12)
        return None, None

    # Year
    if p in ('12m'):
        return month_range(year, 1, 12)

    # Unknown period
    return None, None


def _calculate_weight(record: Dict[str, Any], material: Dict[str, Any]) -> float:
    """Calculate weight from quantity and unit_weight"""
    quantity = float(record.get('origin_quantity') or 0)
    unit_weight = float(material.get('unit_weight') or 0)
    return quantity * unit_weight


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
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle /api/reports/overview endpoint"""
    
    # Get transaction records
    result = reports_service.get_transaction_records_by_organization(
        organization_id=organization_id,
        filters=filters if filters else None,
        report_type='overview'
    )
    
    # Initialize aggregation variables
    ghg_reduction = 0.0
    total_waste = 0.0
    recyclable_waste = 0.0
    plastic_saved = 0.0
    recyclable_ghg_reduction = 0.0
    origin_waste_map = {}
    category_waste_map = {}
    # Track monthly totals grouped by year
    month_totals_by_year = {}
    
    # Aggregate metrics from transaction records
    for record in result.get('data', []):
        # Skip rejected transactions
        if record.get('is_rejected'):
            continue
        
        material = record.get('material') or {}
        weight = _calculate_weight(record, material)
        calc_ghg = float(material.get('calc_ghg') or 0)
        record_ghg = weight * calc_ghg
        
        total_waste += weight
        ghg_reduction += record_ghg
        
        # Aggregate by month for chart_data
        dt = _parse_datetime(record.get('transaction_date'))
        if dt:
            y = dt.year
            m = dt.month
            if y not in month_totals_by_year:
                month_totals_by_year[y] = {}
            month_totals_by_year[y][m] = month_totals_by_year[y].get(m, 0.0) + weight
        
        # Plastic saved calculation
        if material.get('is_plastic'):
            plastic_saved += weight
        
        # Recyclable waste (category_id in {1, 3})
        cat_id = material.get('category_id') if material else record.get('category_id')
        try:
            cat_id_int = int(cat_id) if cat_id is not None else None
        except Exception:
            cat_id_int = None
        
        if cat_id_int in (1, 3):
            recyclable_waste += weight
            recyclable_ghg_reduction += record_ghg
            
            # Aggregate by origin for top recyclables
            origin_id = record.get('origin_id')
            if origin_id is not None:
                origin_waste_map[origin_id] = origin_waste_map.get(origin_id, 0.0) + weight
        
        # Aggregate by category for waste_type_proportions
        cat_id_raw = material.get('category_id') if material else record.get('category_id')
        try:
            cat_id = int(cat_id_raw) if cat_id_raw is not None else None
        except Exception:
            cat_id = None
        if cat_id is not None:
            if cat_id not in category_waste_map:
                category_waste_map[cat_id] = 0.0
            category_waste_map[cat_id] += weight
    
    # Calculate recycle rate
    recycle_rate = ((recyclable_waste / total_waste) * 100) if total_waste > 0 else 0.0
    
    # Build top recyclables (top 5 origins)
    top_origin_ids = sorted(origin_waste_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_recyclables = []
    
    if top_origin_ids:
        try:
            origins_result = reports_service.get_origin_by_organization(organization_id=organization_id)
            origin_names_map = {
                o.get('id'): (o.get('display_name') or o.get('name_en') or o.get('name_th'))
                for o in origins_result.get('data', [])
            }
        except Exception:
            origin_names_map = {}
        
        top_recyclables = [
            {
                'origin_id': oid,
                'origin_name': origin_names_map.get(oid),
                'total_waste': w
            }
            for oid, w in top_origin_ids
        ]
    
    # Build chart_data grouped by year with months sorted Jan..Dec
    chart_data = {}
    for year in sorted(month_totals_by_year.keys()):
        monthly = month_totals_by_year[year]
        chart_data[str(year)] = [
            {
                'month': datetime(2000, m, 1).strftime('%b'),
                'value': round(monthly[m], 2)
            }
            for m in sorted(monthly.keys())
        ]
    
    # Build waste_type_proportions by category
    category_names_map = _fetch_category_names(reports_service.db, set(category_waste_map.keys()))
    waste_type_proportions = []
    for cid, total in sorted(category_waste_map.items(), key=lambda kv: kv[1], reverse=True):
        proportion_percent = (total / total_waste * 100) if total_waste > 0 else 0.0
        waste_type_proportions.append({
            'category_id': cid,
            'category_name': category_names_map.get(cid, f"Category {cid}"),
            'total_waste': total,
            'proportion_percent': proportion_percent,
        })

    return {
        'transactions_total': result.get('transactions_total', 0),
        'transactions_approved': result.get('transactions_approved', 0),
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
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle /api/reports/materials endpoint"""
    
    # Get transaction records
    result = reports_service.get_transaction_records_by_organization(
        organization_id=organization_id,
        filters=filters if filters else None,
        report_type='materials'
    )
    
    # Aggregate by main material
    main_material_agg_map = {}
    total_waste_main = 0.0
    
    for record in result.get('data', []):
        material = record.get('material') or {}
        main_id = material.get('main_material_id') or record.get('main_material_id')
        if main_id is None:
            continue
        
        weight = _calculate_weight(record, material)
        calc_ghg = float(material.get('calc_ghg') or 0)
        ghg = weight * calc_ghg
        total_waste_main += weight
        
        if main_id not in main_material_agg_map:
            main_material_agg_map[main_id] = {'total_waste': 0.0, 'ghg_reduction': 0.0}
        
        main_material_agg_map[main_id]['total_waste'] += weight
        main_material_agg_map[main_id]['ghg_reduction'] += ghg
    
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
    
    # Aggregate by sub materials
    sub_material_agg_map = {}
    sub_total_waste = 0.0
    
    for record in result.get('data', []):
        if record.get('is_rejected'):
            continue
        
        material = record.get('material') or {}
        material_id = record.get('material_id') or material.get('id')
        main_id_for_sub = material.get('main_material_id') or record.get('main_material_id')
        if material_id is None:
            continue
        
        weight = _calculate_weight(record, material)
        calc_ghg = float(material.get('calc_ghg') or 0)
        ghg = weight * calc_ghg
        sub_total_waste += weight
        
        if material_id not in sub_material_agg_map:
            sub_material_agg_map[material_id] = {
                'material_id': material_id,
                'material_name': material.get('name_en') or material.get('name_th'),
                'main_material_id': main_id_for_sub,
                'total_waste': 0.0,
                'ghg_reduction': 0.0,
            }
        
        sub_material_agg_map[material_id]['total_waste'] += weight
        sub_material_agg_map[material_id]['ghg_reduction'] += ghg
    
    # Add proportion percent and sort
    sub_proportions = []
    for item in sub_material_agg_map.values():
        item['proportion_percent'] = (item['total_waste'] / sub_total_waste * 100) if sub_total_waste > 0 else 0.0
        sub_proportions.append(item)
    sub_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

    # Group sub materials by main material name for easier consumption
    grouped_by_main = {}
    for item in sub_proportions:
        main_id = item.get('main_material_id')
        main_name = name_map.get(main_id) if main_id is not None else None
        key_name = main_name or f"Material {main_id}" if main_id is not None else "Unknown"
        if key_name not in grouped_by_main:
            grouped_by_main[key_name] = []
        # Exclude main_material_id inside each sub-item for cleaner payload
        grouped_by_main[key_name].append({
            'material_id': item.get('material_id'),
            'material_name': item.get('material_name'),
            'total_waste': item.get('total_waste'),
            'ghg_reduction': item.get('ghg_reduction'),
            'proportion_percent': item.get('proportion_percent'),
        })
    # Sort each group's sub-materials by total_waste desc
    for k in grouped_by_main:
        grouped_by_main[k].sort(key=lambda x: x['total_waste'], reverse=True)
    
    return {
        'main_material': {
            'porportions': proportions,
            'total_waste': total_waste_main,
        },
        'sub_material': {
            'porportions': sub_proportions,  # flat list (kept for compatibility)
            'porportions_grouped': grouped_by_main,  # new grouped structure by main material name
            'total_waste': sub_total_waste,
        }
    }


def _handle_diversion_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle /api/reports/diversion endpoint"""
    
    # Get transaction records
    result = reports_service.get_transaction_records_by_organization(
        organization_id=organization_id,
        filters=filters if filters else None,
        report_type='diversion'
    )
    
    # Initialize tracking variables
    unique_origins = set()
    transaction_map = {}
    sankey_map = {}
    material_table_map = {}
    main_material_ids = set()
    # Track unique disposal methods (used instead of destination IDs)
    disposal_methods = set()
    
    # Process all records
    for record in result.get('data', []):
        material = record.get('material') or {}
        main_material_id = material.get('main_material_id') or record.get('main_material_id')
        
        # Track unique origins
        origin_id = record.get('origin_id')
        if origin_id is not None:
            unique_origins.add(origin_id)
        
        # Calculate weight
        weight = _calculate_weight(record, material)
        status = record.get('status', '').lower()
        transaction_id = record.get('created_transaction_id')
        
        # Group by transaction for completion tracking
        if transaction_id not in transaction_map:
            transaction_map[transaction_id] = {
                'records': [],
                'total_weight': 0.0
            }
        transaction_map[transaction_id]['records'].append({'status': status, 'weight': weight})
        transaction_map[transaction_id]['total_weight'] += weight
        
        # Use disposal_method directly from transaction_records (instead of destination in notes)
        disposal_method = (record.get('disposal_method') or '').strip() or None
        
        # Build sankey data (MainMaterial -> DisposalMethod flows)
        if main_material_id and disposal_method:
            main_material_ids.add(main_material_id)
            disposal_methods.add(disposal_method)
            key = (main_material_id, disposal_method)
            sankey_map[key] = sankey_map.get(key, 0.0) + weight
        
        # Build material_table data
        if main_material_id:
            main_material_ids.add(main_material_id)
            
            if main_material_id not in material_table_map:
                material_table_map[main_material_id] = {
                    'monthly_data': {},
                    'transactions': {},
                    'destinations': set()
                }
            
            material_entry = material_table_map[main_material_id]
            
            # Aggregate by month
            dt = _parse_datetime(record.get('transaction_date'))
            if dt:
                month = dt.month
                material_entry['monthly_data'][month] = material_entry['monthly_data'].get(month, 0.0) + weight
            
            # Track transaction statuses
            if transaction_id:
                if transaction_id not in material_entry['transactions']:
                    material_entry['transactions'][transaction_id] = []
                material_entry['transactions'][transaction_id].append(status)
            
            # Track disposal methods for this main material
            if disposal_method:
                disposal_methods.add(disposal_method)
                material_entry['destinations'].add(disposal_method)
    
    # Calculate completion metrics
    total_transactions, completed_transactions, complete_transfer = _check_transaction_completion(transaction_map)
    completed_rate = (completed_transactions / total_transactions * 100) if total_transactions > 0 else 0.0
    processing_transfer = 100.0 - completed_rate
    
    # Fetch main material names; disposal methods are already human-readable strings
    main_material_names = _fetch_main_material_names(reports_service.db, main_material_ids)
    
    # Build sankey_data array
    sankey_data = [["From", "To", "Weight"]]
    for (mm_id, method), weight in sankey_map.items():
        from_name = main_material_names.get(mm_id, f"Material {mm_id}")
        to_name = method or "Unknown Disposal"
        sankey_data.append([from_name, to_name, weight])
    
    # Build material_table
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    material_table = []
    
    for main_material_id, entry in material_table_map.items():
        # Build monthly data array (only months with data)
        monthly_data = [
            {'month': month_names[month_num - 1], 'value': entry['monthly_data'][month_num]}
            for month_num in range(1, 13)
            if month_num in entry['monthly_data']
        ]
        
        # Determine status (Completed if all transactions have all records completed)
        all_completed = all(
            all(status == 'completed' for status in statuses)
            for statuses in entry['transactions'].values()
        )
        status = 'Completed' if all_completed else 'Processing'
        
        # Get disposal methods list
        destination_names_list = [dm for dm in entry['destinations']]
        
        # Get material name
        material_name = main_material_names.get(main_material_id, f"Material {main_material_id}")
        
        material_table.append({
            'key': main_material_id,
            'materials': material_name,
            'data': monthly_data,
            'status': status,
            'destination': destination_names_list
        })
    
    return {
        "card_data": {
            "total_origin": len(unique_origins),
            "complete_transfer": complete_transfer,
            "processing_transfer": processing_transfer,
            "completed_rate": completed_rate,
        },
        "sankey_data": sankey_data,
        "material_table": material_table,
    }

def _handle_performance_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle /api/reports/performance endpoint"""
    
    # Get transaction records
    result = reports_service.get_transaction_records_by_organization(
        organization_id=organization_id,
        filters=filters if filters else None,
        report_type='performance'
    )
    
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
    transaction_records = result.get('data', [])
    
    # Build location ID to records mapping
    location_records_map = {}
    for record in transaction_records:
        if record.get('is_rejected'):
            continue
        origin_id = record.get('origin_id')
        if origin_id:
            if origin_id not in location_records_map:
                location_records_map[origin_id] = []
            location_records_map[origin_id].append(record)
    
    # Collect all location IDs and fetch names
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
    
    # Fetch all category names
    all_category_ids = set()
    for record in transaction_records:
        if record.get('is_rejected'):
            continue
        material = record.get('material') or {}
        cat_id = material.get('category_id') or record.get('category_id')
        if cat_id:
            try:
                all_category_ids.add(int(cat_id))
            except Exception:
                pass
    
    category_names = _fetch_category_names(reports_service.db, all_category_ids)
    
    # Helper to calculate metrics from records (grouped by category)
    def calculate_metrics(records):
        material_metrics = {}
        total_weight = 0.0
        recyclable_weight = 0.0
        general_weight = 0.0
        
        for record in records:
            material = record.get('material') or {}
            weight = _calculate_weight(record, material)
            total_weight += weight
            
            # Get category
            category_id = material.get('category_id') or record.get('category_id')
            try:
                cat_id_int = int(category_id) if category_id is not None else None
            except Exception:
                cat_id_int = None
            if cat_id_int is not None:
                material_name = category_names.get(cat_id_int, f"Category {cat_id_int}")
                material_metrics[material_name] = material_metrics.get(material_name, 0.0) + weight
            
            # Check if recyclable (category 1 or 3)
            if cat_id_int in (1, 3):
                recyclable_weight += weight
            # Sum general weight (category 4)
            if cat_id_int == 4:
                general_weight += weight
        
        recycling_rate = (recyclable_weight / total_weight * 100) if total_weight > 0 else 0.0
        
        # Round values
        metrics = {k: round(v, 2) for k, v in material_metrics.items() if v > 0}
        
        return {
            'metrics': metrics,
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
    # The sequence is always: Branch → Building → Floor → Room (→ Item for 5+ levels)
    # But it can start at any point based on the depth
    HIERARCHY_SEQUENCE = [
        ('branchName', 'buildings'),
        ('buildingName', 'floors'),
        ('floorName', 'rooms'),
        ('roomName', 'items'),
        ('itemName', 'items'),  # For very deep nesting (5+ levels)
    ]
    
    def get_level_config(total_depth):
        """
        Returns (name_key, children_key) for each level based on total depth
        The hierarchy always follows: Branch → Building → Floor → Room (→ Item for 5+ levels)
        But starts at the appropriate point based on depth
        
        Examples:
        - Depth 0 (1 level):  Room
        - Depth 1 (2 levels): Floor → Room
        - Depth 2 (3 levels): Building → Floor → Room
        - Depth 3 (4 levels): Branch → Building → Floor → Room
        - Depth 4+ (5+ levels): Branch → Building → Floor → Room → Item
        """
        # Calculate the starting index in the sequence
        # Sequence indices: 0=Branch, 1=Building, 2=Floor, 3=Room, 4=Item
        # For depth 0-3, start at index (3 - depth)
        # For depth 4+, start at index 0
        start_index = max(0, 3 - total_depth)
        
        configs = []
        for i in range(total_depth + 1):
            seq_index = start_index + i
            if seq_index < len(HIERARCHY_SEQUENCE):
                name_key, children_key = HIERARCHY_SEQUENCE[seq_index]
                # Last level has no children
                if i == total_depth:
                    configs.append((name_key, None))
                else:
                    configs.append((name_key, children_key))
            else:
                # Very deep nesting - continue using itemName with items
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
            
            # Get child nodes
            children = node.get('children', [])
            
            # Recursively process children
            child_items = build_hierarchy(children, level + 1) if children else []
            
            # Aggregate all records from this node and all descendants
            all_records = node_records.copy()
            
            def collect_descendant_records(items):
                collected = []
                for item in items:
                    item_id = int(item['id'])
                    collected.extend(location_records_map.get(item_id, []))
                    
                    # Recursively collect from all possible child keys
                    for child_key in ['buildings', 'floors', 'rooms', 'items']:
                        if child_key in item:
                            for child in item[child_key]:
                                collected.extend(collect_descendant_records([child]))
                
                return collected
            
            if child_items:
                all_records.extend(collect_descendant_records(child_items))
            
            # Calculate metrics
            calc = calculate_metrics(all_records)
            
            # Skip if no data
            if calc['totalWasteKg'] == 0:
                continue
            
            # Get location name
            location_name = location_names.get(node_id, f"Location {node_id}")
            
            # Build item structure - all levels have same base structure
            item = {
                'id': str(node_id),
                'totalWasteKg': calc['totalWasteKg'],
                'metrics': calc['metrics'],
            }
            
            # Level 0 always gets recyclingRatePercent (top of hierarchy)
            if level == 0:
                item['recyclingRatePercent'] = calc['recyclingRatePercent']
                item['recyclable_weight'] = calc['recyclable_weight']
                item['general_weight'] = calc['general_weight']
            
            # Get config for this level
            if level < len(level_configs):
                name_key, children_key = level_configs[level]
            else:
                # Fallback for very deep nesting
                name_key, children_key = ('itemName', 'items' if children else None)
            
            # Set the name
            item[name_key] = location_name
            
            # Set children if they exist
            if child_items and children_key:
                item[children_key] = child_items
            
            result.append(item)
        
        return result
    
    # Build the performance data
    performance_data = build_hierarchy(root_nodes)
    
    return {
        'success': True,
        'data': performance_data,
        'message': 'Performance report generated successfully'
    }

def _handle_comparison_report(
    reports_service: ReportsService,
    organization_id: int,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle /api/reports/comparison endpoint"""
    
    period = filters.get('period')
    left_sel = filters.get('leftSelection')
    right_sel = filters.get('rightSelection')
    
    # Build left and right date ranges
    left_from, left_to = _compute_period_range(period, left_sel)
    right_from, right_to = _compute_period_range(period, right_sel)

    def fetch_side(date_from: Optional[str], date_to: Optional[str]) -> Dict[str, Any]:
        # For comparison, only use period-derived date range; ignore all other filters
        side_filters = {}
        if date_from:
            side_filters['date_from'] = date_from
        if date_to:
            side_filters['date_to'] = date_to
        return reports_service.get_transaction_records_by_organization(
            organization_id=organization_id,
            filters=side_filters if side_filters else None,
            report_type='comparison'
        )

    left_result = fetch_side(left_from, left_to)
    right_result = fetch_side(right_from, right_to)

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

    def build_grouped(result: Dict[str, Any], start_iso: Optional[str], end_iso: Optional[str], reports_service: ReportsService) -> Dict[str, Any]:
        material_map: Dict[str, float] = {}
        month_map: Dict[str, float] = {}
        total_waste = 0.0
        category_ids: set = set()
        # First pass: collect category IDs
        for record in result.get('data', []):
            # Skip rejected
            if record.get('is_rejected'):
                continue
            material = record.get('material') or {}
            cat_id = material.get('category_id') or record.get('category_id')
            if cat_id:
                try:
                    category_ids.add(int(cat_id))
                except Exception:
                    pass
        # Fetch category names
        category_names: Dict[int, str] = {}
        if category_ids:
            try:
                rows = reports_service.db.query(
                    MaterialCategory.id, MaterialCategory.name_en, MaterialCategory.name_th
                ).filter(MaterialCategory.id.in_(category_ids)).all()
                for _id, name_en, name_th in rows:
                    category_names[_id] = (name_en or name_th or f"Category {_id}")
            except Exception:
                category_names = {}

        # Second pass: aggregate
        for record in result.get('data', []):
            if record.get('is_rejected'):
                continue
            material = record.get('material') or {}
            cat_id = material.get('category_id') or record.get('category_id')
            if not cat_id:
                continue
            try:
                cat_id_int = int(cat_id)
            except Exception:
                continue
            material_name = category_names.get(cat_id_int, f"Category {cat_id_int}")
            weight = _calculate_weight(record, material)
            dt = _parse_datetime(record.get('transaction_date'))
            if not dt:
                continue
            month_label = datetime(2000, dt.month, 1).strftime('%b')
            # Aggregate
            material_map[material_name] = material_map.get(material_name, 0.0) + weight
            month_map[month_label] = month_map.get(month_label, 0.0) + weight
            total_waste += weight

        # Ensure months are ordered chronologically in output dict (preserving insertion order by building anew)
        ordered_month_map: Dict[str, float] = {}
        month_labels = _month_labels_in_range(start_iso, end_iso)
        if month_labels is None:
            # Fallback to only present months in Jan..Dec order
            for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']:
                if m in month_map:
                    ordered_month_map[m] = month_map[m]
        else:
            for m in month_labels:
                ordered_month_map[m] = month_map.get(m, 0.0)

        # Sort materials by total_waste desc in an ordered dict-like structure
        ordered_material_items = sorted(material_map.items(), key=lambda kv: kv[1], reverse=True)
        ordered_material_map: Dict[str, float] = {name: val for name, val in ordered_material_items}

        # Clamp tiny floating point residuals and round values
        EPS = 1e-6
        def clamp_round(x: float) -> float:
            if -EPS < x < EPS:
                return 0.0
            return round(x, 2)

        ordered_material_map = {k: clamp_round(v) for k, v in ordered_material_map.items()}
        ordered_month_map = {k: clamp_round(v) for k, v in ordered_month_map.items()}
        total_waste = clamp_round(total_waste)

        return {
            'material': ordered_material_map,
            'month': ordered_month_map,
            'total_waste_kg': total_waste,
        }

    left_grouped = build_grouped(left_result, left_from, left_to, reports_service)
    right_grouped = build_grouped(right_result, right_from, right_to, reports_service)

    return {
        'success': True,
        'left': left_grouped,
        'right': right_grouped,
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
        if path == '/api/reports/overview':
            filters = _build_filters_from_query_params(query_params)
            return _handle_overview_report(reports_service, organization_id, filters)

        elif path == '/api/reports/performance':
            filters = _build_filters_from_query_params(query_params)
            return _handle_performance_report(reports_service, organization_id, filters)
        
        elif path == '/api/reports/diversion':
            filters = _build_filters_from_query_params(query_params)
            return _handle_diversion_report(reports_service, organization_id, filters)
        
        elif path == '/api/reports/filter/origins':
            filters = _build_filters_from_query_params(query_params)
            # Remove origin filters - only use material filters for origins endpoint
            filters.pop('origin_ids', None)
            # Do not apply default YTD for filter endpoints; only use dates if explicitly provided
            has_date = any(k in query_params for k in ('date_from', 'date_to', 'datefrom', 'dateto'))
            if not has_date:
                filters.pop('date_from', None)
                filters.pop('date_to', None)
            return reports_service.get_origin_by_organization(organization_id=organization_id, filters=filters)

        elif path == '/api/reports/filter/materials':
            filters = _build_filters_from_query_params(query_params)
            # Remove material filters - only use origin filters for materials endpoint
            filters.pop('material_ids', None)
            # Do not apply default YTD for filter endpoints; only use dates if explicitly provided
            has_date = any(k in query_params for k in ('date_from', 'date_to', 'datefrom', 'dateto'))
            if not has_date:
                filters.pop('date_from', None)
                filters.pop('date_to', None)
            return reports_service.get_material_by_organization(organization_id=organization_id, filters=filters)
        
        elif path == '/api/reports/comparison':
            filters = _build_filters_from_query_params(query_params)
            return _handle_comparison_report(reports_service, organization_id, filters)

        elif path == '/api/reports/materials':
            filters = _build_filters_from_query_params(query_params)
            return _handle_materials_report(reports_service, organization_id, filters)
    
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
