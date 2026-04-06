"""
ESG API Handlers — Route dispatch for all ESG endpoints
"""

from typing import Dict, Any
import logging
import traceback

from .esg_service import EsgService
from .esg_document_service import EsgDocumentService
from .esg_ideas_service import EsgIdeasService
from .esg_line_service import EsgLineService
from .esg_data_entry_service import EsgDataEntryService
from .esg_export_service import EsgExportService
from .esg_dashboard_service import EsgDashboardService
from .esg_carbon_service import EsgCarbonService
from .esg_notification_service import EsgNotificationService
from .liff_auth_service import LiffAuthService
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

    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_org_id = current_user.get('organization_id')

    try:
        # ===== LIFF APIs (/api/esg/liff/*) =====
        if path == '/api/esg/liff/summary' and method == 'GET':
            dash = EsgDashboardService(db_session)
            return dash.get_summary(current_user_org_id)

        elif path == '/api/esg/liff/charts' and method == 'GET':
            dash = EsgDashboardService(db_session)
            year = int(query_params.get('year', 0)) or None
            return dash.get_charts(current_user_org_id, year)

        elif path == '/api/esg/liff/entries' and method == 'GET':
            entry_service = EsgDataEntryService(db_session)
            return entry_service.list_entries(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                size=min(int(query_params.get('size', 10)), 100),
                status=query_params.get('status'),
            )

        elif path == '/api/esg/liff/entries' and method == 'POST':
            if not data:
                raise BadRequestException('Request body is required')
            entry_service = EsgDataEntryService(db_session)
            return entry_service.create_entry(current_user_org_id, int(current_user_id), data)

        elif '/api/esg/liff/entries/' in path and '/verify' in path and method == 'POST':
            entry_id = _extract_id_from_path(path, 'entries')
            entry_service = EsgDataEntryService(db_session)
            result = entry_service.verify_entry(entry_id, current_user_org_id)
            if not result:
                raise NotFoundException('Data entry not found')
            return result

        elif '/api/esg/liff/entries/' in path and method == 'PUT':
            entry_id = _extract_id_from_path(path, 'entries')
            if not data:
                raise BadRequestException('Request body is required')
            entry_service = EsgDataEntryService(db_session)
            result = entry_service.update_entry(entry_id, current_user_org_id, data)
            if not result:
                raise NotFoundException('Data entry not found')
            return result

        elif '/api/esg/liff/entries/' in path and method == 'DELETE':
            entry_id = _extract_id_from_path(path, 'entries')
            entry_service = EsgDataEntryService(db_session)
            deleted = entry_service.delete_entry(entry_id, current_user_org_id)
            if not deleted:
                raise NotFoundException('Data entry not found')
            return {'success': True, 'message': 'Entry deleted'}

        elif path == '/api/esg/liff/categories' and method == 'GET':
            return esg_service.list_categories(query_params.get('pillar'))

        elif path == '/api/esg/liff/subcategories' and method == 'GET':
            category_id = query_params.get('category_id')
            return esg_service.list_subcategories(
                category_id=int(category_id) if category_id else None,
                pillar=query_params.get('pillar'),
            )

        elif path == '/api/esg/liff/settings' and method == 'GET':
            return esg_service.get_settings(current_user_org_id)

        elif path == '/api/esg/liff/export' and method == 'POST':
            fmt = (data or {}).get('format', 'xlsx')
            export_service = EsgExportService(db_session)
            if fmt == 'pdf':
                return export_service.export_to_pdf(current_user_org_id)
            return export_service.export_to_excel(current_user_org_id)

        elif path == '/api/esg/liff/upload-url' and method == 'POST':
            if not data or not data.get('file_name'):
                raise BadRequestException('file_name is required')
            return _handle_upload_url(data, current_user_id, current_user_org_id, db_session)

        # ===== LIFF INVITATION =====
        elif path == '/api/esg/liff/invitation/accept' and method == 'POST':
            if not data or not data.get('invitation_token') or not data.get('access_token'):
                raise BadRequestException('invitation_token and access_token are required')
            liff_svc = LiffAuthService(db_session)
            try:
                return liff_svc.accept_invitation(data['invitation_token'], data['access_token'])
            except ValueError as ve:
                raise BadRequestException(str(ve))

        # ===== ESG INVITATION MANAGEMENT (desktop) =====
        elif path == '/api/esg/invitations' and method == 'POST':
            liff_svc = LiffAuthService(db_session)
            return liff_svc.generate_invitation(current_user_org_id, int(current_user_id))

        elif path == '/api/esg/invitations' and method == 'GET':
            liff_svc = LiffAuthService(db_session)
            return liff_svc.list_invitations(current_user_org_id)

        # ===== LINE MEMBER MANAGEMENT (desktop) =====
        elif path == '/api/esg/line-members' and method == 'GET':
            liff_svc = LiffAuthService(db_session)
            return liff_svc.list_line_members(current_user_org_id)

        elif '/api/esg/line-members/' in path and method == 'DELETE':
            member_id = _extract_id_from_path(path, 'line-members')
            liff_svc = LiffAuthService(db_session)
            try:
                return liff_svc.remove_line_member(current_user_org_id, member_id)
            except ValueError as ve:
                raise NotFoundException(str(ve))

        # ===== LEGACY DASHBOARD (keep for backward compat) =====
        elif path == '/api/dashboard/summary' and method == 'GET':
            dash = EsgDashboardService(db_session)
            return dash.get_summary(current_user_org_id)

        elif path == '/api/dashboard/charts' and method == 'GET':
            dash = EsgDashboardService(db_session)
            year = int(query_params.get('year', 0)) or None
            return dash.get_charts(current_user_org_id, year)

        # ===== SETTINGS =====
        if path == '/api/esg/settings' and method == 'GET':
            return esg_service.get_settings(current_user_org_id)

        elif path == '/api/esg/settings' and method == 'POST':
            return esg_service.update_settings(current_user_org_id, data or {})

        # ===== ORG SETUP =====
        elif path == '/api/esg/org-setup' and method == 'GET':
            return esg_service.get_org_setup(current_user_org_id)

        elif path == '/api/esg/org-setup' and method == 'POST':
            return esg_service.update_org_setup(current_user_org_id, data or {})

        # ===== PLATFORM BINDINGS =====
        elif path == '/api/esg/platform-bindings' and method == 'GET':
            return esg_service.list_platform_bindings(current_user_org_id)

        elif path == '/api/esg/platform-bindings' and method == 'POST':
            if not data:
                raise BadRequestException('Request body is required')
            return esg_service.create_platform_binding(current_user_org_id, data)

        elif path == '/api/esg/platform-bindings/pair' and method == 'POST':
            if not data or not data.get('pairing_code'):
                raise BadRequestException('pairing_code is required')
            line_service = EsgLineService(db_session)
            return line_service.pair_group_by_code(current_user_org_id, data['pairing_code'])

        elif '/api/esg/platform-bindings/' in path and '/groups/' in path and method == 'DELETE':
            parts = path.split('/')
            binding_id = int(parts[parts.index('platform-bindings') + 1])
            group_id = parts[parts.index('groups') + 1]
            return esg_service.remove_authorized_group(binding_id, current_user_org_id, group_id)

        elif '/api/esg/platform-bindings/' in path and '/groups' in path and method == 'POST':
            binding_id = _extract_id_from_path(path, 'platform-bindings')
            if not data:
                raise BadRequestException('Request body is required')
            return esg_service.add_authorized_group(binding_id, current_user_org_id, data)

        elif '/api/esg/platform-bindings/' in path and method == 'PUT':
            binding_id = _extract_id_from_path(path, 'platform-bindings')
            if not data:
                raise BadRequestException('Request body is required')
            return esg_service.update_platform_binding(binding_id, current_user_org_id, data)

        # ===== DATA ENTRIES =====
        elif path == '/api/esg/data-entries' and method == 'POST':
            if not data:
                raise BadRequestException('Request body is required')
            entry_service = EsgDataEntryService(db_session)
            return entry_service.create_entry(current_user_org_id, int(current_user_id), data)

        elif path == '/api/esg/data-entries' and method == 'GET':
            entry_service = EsgDataEntryService(db_session)
            return entry_service.list_entries(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                size=min(int(query_params.get('size', 10)), 100),
            )

        elif '/api/esg/data-entries/' in path and method == 'GET':
            entry_id = _extract_id_from_path(path, 'data-entries')
            entry_service = EsgDataEntryService(db_session)
            result = entry_service.get_entry(entry_id, current_user_org_id)
            if not result:
                raise NotFoundException('Data entry not found')
            return result

        elif '/api/esg/data-entries/' in path and method == 'PUT':
            entry_id = _extract_id_from_path(path, 'data-entries')
            if not data:
                raise BadRequestException('Request body is required')
            entry_service = EsgDataEntryService(db_session)
            result = entry_service.update_entry(entry_id, current_user_org_id, data)
            if not result:
                raise NotFoundException('Data entry not found')
            return result

        elif '/api/esg/data-entries/' in path and method == 'DELETE':
            entry_id = _extract_id_from_path(path, 'data-entries')
            entry_service = EsgDataEntryService(db_session)
            deleted = entry_service.delete_entry(entry_id, current_user_org_id)
            if not deleted:
                raise NotFoundException('Data entry not found')
            return {'success': True, 'message': 'Entry deleted'}

        # ===== UPLOAD URL =====
        elif path == '/api/esg/upload-url' and method == 'POST':
            if not data or not data.get('file_name'):
                raise BadRequestException('file_name is required')
            return _handle_upload_url(data, current_user_id, current_user_org_id, db_session)

        # ===== VERIFY =====
        elif '/api/esg/data-entries/' in path and '/verify' in path and method == 'POST':
            entry_id = _extract_id_from_path(path, 'data-entries')
            entry_service = EsgDataEntryService(db_session)
            result = entry_service.verify_entry(entry_id, current_user_org_id)
            if not result:
                raise NotFoundException('Data entry not found')
            return result

        # ===== EXPORT =====
        elif path == '/api/esg/export' and method == 'POST':
            fmt = (data or {}).get('format', 'xlsx')
            export_service = EsgExportService(db_session)
            if fmt == 'pdf':
                return export_service.export_to_pdf(current_user_org_id)
            return export_service.export_to_excel(current_user_org_id)

        # ===== EMISSION FACTORS =====
        elif path == '/api/esg/emission-factors' and method == 'GET':
            carbon_svc = EsgCarbonService(db_session)
            return carbon_svc.list_factors(query_params.get('category'))

        # ===== NOTIFICATION (cron) =====
        elif path == '/api/esg/notifications/send-reminders' and method == 'POST':
            notif = EsgNotificationService(db_session)
            return notif.send_monthly_reminders()

        # ===== LINE WEBHOOK (public, no JWT) =====
        elif path == '/api/esg/line/webhook' and method == 'POST':
            raw_body = event.get('body', '')
            signature = (event.get('headers', {}) or {}).get('x-line-signature', '')
            line_service = EsgLineService(db_session)
            return line_service.handle_webhook(raw_body, signature)

        # ===== DATA HIERARCHY =====
        elif path == '/api/esg/categories' and method == 'GET':
            return esg_service.list_categories(query_params.get('pillar'))

        elif path == '/api/esg/subcategories' and method == 'GET':
            category_id = query_params.get('category_id')
            return esg_service.list_subcategories(
                category_id=int(category_id) if category_id else None,
                pillar=query_params.get('pillar'),
            )

        elif path == '/api/esg/datapoints' and method == 'GET':
            subcategory_id = query_params.get('subcategory_id')
            return esg_service.list_datapoints(
                subcategory_id=int(subcategory_id) if subcategory_id else None,
                pillar=query_params.get('pillar'),
            )

        # ===== COMPLETENESS & POSITIONING =====
        elif path == '/api/esg/completeness' and method == 'GET':
            return esg_service.get_data_completeness(current_user_org_id)

        elif path == '/api/esg/positioning' and method == 'GET':
            return esg_service.get_esg_positioning(current_user_org_id)

        # ===== EXTRACTIONS =====
        elif path == '/api/esg/extractions' and method == 'GET':
            return esg_service.list_extractions(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                page_size=min(int(query_params.get('page_size', 20)), 100),
                channel=query_params.get('channel'),
                status=query_params.get('status'),
            )

        elif '/api/esg/extractions/' in path and method == 'GET':
            extraction_id = _extract_id_from_path(path, 'extractions')
            return esg_service.get_extraction(extraction_id, current_user_org_id)

        # ===== IDEAS =====
        elif path == '/api/esg/ideas' and method == 'GET':
            ideas_service = EsgIdeasService(db_session)
            return ideas_service.get_ideas(current_user_org_id)

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


def _handle_upload_url(data, current_user_id, current_user_org_id, db_session):
    """Generate a single pre-signed S3 upload URL for data entry evidence"""
    import boto3
    import uuid
    import os
    from datetime import datetime

    file_name = data['file_name']
    content_type = data.get('content_type', 'application/octet-stream')
    line_user_id = data.get('line_user_id', 'web')

    s3 = boto3.client('s3')
    bucket = os.environ.get('S3_BUCKET_NAME', 'prod-gepp-platform-assets')
    ext = file_name.rsplit('.', 1)[-1] if '.' in file_name else 'bin'
    date_str = datetime.utcnow().strftime('%Y%m%d')
    hash_id = uuid.uuid4().hex[:12]
    file_key = f'esg/org/{current_user_org_id}/LINE/{line_user_id}/{date_str}_{hash_id}.{ext}'

    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': bucket,
            'Key': file_key,
            'ContentType': content_type,
        },
        ExpiresIn=3600,
    )

    return {
        'success': True,
        'upload_url': upload_url,
        'file_key': file_key,
        'expires_in': 3600,
    }


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
