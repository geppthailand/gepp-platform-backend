"""
Supply Chain HTTP Handler — routes /api/esg/supply-chain/* and /api/esg/supplier-portal/*
"""

import json
import logging
from typing import Dict, Any

from GEPPPlatform.libs.authGuard import verify_jwt

from .supplier_service import SupplierService
from .supplier_portal_service import SupplierPortalService
from .supplier_submission_service import SupplierSubmissionService
from .chaser_service import ChaserService
from .scope3_service import Scope3Service
from .cbam_service import CbamService
from .macc_service import MaccService

logger = logging.getLogger(__name__)


def handle_supply_chain_routes(event: Dict[str, Any], context, session) -> Dict[str, Any]:
    """Route supply chain API requests."""
    path = event.get('path', '') or event.get('rawPath', '')
    method = event.get('httpMethod', 'GET')
    body = json.loads(event.get('body', '{}') or '{}')
    params = event.get('queryStringParameters') or {}
    headers = event.get('headers') or {}

    try:
        # --- Supplier Portal (no auth required) ---
        if '/supplier-portal/' in path:
            return _handle_supplier_portal(path, method, body, params, session)

        # --- All other routes require auth ---
        user = verify_jwt(headers)
        if not user:
            return _response(401, {'error': 'Unauthorized'})

        org_id = user.get('organization_id')
        user_id = user.get('user_id')

        if '/suppliers/bulk-import' in path:
            return _handle_supplier_bulk_import(method, body, session, org_id)
        elif '/suppliers' in path:
            return _handle_suppliers(path, method, body, params, session, org_id, user)
        elif '/chasers' in path:
            return _handle_chasers(path, method, body, params, session, org_id)
        elif '/scope3/' in path or path.endswith('/scope3'):
            return _handle_scope3(path, method, body, params, session, org_id)
        elif '/cbam/' in path or path.endswith('/cbam'):
            return _handle_cbam(path, method, body, params, session, org_id)
        elif '/macc/' in path or path.endswith('/macc'):
            return _handle_macc(path, method, body, params, session, org_id)
        elif '/submission-status' in path:
            return _handle_submission_status(method, params, session, org_id)
        elif '/submissions/' in path or path.endswith('/submissions'):
            return _handle_submissions(path, method, body, params, session, org_id, user_id)

        return _response(404, {'error': 'Not found'})

    except Exception as e:
        logger.error(f"Supply chain route error: {e}", exc_info=True)
        return _response(500, {'error': f'Internal server error: {str(e)}'})


# ---------------------------------------------------------------------------
# Sub-handlers
# ---------------------------------------------------------------------------

def _handle_suppliers(path, method, body, params, session, org_id, user):
    """CRUD for suppliers."""
    svc = SupplierService(session)
    supplier_id = _extract_id(path, 'suppliers')

    if method == 'GET' and supplier_id:
        result = svc.get_supplier(org_id, supplier_id)
        if not result:
            return _response(404, {'error': 'Supplier not found'})
        return _response(200, {'success': True, 'supplier': result})

    if method == 'GET':
        result = svc.list_suppliers(
            org_id,
            status=params.get('status'),
            tier=params.get('tier'),
            search=params.get('search'),
            page=int(params.get('page', 1)),
            size=min(int(params.get('size', 50)), 200),
        )
        return _response(200, {'success': True, **result})

    if method == 'POST':
        if not body:
            return _response(400, {'error': 'Request body is required'})
        result = svc.create_supplier(org_id, body)
        return _response(201, {'success': True, 'supplier': result})

    if method == 'PUT' and supplier_id:
        if not body:
            return _response(400, {'error': 'Request body is required'})
        result = svc.update_supplier(org_id, supplier_id, body)
        if not result:
            return _response(404, {'error': 'Supplier not found'})
        return _response(200, {'success': True, 'supplier': result})

    if method == 'DELETE' and supplier_id:
        deleted = svc.delete_supplier(org_id, supplier_id)
        if not deleted:
            return _response(404, {'error': 'Supplier not found'})
        return _response(200, {'success': True, 'message': 'Supplier deleted'})

    return _response(405, {'error': 'Method not allowed'})


def _handle_supplier_bulk_import(method, body, session, org_id):
    """Bulk import suppliers."""
    if method != 'POST':
        return _response(405, {'error': 'Method not allowed'})
    if not body or not body.get('suppliers'):
        return _response(400, {'error': 'suppliers array is required'})
    svc = SupplierService(session)
    result = svc.bulk_import(org_id, body['suppliers'])
    return _response(200, {'success': True, **result})


