"""
ESG API Handlers — Route dispatch for all ESG endpoints
"""

from typing import Dict, Any
import logging
import traceback

from .esg_service import EsgService
from .esg_document_service import EsgDocumentService
from .esg_calculation_service import EsgCalculationService
from ...exceptions import (
    APIException, UnauthorizedException, NotFoundException,
    BadRequestException, ValidationException
)

logger = logging.getLogger(__name__)


def handle_esg_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """Main handler for ESG routes"""
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})

    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    esg_service = EsgService(db_session)
    doc_service = EsgDocumentService(db_session)
    calc_service = EsgCalculationService(db_session)

    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_org_id = current_user.get('organization_id')

    try:
        # ===== SETTINGS =====
        if path == '/api/esg/settings' and method == 'GET':
            return esg_service.get_settings(current_user_org_id)

        elif path == '/api/esg/settings' and method == 'POST':
            return esg_service.update_settings(current_user_org_id, data or {})

        # ===== DOCUMENTS =====
        elif path == '/api/esg/documents' and method == 'GET':
            return esg_service.list_documents(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                page_size=min(int(query_params.get('page_size', 20)), 100),
                esg_category=query_params.get('esg_category'),
                document_type=query_params.get('document_type'),
                ai_status=query_params.get('ai_status'),
                source=query_params.get('source'),
            )

        elif path == '/api/esg/documents' and method == 'POST':
            if not data:
                raise BadRequestException('Request body is required')
            return doc_service.upload_and_classify(
                organization_id=current_user_org_id,
                file_data=data,
                uploaded_by_id=int(current_user_id) if current_user_id else None,
            )

        elif '/api/esg/documents/' in path and '/classify' in path and method == 'POST':
            doc_id = _extract_id_from_path(path, 'documents')
            return doc_service.classify_document(doc_id, current_user_org_id)

        elif '/api/esg/documents/' in path and method == 'GET':
            doc_id = _extract_id_from_path(path, 'documents')
            return esg_service.get_document(doc_id, current_user_org_id)

        # ===== WASTE RECORDS =====
        elif path == '/api/esg/waste-records' and method == 'GET':
            return esg_service.list_waste_records(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                page_size=min(int(query_params.get('page_size', 20)), 100),
                waste_type=query_params.get('waste_type'),
                treatment_method=query_params.get('treatment_method'),
                date_from=query_params.get('date_from'),
                date_to=query_params.get('date_to'),
                verification_status=query_params.get('verification_status'),
            )

        elif path == '/api/esg/waste-records' and method == 'POST':
            if not data:
                raise BadRequestException('Request body is required')
            return esg_service.create_waste_record(
                organization_id=current_user_org_id,
                data=data,
                created_by_id=int(current_user_id) if current_user_id else None,
            )

        elif path == '/api/esg/waste-records/bulk' and method == 'POST':
            if not data or not data.get('document_id') or not data.get('records'):
                raise BadRequestException('document_id and records are required')
            return esg_service.bulk_create_waste_records(
                organization_id=current_user_org_id,
                document_id=data['document_id'],
                records_data=data['records'],
                created_by_id=int(current_user_id) if current_user_id else None,
            )

        elif '/api/esg/waste-records/' in path and method == 'PUT':
            record_id = _extract_id_from_path(path, 'waste-records')
            if not data:
                raise BadRequestException('Request body is required')
            return esg_service.update_waste_record(record_id, current_user_org_id, data)

        elif '/api/esg/waste-records/' in path and method == 'DELETE':
            record_id = _extract_id_from_path(path, 'waste-records')
            return esg_service.delete_waste_record(record_id, current_user_org_id)

        elif '/api/esg/waste-records/' in path and method == 'GET':
            record_id = _extract_id_from_path(path, 'waste-records')
            return esg_service.get_waste_record(record_id, current_user_org_id)

        # ===== EMISSION FACTORS =====
        elif path == '/api/esg/emission-factors' and method == 'GET':
            return esg_service.list_emission_factors(
                waste_type=query_params.get('waste_type'),
                treatment_method=query_params.get('treatment_method'),
                source=query_params.get('source'),
            )

        # ===== DASHBOARD =====
        elif path == '/api/esg/dashboard' and method == 'GET':
            year = int(query_params.get('year', 0)) or None
            return esg_service.get_dashboard_kpis(current_user_org_id, year)

        elif path == '/api/esg/dashboard/trends' and method == 'GET':
            year = int(query_params.get('year', 0)) or None
            return esg_service.get_dashboard_trends(current_user_org_id, year)

        elif path == '/api/esg/dashboard/breakdown' and method == 'GET':
            year = int(query_params.get('year', 0)) or None
            group_by = query_params.get('group_by', 'treatment_method')
            return esg_service.get_dashboard_breakdown(current_user_org_id, year, group_by)

        # ===== SUMMARIES / RECALCULATE =====
        elif path == '/api/esg/summaries/recalculate' and method == 'POST':
            year = int((data or {}).get('year', 0)) or None
            if not year:
                raise BadRequestException('year is required')
            return calc_service.recalculate_all_summaries(current_user_org_id, year)

        # ===== PRESIGNED URLs =====
        elif path == '/api/esg/presigneds' and method == 'POST':
            return _handle_presigned_urls(data, current_user_id, current_user_org_id, db_session)

        else:
            return {
                'success': False,
                'message': 'ESG route not found',
                'error_code': 'ROUTE_NOT_FOUND'
            }

    except ValidationException as e:
        response = {'success': False, 'message': str(e), 'error_code': 'VALIDATION_ERROR'}
        if hasattr(e, 'errors') and e.errors:
            response['errors'] = e.errors
        return response
    except NotFoundException as e:
        return {'success': False, 'message': str(e), 'error_code': 'NOT_FOUND'}
    except UnauthorizedException as e:
        return {'success': False, 'message': str(e), 'error_code': 'UNAUTHORIZED'}
    except BadRequestException as e:
        return {'success': False, 'message': str(e), 'error_code': 'BAD_REQUEST'}
    except APIException as e:
        return {'success': False, 'message': str(e), 'error_code': 'API_ERROR', 'stack_trace': traceback.format_exc()}
    except Exception as e:
        logger.error(f"ESG route error: {str(e)}", exc_info=True)
        return {'success': False, 'message': f'Internal server error: {str(e)}', 'error_code': 'INTERNAL_ERROR'}


