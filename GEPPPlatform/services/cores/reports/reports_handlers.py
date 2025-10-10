"""
Reports HTTP handlers
Handles all /api/reports/* routes
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .reports_service import ReportsService
from ....exceptions import APIException, ValidationException, NotFoundException
from GEPPPlatform.models.cores.references import MainMaterial


def handle_reports_routes(event: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all reports-related endpoints
    
    Routes:
    - GET /api/reports - Get transaction records for the organization
    """
    
    db_session = common_params.get('db_session')
    method = common_params.get('method', 'GET')
    query_params = common_params.get('query_params', {})
    path_params = common_params.get('path_params', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    
    try:
        # Initialize service
        reports_service = ReportsService(db_session)
        
        # Only handle GET requests for now
        if method == 'GET':
            if path == '/api/reports/overview':
                # Get organization_id from current user
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                # Build filters from query params
                filters = {}
                if query_params.get('material_id'):
                    filters['material_id'] = int(query_params['material_id'])
                if query_params.get('origin_id'):
                    filters['origin_id'] = int(query_params['origin_id'])
                if query_params.get('date_from'):
                    filters['date_from'] = query_params['date_from']
                if query_params.get('date_to'):
                    filters['date_to'] = query_params['date_to']   
                
                # Get transaction records using service
                result = reports_service.get_transaction_records_by_organization(
                    organization_id=organization_id,
                    filters=filters if filters else None,
                    report_type='overview'
                )
                
                # Build overview response including totals
                ghg_reduction = 0.0
                total_waste = 0.0
                recyclable_waste = 0.0  # category_id in {1, 3}
                origin_waste_map = {}
                material_waste_map = {}
                plastic_saved = 0.0
                recyclable_ghg_reduction = 0.0  # sum of GHG reduction for recyclable categories (1, 3)
                month_totals = {}
                for record in result.get('data', []):
                    # Skip rejected transactions for all downstream metrics
                    if record.get('is_rejected'):
                        continue
                    quantity = float(record.get('origin_quantity') or 0)
                    material = record.get('material') or {}
                    unit_weight = float(material.get('unit_weight') or 0)
                    calc_ghg = float(material.get('calc_ghg') or 0)
                    weight = quantity * unit_weight
                    total_waste += weight
                    record_ghg = weight * calc_ghg
                    ghg_reduction += record_ghg

                    # Aggregate by month for chart_data
                    created_str = record.get('created_date')
                    if created_str:
                        try:
                            dt = datetime.fromisoformat(created_str)
                        except Exception:
                            try:
                                dt = datetime.fromisoformat(created_str.replace('Z', '+00:00')) if isinstance(created_str, str) else None
                            except Exception:
                                dt = None
                        if dt is not None:
                            m = dt.month
                            month_totals[m] = month_totals.get(m, 0.0) + weight

                    # Plastic saved: only materials tagged plastic
                    try:
                        if material.get('is_plastic'):
                            plastic_saved += weight
                    except Exception:
                        pass

                    # Determine category from material if present, otherwise fallback to record.category_id
                    cat_id = material.get('category_id') if material else record.get('category_id')
                    try:
                        cat_id_int = int(cat_id) if cat_id is not None else None
                    except Exception:
                        cat_id_int = None
                    if cat_id_int in (1, 3):
                        recyclable_waste += weight
                        recyclable_ghg_reduction += record_ghg
                        # Aggregate waste by origin for top recyclables (only recyclable materials)
                        origin_id = record.get('origin_id')
                        if origin_id is not None:
                            origin_waste_map[origin_id] = origin_waste_map.get(origin_id, 0.0) + weight

                    # Aggregate waste by material for waste_type_proportions
                    material_id = record.get('material_id') or material.get('id')
                    if material_id is not None:
                        entry = material_waste_map.get(material_id)
                        if entry is None:
                            entry = {
                                'material_id': material_id,
                                'material_name': material.get('name_en') or material.get('name_th'),
                                'total_waste': 0.0
                            }
                            material_waste_map[material_id] = entry
                        entry['total_waste'] += weight

                recycle_rate = (recyclable_waste / total_waste) if total_waste > 0 else 0.0

                # Build top recyclables: top 5 origins by total waste
                top_origin_ids = sorted(origin_waste_map.items(), key=lambda kv: kv[1], reverse=True)[:5]
                # Fetch origin names for display
                top_recyclables = []
                if top_origin_ids:
                    origin_names_map = {}
                    try:
                        origins_result = reports_service.get_origin_by_organization(organization_id=organization_id)
                        for o in origins_result.get('data', []):
                            origin_names_map[o.get('id')] = o.get('display_name') or o.get('name_en') or o.get('name_th')
                    except Exception:
                        origin_names_map = {}
                    for oid, w in top_origin_ids:
                        top_recyclables.append({
                            'origin_id': oid,
                            'origin_name': origin_names_map.get(oid),
                            'total_waste': w
                        })

                # Build chart_data sorted by calendar month
                chart_data = []
                for m in sorted(month_totals.keys()):
                    # Use a fixed year to format month abbreviation
                    month_label = datetime(2000, m, 1).strftime('%b')
                    chart_data.append({'month': month_label, 'value': month_totals[m]})

                overview_data = {
                    'transactions_total': result.get('transactions_total', 0),
                    'transactions_approved': result.get('transactions_approved', 0),
                    'key_indicators': {
                        'total_waste': total_waste,
                        'recycle_rate': recycle_rate,
                        'ghg_reduction': ghg_reduction,
                    },
                    'top_recyclables': top_recyclables,
                    'overall_charts': { 'chart_stat_data': [
                        {'title': 'Total Recyclables', 'value': recyclable_waste},
                        {'title': 'Number of Trees', 'value': (recyclable_ghg_reduction / 9.5 * 100) if recyclable_ghg_reduction > 0 else 0.0},
                        {'title': 'Plastic Saved', 'value': plastic_saved},
                    ],
                        'chart_data': chart_data
                    },
                    'waste_type_proportions': sorted(material_waste_map.values(), key=lambda x: x['total_waste'], reverse=True),
                    'material_summary': []
                }
                
                return overview_data
            elif path == '/api/reports/materials':
                # Get organization_id from current user
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                # Build filters from query params
                filters = {}
                if query_params.get('material_id'):
                    filters['material_id'] = int(query_params['material_id'])
                if query_params.get('origin_id'):
                    filters['origin_id'] = int(query_params['origin_id'])
                if query_params.get('date_from'):
                    filters['date_from'] = query_params['date_from']
                if query_params.get('date_to'):
                    filters['date_to'] = query_params['date_to']   
                
                # Get transaction records using service
                result = reports_service.get_transaction_records_by_organization(
                    organization_id=organization_id,
                    filters=filters if filters else None,
                    report_type='overview'
                )

                # Aggregate total weight and GHG reduction per main_material
                main_material_agg_map = {}
                total_waste_main = 0.0
                for record in result.get('data', []):
                    material = record.get('material') or {}
                    main_id = material.get('main_material_id') or record.get('main_material_id')
                    if main_id is None:
                        continue
                    quantity = float(record.get('origin_quantity') or 0)
                    unit_weight = float(material.get('unit_weight') or 0)
                    calc_ghg = float(material.get('calc_ghg') or 0)
                    weight = quantity * unit_weight
                    ghg = weight * calc_ghg
                    total_waste_main += weight
                    agg = main_material_agg_map.get(main_id)
                    if agg is None:
                        agg = {'total_waste': 0.0, 'ghg_reduction': 0.0}
                        main_material_agg_map[main_id] = agg
                    agg['total_waste'] += weight
                    agg['ghg_reduction'] += ghg

                # Fetch main material names for display
                name_map = {}
                if main_material_agg_map:
                    try:
                        rows = reports_service.db.query(MainMaterial.id, MainMaterial.name_en, MainMaterial.name_th).filter(
                            MainMaterial.id.in_(list(main_material_agg_map.keys()))
                        ).all()
                        for _id, name_en, name_th in rows:
                            name_val = name_en or name_th
                            name_map[_id] = name_val
                    except Exception:
                        name_map = {}

                proportions = [
                    {
                        'main_material_id': mid,
                        'main_material_name': name_map.get(mid),
                        'total_waste': agg['total_waste'],
                        'ghg_reduction': agg['ghg_reduction'],
                        'proportion_percent': (agg['total_waste'] / total_waste_main * 100) if total_waste_main > 0 else 0.0,
                    }
                    for mid, agg in sorted(main_material_agg_map.items(), key=lambda kv: kv[1]['total_waste'], reverse=True)
                ]

                # Sub materials (actual materials from transaction_records)
                sub_material_agg_map = {}
                sub_total_waste = 0.0
                for record in result.get('data', []):
                    if record.get('is_rejected'):
                        continue
                for record in result.get('data', []):
                    if record.get('is_rejected'):
                        continue
                    material = record.get('material') or {}
                    material_id = record.get('material_id') or material.get('id')
                    if material_id is None:
                        continue
                    quantity = float(record.get('origin_quantity') or 0)
                    unit_weight = float(material.get('unit_weight') or 0)
                    calc_ghg = float(material.get('calc_ghg') or 0)
                    weight = quantity * unit_weight
                    ghg = weight * calc_ghg
                    sub_total_waste += weight
                    agg = sub_material_agg_map.get(material_id)
                    if agg is None:
                        agg = {
                            'material_id': material_id,
                            'material_name': material.get('name_en') or material.get('name_th'),
                            'total_waste': 0.0,
                            'ghg_reduction': 0.0,
                        }
                        sub_material_agg_map[material_id] = agg
                    agg['total_waste'] += weight
                    agg['ghg_reduction'] += ghg

                # Add proportion percent and sort
                sub_proportions = []
                for item in sub_material_agg_map.values():
                    item['proportion_percent'] = (item['total_waste'] / sub_total_waste * 100) if sub_total_waste > 0 else 0.0
                    sub_proportions.append(item)
                sub_proportions.sort(key=lambda x: x['total_waste'], reverse=True)

                material_summary_data = {
                    'main_material': {
                        'porportions': proportions,
                        'total_waste': total_waste_main,
                    },
                    'sub_material': {
                        'porportions': sub_proportions,
                        'total_waste': sub_total_waste,
                    }
                }

                return material_summary_data

            elif path == '/api/reports/diversion':
                # Get organization_id from current user
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                # Build filters from query params
                filters = {}
                if query_params.get('material_id'):
                    filters['material_id'] = int(query_params['material_id'])
                if query_params.get('origin_id'):
                    filters['origin_id'] = int(query_params['origin_id'])
                if query_params.get('date_from'):
                    filters['date_from'] = query_params['date_from']
                if query_params.get('date_to'):
                    filters['date_to'] = query_params['date_to']   
                
                # Get transaction records using service
                result = reports_service.get_transaction_records_by_organization(
                    organization_id=organization_id,
                    filters=filters if filters else None,
                    report_type='overview'
                )

                waste_diversion_data = {
                    
                }

                return waste_diversion_data
            
            elif path == '/api/reports/origins':
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                result = reports_service.get_origin_by_organization(
                    organization_id=organization_id
                )
                return result
            
            elif path == '/api/reports/materials':
                organization_id = current_user.get('organization_id')
                
                if not organization_id:
                    raise ValidationException("Organization ID is required")
                
                result = reports_service.get_material_by_organization(
                    organization_id=organization_id
                )
                
                return result
            else:
                raise APIException(
                    "Report endpoint not found",
                    status_code=404,
                    error_code="REPORT_NOT_FOUND"
                )
        
        else:
            raise APIException(
                f"Method {method} not supported yet. Only GET requests are available.",
                status_code=405,
                error_code="METHOD_NOT_ALLOWED"
            )
    
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

