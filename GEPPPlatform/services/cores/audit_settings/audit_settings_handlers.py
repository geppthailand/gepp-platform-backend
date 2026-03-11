"""
Audit Settings API Handlers
Handles HTTP requests for AI audit configuration (doc types, doc requires, check columns, column details)
"""

import json
from typing import Dict, Any

from .audit_settings_service import AuditSettingsService
from ....exceptions import APIException, NotFoundException, BadRequestException


def handle_audit_settings_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')

    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    service = AuditSettingsService(db_session)

    current_user = params.get('current_user', {})
    org_id = current_user.get('organization_id')

    # GET /api/audit-settings/document-types
    if '/document-types' in path and method == 'GET':
        return {'success': True, 'data': service.get_document_types()}

    # GET /api/audit-settings/column-details
    elif '/column-details' in path and method == 'GET':
        return {'success': True, 'data': service.get_column_details()}

    # GET /api/audit-settings/doc-requires
    elif '/doc-requires' in path and method == 'GET':
        if not org_id:
            raise BadRequestException('Organization ID not found in user context')
        return {'success': True, 'data': service.get_doc_require_types(org_id)}

    # PUT /api/audit-settings/doc-requires
    elif '/doc-requires' in path and method == 'PUT':
        if not org_id:
            raise BadRequestException('Organization ID not found in user context')
        result = service.update_doc_require_types(org_id, data)
        return {'success': True, 'data': result, 'message': 'Document requirements updated'}

    # GET /api/audit-settings/check-columns
    elif '/check-columns' in path and method == 'GET':
        if not org_id:
            raise BadRequestException('Organization ID not found in user context')
        return {'success': True, 'data': service.get_check_columns(org_id)}

    # PUT /api/audit-settings/check-columns
    elif '/check-columns' in path and method == 'PUT':
        if not org_id:
            raise BadRequestException('Organization ID not found in user context')
        result = service.update_check_columns(org_id, data)
        return {'success': True, 'data': result, 'message': 'Check columns updated'}

    else:
        raise NotFoundException(f'Route not found: {path} [{method}]')