def _handle_supplier_portal(path, method, body, params, session):
    """Supplier portal — magic link auth, form schema, submission."""
    svc = SupplierPortalService(session)

    if '/verify' in path and method == 'POST':
        token = body.get('token') or params.get('token')
        if not token:
            return _response(400, {'error': 'token is required'})
        result = svc.verify_token(token)
        if not result.get('valid'):
            return _response(401, {'error': result.get('error', 'Invalid token')})
        return _response(200, {'success': True, **result})

    if '/form-schema' in path and method == 'GET':
        token = params.get('token')
        if not token:
            return _response(400, {'error': 'token is required'})
        result = svc.get_form_schema(token)
        if not result:
            return _response(401, {'error': 'Invalid or expired token'})
        return _response(200, {'success': True, **result})

    if '/submit' in path and method == 'POST':
        token = body.get('token') or params.get('token')
        if not token:
            return _response(400, {'error': 'token is required'})
        result = svc.submit_data(token, body.get('data', {}))
        if result.get('error'):
            return _response(400, result)
        return _response(201, {'success': True, **result})

    if '/history' in path and method == 'GET':
        token = params.get('token')
        if not token:
            return _response(400, {'error': 'token is required'})
        result = svc.get_submission_history(token)
        if result is None:
            return _response(401, {'error': 'Invalid or expired token'})
        return _response(200, {'success': True, 'submissions': result})

    if '/magic-link' in path and method == 'POST':
        # Creating a magic link (called by org user, but routed here for convenience)
        result = svc.create_magic_link(
            supplier_id=body.get('supplier_id'),
            org_id=body.get('org_id'),
            email=body.get('email'),
            expires_days=body.get('expires_days', 30),
        )
        return _response(201, {'success': True, **result})

    return _response(404, {'error': 'Portal route not found'})


def _handle_submission_status(method, params, session, org_id):
    """Submission traffic-light summary."""
    if method != 'GET':
        return _response(405, {'error': 'Method not allowed'})
    svc = SupplierService(session)
    result = svc.get_submission_status(org_id)
    return _response(200, {'success': True, **result})


def _handle_submissions(path, method, body, params, session, org_id, user_id):
    """Submission list / review / bulk-approve."""
    svc = SupplierSubmissionService(session)
    submission_id = _extract_id(path, 'submissions')

    if '/bulk-approve' in path and method == 'POST':
        ids = body.get('submission_ids', [])
        if not ids:
            return _response(400, {'error': 'submission_ids is required'})
        result = svc.bulk_approve(org_id, ids)
        return _response(200, {'success': True, **result})

    if method == 'GET' and not submission_id:
        result = svc.list_submissions(
            org_id,
            supplier_id=params.get('supplier_id'),
            status=params.get('status'),
            year=int(params['year']) if params.get('year') else None,
        )
        return _response(200, {'success': True, **result})

    if method == 'POST' and submission_id and ('/review' in path or '/approve' in path or '/reject' in path):
        action = 'approve' if '/approve' in path else ('reject' if '/reject' in path else body.get('action', 'approve'))
        result = svc.review_submission(
            submission_id, org_id, action,
            notes=body.get('notes'),
            reviewer_id=user_id,
        )
        if not result:
            return _response(404, {'error': 'Submission not found'})
        return _response(200, {'success': True, 'submission': result})

    return _response(405, {'error': 'Method not allowed'})


def _handle_chasers(path, method, body, params, session, org_id):
    """Chaser CRUD + trigger."""
    svc = ChaserService(session)
    chaser_id = _extract_id(path, 'chasers')

    if '/trigger' in path and method == 'POST':
        result = svc.trigger_due_chasers(org_id)
        return _response(200, {'success': True, **result})

    if method == 'GET':
        result = svc.list_chasers(org_id)
        return _response(200, {'success': True, 'chasers': result})

    if method == 'POST':
        if not body:
            return _response(400, {'error': 'Request body is required'})
        body['organization_id'] = org_id
        result = svc.create_chaser(body)
        return _response(201, {'success': True, 'chaser': result})

    if method == 'PUT' and chaser_id:
        if not body:
            return _response(400, {'error': 'Request body is required'})
        result = svc.update_chaser(chaser_id, body)
        if not result:
            return _response(404, {'error': 'Chaser not found'})
        return _response(200, {'success': True, 'chaser': result})

    if method == 'DELETE' and chaser_id:
        deleted = svc.delete_chaser(chaser_id, org_id)
        if not deleted:
            return _response(404, {'error': 'Chaser not found'})
        return _response(200, {'success': True, 'message': 'Chaser deleted'})

    return _response(405, {'error': 'Method not allowed'})


