"""
ESG API Handlers — Route dispatch for all ESG endpoints
"""

from typing import Dict, Any, Optional
from datetime import datetime
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
from .materiality_service import MaterialityService
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
        # Every LIFF endpoint is scoped to the current LINE user — they
        # see their own dashboard / history / report only. The org-wide
        # view stays on the desktop platform under /api/esg/* (no /liff
        # prefix).
        liff_user_id = int(current_user_id) if current_user_id else None

        if path == '/api/esg/liff/report' and method == 'GET':
            from .esg_report_service import EsgReportService
            report_svc = EsgReportService(db_session)
            year = int(query_params.get('year', 0)) or None
            view = query_params.get('view', 'executive')
            lang = (query_params.get('lang') or 'en').lower()
            return report_svc.get_report(
                current_user_org_id,
                year=year,
                view=view,
                user_id=liff_user_id,
                lang='th' if lang.startswith('th') else 'en',
            )

        elif path == '/api/esg/liff/summary' and method == 'GET':
            dash = EsgDashboardService(db_session)
            return dash.get_summary(current_user_org_id, user_id=liff_user_id)

        elif path == '/api/esg/liff/charts' and method == 'GET':
            dash = EsgDashboardService(db_session)
            year = int(query_params.get('year', 0)) or None
            return dash.get_charts(current_user_org_id, year, user_id=liff_user_id)

        elif path == '/api/esg/liff/entries' and method == 'GET':
            entry_service = EsgDataEntryService(db_session)
            return entry_service.list_entries(
                organization_id=current_user_org_id,
                page=int(query_params.get('page', 1)),
                size=min(int(query_params.get('size', 10)), 100),
                status=query_params.get('status'),
                user_id=liff_user_id,
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

        # ===== TGO-FORMAT SCOPE 3 EXPORT =====
        # Two routes (LIFF + desktop) hitting the same service. Body:
        #   { year: int, scope3_category_id?: int (1..15) }
        # When `scope3_category_id` is omitted, the workbook contains
        # all 15 detail sheets; when set, just that one sheet + a
        # 1-row summary block. Audit-grade, org-wide.
        elif path in ('/api/esg/liff/scope3-export', '/api/esg/scope3-export') and method == 'POST':
            from .esg_scope3_export_service import EsgScope3ExportService
            from ...models.esg.esg_users import EsgUser
            body = data or {}
            year = body.get('year')
            try:
                year = int(year) if year else datetime.utcnow().year
            except (TypeError, ValueError):
                raise BadRequestException('`year` must be an integer')
            cat = body.get('scope3_category_id') or body.get('cat')
            try:
                cat = int(cat) if cat else None
            except (TypeError, ValueError):
                cat = None
            if cat is not None and not (1 <= cat <= 15):
                raise BadRequestException('`scope3_category_id` must be 1..15')

            # Optional LINE-chat delivery. Body: { delivery: 'line_chat' }.
            # Resolves the JWT user → EsgUser → platform_user_id so we can
            # call the LINE Push API. When delivery is missing or no LINE
            # binding exists, fall back to the regular S3 download URL.
            push_target: Optional[str] = None
            delivery = (body.get('delivery') or '').strip().lower()
            if delivery == 'line_chat' and current_user_id:
                try:
                    line_user = (
                        db_session.query(EsgUser)
                        .filter(
                            EsgUser.id == int(current_user_id),
                            EsgUser.platform == 'line',
                        )
                        .first()
                    )
                    if line_user and line_user.platform_user_id:
                        push_target = line_user.platform_user_id
                except Exception:
                    logger.exception('Could not resolve LINE id for push')

            svc = EsgScope3ExportService(db_session)
            return svc.export(
                organization_id=current_user_org_id,
                year=year,
                scope3_category_id=cat,
                push_to_line_user_id=push_target,
            )

        elif path == '/api/esg/liff/upload-url' and method == 'POST':
            if not data or not data.get('file_name'):
                raise BadRequestException('file_name is required')
            return _handle_upload_url(data, current_user_id, current_user_org_id, db_session)

        # ===== AI EXTRACTION FROM UPLOADED IMAGE =====
        # Used by /data-entry (desktop) and /liff/app/entry?category=N
        # to mirror the LINE-chat image-upload flow. Caller first
        # uploads the file via /upload-url, then POSTs the file_key
        # here. We run the same extraction pipeline that the LINE
        # webhook uses and return the resulting EsgRecord rows.
        elif path == '/api/esg/extract-image' and method == 'POST':
            if not data or not data.get('file_key'):
                raise BadRequestException('file_key is required')
            return _handle_extract_image(
                data, current_user_id, current_user_org_id, db_session,
            )


        # ===== PRESIGNED VIEW URL =====
        elif path == '/api/esg/presigned-view' and method == 'POST':
            if not data or not data.get('s3_url'):
                raise BadRequestException('s3_url is required')
            return _handle_presigned_view(data['s3_url'])

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
            return liff_svc.list_members(current_user_org_id)

        elif '/api/esg/line-members/' in path and method == 'DELETE':
            member_id = _extract_id_from_path(path, 'line-members')
            liff_svc = LiffAuthService(db_session)
            try:
                return liff_svc.remove_member(current_user_org_id, member_id)
            except ValueError as ve:
                raise NotFoundException(str(ve))

        # ===== LEGACY DASHBOARD (keep for backward compat) =====
        elif path == '/api/dashboard/summary' and method == 'GET':
            dash = EsgDashboardService(db_session)
            return dash.get_summary(
                current_user_org_id,
                jwt_user_id=int(current_user_id) if current_user_id else None,
            )

        elif path == '/api/dashboard/charts' and method == 'GET':
            dash = EsgDashboardService(db_session)
            year = int(query_params.get('year', 0)) or None
            return dash.get_charts(
                current_user_org_id, year,
                jwt_user_id=int(current_user_id) if current_user_id else None,
            )

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

        # ===== DATA WAREHOUSE =====
        elif path == '/api/esg/data-warehouse/hierarchy' and method == 'GET':
            return esg_service.get_data_warehouse_hierarchy(current_user_org_id)

        elif '/api/esg/data-warehouse/datapoint/' in path and '/records' in path and method == 'GET':
            # GET /api/esg/data-warehouse/datapoint/{id}/records
            dp_id = int(path.split('/datapoint/')[1].split('/records')[0])
            return esg_service.get_datapoint_records(current_user_org_id, dp_id)

        elif '/api/esg/data-warehouse/scope3/' in path and '/records' in path and method == 'GET':
            # GET /api/esg/data-warehouse/scope3/{1..15}/records
            # Returns records grouped by record_label for the modal table.
            scope3_cat_id = int(path.split('/scope3/')[1].split('/records')[0])
            return esg_service.get_scope3_category_records(
                current_user_org_id, scope3_cat_id
            )

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

        # ===== Materiality Filter =====
        elif path == '/api/esg/materiality/me' and method == 'GET':
            if not current_user_id or not current_user_org_id:
                raise UnauthorizedException('User context required')
            mat = MaterialityService(db_session)
            state = mat.get_state(int(current_user_id), int(current_user_org_id))
            return {'success': True, 'data': state}

        elif path == '/api/esg/materiality/me' and method == 'PATCH':
            if not current_user_id or not current_user_org_id:
                raise UnauthorizedException('User context required')
            if not data:
                raise BadRequestException('Request body is required')
            mat = MaterialityService(db_session)
            state = mat.patch_progress(
                int(current_user_id),
                int(current_user_org_id),
                data.get('answers') or {},
                data.get('lastQuestionId'),
            )
            return {'success': True, 'data': state}

        elif path == '/api/esg/materiality/me/complete' and method == 'POST':
            if not current_user_id or not current_user_org_id:
                raise UnauthorizedException('User context required')
            if not data:
                raise BadRequestException('Request body is required')
            mat = MaterialityService(db_session)
            result = mat.complete(
                int(current_user_id),
                int(current_user_org_id),
                data.get('answers') or {},
                submitter_name=data.get('submitterName')
                              or data.get('submitter_name'),
            )
            return {'success': True, 'data': result}

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


def _handle_presigned_view(s3_url: str):
    """Generate a presigned GET URL for viewing an S3 file."""
    from ...prompts.esg_classify.clients.llm_client import _get_s3_presigned_url
    if not s3_url.startswith('s3://'):
        raise BadRequestException('Invalid S3 URL format')
    presigned = _get_s3_presigned_url(s3_url, expiration=3600)
    return {'success': True, 'url': presigned, 'expires_in': 3600}


def _handle_upload_url(data, current_user_id, current_user_org_id, db_session):
    """
    Generate a presigned POST for ESG evidence upload.

    Uses the same `TransactionPresignedUrlService` the transactions
    module uses — that flow is browser-friendly (form POST with
    `upload_fields`, not raw PUT) and the bucket CORS is already wired
    for it. Frontend posts a multipart FormData built from
    `upload_fields` + the file.
    """
    from ..cores.transactions.presigned_url_service import TransactionPresignedUrlService

    file_name = data['file_name']
    presigned_service = TransactionPresignedUrlService()
    result = presigned_service.get_transaction_file_upload_presigned_urls(
        file_names=[file_name],
        organization_id=current_user_org_id,
        user_id=int(current_user_id) if current_user_id else 0,
        db=db_session,
        # `FileType.document` is the closest existing enum value for
        # ESG evidence (receipts, invoices, manifests). Adding a new
        # enum value would need a DB migration, which we skip here.
        file_type='document',
        related_entity_type='esg_record',
        expiration_seconds=3600,
    )
    if not result.get('success') or not result.get('presigned_urls'):
        raise BadRequestException(result.get('message') or 'failed to generate upload URL')
    item = result['presigned_urls'][0]
    return {
        'success': True,
        # Browser POSTs to `upload_url` with FormData containing each
        # `upload_fields` entry + the file as the last field.
        'upload_url': item['upload_url'],
        'upload_fields': item['upload_fields'],
        'file_key': item['s3_key'],
        # Final S3 URL once the upload completes — what we hand to the
        # extraction service as `s3_url`.
        'final_s3_url': item['final_s3_url'],
        'expires_in': 3600,
    }


def _handle_extract_image(data, current_user_id, current_user_org_id, db_session):
    """
    Run the same AI extraction pipeline the LINE webhook uses on a
    user-uploaded image, then return the persisted EsgRecord rows.

    Caller flow:
      1) POST /api/esg/liff/upload-url    → { upload_url, file_key }
      2) PUT  upload_url with the image bytes
      3) POST /api/esg/extract-image      → { records, summary }

    Body:
      file_key (str, required)         — S3 key returned in step 1
      category_hint (int, optional)    — Scope 3 category 1..15 the user
                                         picked on the form. Currently
                                         used for telemetry; the LLM
                                         still classifies on its own.
    """
    from .esg_image_extraction_service import EsgImageExtractionService
    import os

    file_key = data['file_key']
    # The downstream LLM client (`_call_llm_with_images`) only
    # presigns URLs that start with `s3://`; anything else (including
    # the public HTTPS URL the presigned-POST flow returns) gets
    # passed verbatim and Gemini hits 403 on the private bucket.
    # Always normalise to `s3://bucket/key` here, identical to how
    # the LINE webhook passes the image.
    bucket = os.environ.get('S3_BUCKET_NAME', 'prod-gepp-platform-assets')
    if file_key.startswith('s3://'):
        s3_url = file_key
    elif file_key.startswith('http'):
        # Strip protocol + host; what's left is the key.
        from urllib.parse import urlparse
        parsed = urlparse(file_key)
        host_bucket = parsed.netloc.split('.')[0] if parsed.netloc else bucket
        key = parsed.path.lstrip('/')
        s3_url = f's3://{host_bucket}/{key}'
    else:
        s3_url = f's3://{bucket}/{file_key.lstrip("/")}'

    # `line_user_id` is the EsgRecord owner column we filter LIFF
    # history on. For desktop / LIFF-form uploads we don't have a LINE
    # platform_user_id, so we tag with a synthetic identifier that the
    # downstream queries can still match on.
    line_user_id = (data.get('line_user_id') or '').strip()
    if not line_user_id and current_user_id:
        line_user_id = f'user-{current_user_id}'

    svc = EsgImageExtractionService(db_session)
    result = svc.extract_from_image(
        s3_url=s3_url,
        org_id=current_user_org_id,
        line_user_id=line_user_id,
        message_id=f'web-{current_user_id}-{file_key[-12:]}',
    )
    # Trim down — frontend only needs the records + refs + extraction id
    return {
        'success': bool(result.get('success')),
        'extraction_id': result.get('extraction_id'),
        'records': result.get('records') or [],
        'refs': result.get('refs') or {},
        'message': result.get('message') or 'extraction complete',
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