def _handle_presigned_urls(data, current_user_id, current_user_org_id, db_session):
    """Generate presigned URLs for ESG document uploads"""
    if not data or not data.get('file_names'):
        raise BadRequestException('file_names is required')

    from ..cores.transactions.presigned_url_service import TransactionPresignedUrlService
    presigned_service = TransactionPresignedUrlService()

    result = presigned_service.get_transaction_file_upload_presigned_urls(
        file_names=data['file_names'],
        organization_id=current_user_org_id,
        user_id=int(current_user_id),
        db=db_session,
        file_type=data.get('file_type', 'esg_document'),
        related_entity_type='esg_document',
        related_entity_id=data.get('related_entity_id'),
        expiration_seconds=data.get('expiration_seconds', 3600)
    )

    if result['success']:
        return {
            'success': True,
            'message': result['message'],
            'presigned_urls': result['presigned_urls'],
            'file_records': result.get('file_records', []),
            'expires_in_seconds': result.get('expires_in_seconds', 3600)
        }
    raise APIException(result['message'])


def _extract_id_from_path(path: str, segment: str) -> int:
    """Extract ID from URL path after the given segment"""
    try:
        parts = path.split('/')
        idx = parts.index(segment)
        return int(parts[idx + 1])
    except (ValueError, IndexError):
        raise BadRequestException(f'Invalid ID in URL path for {segment}')