def _handle_scope3(path, method, body, params, session, org_id):
    """Scope 3 categories, entries, summary."""
    svc = Scope3Service(session)
    entry_id = _extract_id(path, 'entries')

    if '/categories' in path and method == 'GET':
        result = svc.get_categories()
        return _response(200, {'success': True, 'categories': result})

    if '/summary' in path and method == 'GET':
        year = int(params['year']) if params.get('year') else None
        result = svc.get_summary(org_id, year=year)
        return _response(200, {'success': True, **result})

    if '/calculate' in path and method == 'POST':
        cat = body.get('category_number')
        calc_method = body.get('method', 'spend_based')
        if not cat:
            return _response(400, {'error': 'category_number is required'})
        result = svc.calculate_category(org_id, cat, method=calc_method)
        return _response(200, {'success': True, **result})

    if '/entries' in path:
        if method == 'GET':
            result = svc.list_entries(
                org_id,
                category=params.get('category'),
                year=int(params['year']) if params.get('year') else None,
                method=params.get('method'),
            )
            return _response(200, {'success': True, **result})

        if method == 'POST':
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.create_entry(org_id, body)
            return _response(201, {'success': True, 'entry': result})

        if method == 'PUT' and entry_id:
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.update_entry(entry_id, org_id, body)
            if not result:
                return _response(404, {'error': 'Entry not found'})
            return _response(200, {'success': True, 'entry': result})

    return _response(405, {'error': 'Method not allowed'})


def _handle_cbam(path, method, body, params, session, org_id):
    """CBAM products and reports."""
    svc = CbamService(session)
    product_id = _extract_id(path, 'products')

    if '/report' in path and method == 'POST':
        quarter = body.get('quarter')
        year = body.get('year')
        if not quarter or not year:
            return _response(400, {'error': 'quarter and year are required'})
        result = svc.generate_report(org_id, quarter, year)
        return _response(200, {'success': True, **result})

    if '/defaults' in path and method == 'GET':
        result = svc.get_default_values(cn_code=params.get('cn_code'))
        return _response(200, {'success': True, 'defaults': result})

    if '/compare' in path and method == 'GET' and product_id:
        result = svc.compare_with_defaults(product_id, org_id)
        if not result:
            return _response(404, {'error': 'Product not found'})
        return _response(200, {'success': True, **result})

    if '/calculate' in path and method == 'POST' and product_id:
        result = svc.calculate_embedded_emissions(product_id, org_id)
        if not result:
            return _response(404, {'error': 'Product not found'})
        return _response(200, {'success': True, **result})

    if '/products' in path or method in ('GET', 'POST', 'PUT', 'DELETE'):
        if method == 'GET' and product_id:
            result = svc.get_product(product_id, org_id)
            if not result:
                return _response(404, {'error': 'Product not found'})
            return _response(200, {'success': True, 'product': result})

        if method == 'GET':
            result = svc.list_products(org_id)
            return _response(200, {'success': True, 'products': result})

        if method == 'POST':
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.create_product(org_id, body)
            return _response(201, {'success': True, 'product': result})

        if method == 'PUT' and product_id:
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.update_product(product_id, org_id, body)
            if not result:
                return _response(404, {'error': 'Product not found'})
            return _response(200, {'success': True, 'product': result})

    return _response(405, {'error': 'Method not allowed'})


def _handle_macc(path, method, body, params, session, org_id):
    """MACC initiatives and curve generation."""
    svc = MaccService(session)
    initiative_id = _extract_id(path, 'initiatives')

    if '/library' in path and method == 'GET':
        result = svc.get_library(
            category=params.get('category'),
            scope=params.get('scope'),
            difficulty=params.get('difficulty'),
        )
        return _response(200, {'success': True, 'library': result})

    if '/curve' in path and method == 'GET':
        result = svc.generate_curve(org_id)
        return _response(200, {'success': True, **result})

    if '/initiatives' in path or method in ('GET', 'POST', 'PUT'):
        if method == 'GET':
            result = svc.list_initiatives(org_id, status=params.get('status'))
            return _response(200, {'success': True, 'initiatives': result})

        if method == 'POST':
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.create_initiative(org_id, body)
            return _response(201, {'success': True, 'initiative': result})

        if method == 'PUT' and initiative_id:
            if not body:
                return _response(400, {'error': 'Request body is required'})
            result = svc.update_initiative(initiative_id, org_id, body)
            if not result:
                return _response(404, {'error': 'Initiative not found'})
            return _response(200, {'success': True, 'initiative': result})

    return _response(405, {'error': 'Method not allowed'})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_id(path: str, segment: str):
    """Extract integer ID from path segment, e.g. /suppliers/123 -> 123. Returns None if absent."""
    try:
        parts = path.rstrip('/').split('/')
        idx = parts.index(segment)
        raw = parts[idx + 1]
        # Ignore sub-resources like 'bulk-import', 'review', etc.
        return int(raw)
    except (ValueError, IndexError):
        return None


def _response(status: int, body: dict) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps(body, default=str),
    }
