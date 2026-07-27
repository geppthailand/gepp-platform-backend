"""
Import API handlers — Excel bulk-import of waste transactions.

Routes (all scoped to the authenticated user's org):
    POST /api/import-files              upload a file (base64-in-JSON) → import_files row
    POST /api/import-files/{id}/extract parse + fuzzy-match → preview_payload
    GET  /api/import-files/{id}         fetch the preview (review step / reopen)
    POST /api/import-files/{id}/confirm create grouped transactions from the (edited) rows
    POST /api/import-files/{id}/revert  soft-delete the whole upload's transactions
    GET  /api/import-files[?type=]      upload history

The Lambda dispatcher is JSON-only, so the file arrives as base64 in the body (field
`file_base64`), mirroring the existing transaction-file convention.
"""

import base64
import logging
from typing import Any, Dict

from .import_service import ImportService

logger = logging.getLogger(__name__)

from ....exceptions import APIException, BadRequestException, UnauthorizedException


def handle_import_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {}) or {}

    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    current_user = params.get('current_user', {}) or {}
    user_id = current_user.get('user_id')
    organization_id = current_user.get('organization_id')
    if not user_id or not organization_id:
        raise UnauthorizedException('Authentication required')

    service = ImportService(db_session)
    data = data or {}

    # Template download — GET /api/import-files/template?with_destination=true|false.
    # Handled before id-parsing since "template" is not a numeric import_file_id.
    if method == 'GET' and path.rstrip('/').endswith('/template'):
        with_destination = str(query_params.get('with_destination', '')).lower() in ('1', 'true', 'yes')
        return service.get_template(with_destination=with_destination)

    # Parse path → import_file_id + action.
    segments = [s for s in path.strip('/').split('/') if s]  # e.g. ['api','import-files','12','extract']
    import_file_id = None
    action = None
    if len(segments) >= 3:
        try:
            import_file_id = int(segments[2])
        except (TypeError, ValueError):
            import_file_id = None
    if len(segments) >= 4:
        action = segments[3]

    # ── Collection routes ──────────────────────────────────────────────────────
    if import_file_id is None:
        if method == 'POST':
            return _handle_upload(service, data, organization_id, user_id)
        if method == 'GET':
            return service.list_history(organization_id, query_params.get('type'))
        raise BadRequestException(f'Unsupported method {method} for /api/import-files')

    # ── Item routes ─────────────────────────────────────────────────────────────
    if method == 'GET' and not action:
        return service.get_preview(import_file_id, organization_id)
    if method == 'POST' and action == 'extract':
        return service.extract(import_file_id, organization_id)
    if method == 'POST' and action == 'save':
        # Persist edited/deleted review rows without confirming (so reopening reflects them).
        return service.save_preview(import_file_id, organization_id, data.get('rows'))
    if method == 'POST' and action == 'confirm':
        rows = data.get('rows')
        return service.confirm(import_file_id, organization_id, user_id, rows)
    if method == 'POST' and action == 'revert':
        return service.revert(import_file_id, organization_id)
    if method == 'POST' and action == 'reimport':
        return service.reimport(import_file_id, organization_id)

    raise BadRequestException(f'Unsupported route: {method} {path}')


def _handle_upload(service: ImportService, data: Dict[str, Any], organization_id: int, user_id: int) -> Dict[str, Any]:
    file_b64 = data.get('file_base64') or data.get('file')
    filename = data.get('filename') or 'import.xlsx'
    content_type = data.get('content_type')
    import_type = data.get('type') or 'transaction'
    if not file_b64:
        raise BadRequestException('file_base64 is required')
    try:
        # Tolerate a data-URI prefix ("data:...;base64,....").
        if isinstance(file_b64, str) and ',' in file_b64[:64] and 'base64' in file_b64[:64]:
            file_b64 = file_b64.split(',', 1)[1]
        file_bytes = base64.b64decode(file_b64)
    except Exception as e:
        raise BadRequestException(f'Invalid base64 file data: {e}')
    return service.upload_file(
        organization_id=organization_id,
        user_id=user_id,
        import_type=import_type,
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
    )
