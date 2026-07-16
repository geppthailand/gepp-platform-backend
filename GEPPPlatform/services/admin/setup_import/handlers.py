"""
Route dispatch for the back-office "Import Organization Setup" endpoints.

All routes are org-scoped under the admin namespace and operate on the *target* org DB
(resolved via db_target_resolver, same as the transactions-export route):

  POST /admin/organizations/{id}/setup-import                     upload (base64 xlsx)
  POST /admin/organizations/{id}/setup-import/{importId}/extract  parse + validate → preview
  POST /admin/organizations/{id}/setup-import/{importId}/confirm  create everything (body: edited preview)
  POST /admin/organizations/{id}/setup-import/{importId}/revert   soft-delete + strip nodes
  GET  /admin/organizations/{id}/setup-imports                    version/history list
"""

import base64
from typing import Any, Dict, List, Optional

from ....exceptions import BadRequestException, NotFoundException
from .setup_import_service import SetupImportService


def _decode_file(data: Dict[str, Any]) -> bytes:
    b64 = data.get('file_base64') or data.get('file')
    if not b64:
        raise BadRequestException('file_base64 is required')
    if isinstance(b64, str) and ',' in b64[:64] and 'base64' in b64[:64]:
        b64 = b64.split(',', 1)[1]  # tolerate a data-URI prefix
    try:
        return base64.b64decode(b64)
    except Exception as e:
        raise BadRequestException(f'Invalid base64 file data: {e}')


def handle_setup_import_route(
    method: str,
    path_parts: List[str],
    data: Dict[str, Any],
    query_params: Dict[str, Any],
    db_session,
    current_user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """`path_parts` is the /api/admin-stripped segments, e.g. ['organizations','3','setup-import']."""
    data = data or {}
    query_params = query_params or {}
    admin_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')
    organization_id = int(path_parts[1])

    # Resolve the target org DB (same pattern as transactions-export).
    from ..db_target_resolver import session_for_target
    target = query_params.get('dbTarget') or 'local'
    try:
        session, owns = session_for_target(target, db_session)
    except PermissionError as e:
        raise BadRequestException(str(e))

    try:
        service = SetupImportService(session)

        # GET .../setup-imports  → history list
        if method == 'GET' and len(path_parts) == 3 and path_parts[2] == 'setup-imports':
            return service.list_history(organization_id)

        if method == 'POST' and len(path_parts) == 3 and path_parts[2] == 'setup-import':
            return service.upload(
                organization_id, admin_id,
                data.get('filename') or 'organization_setup.xlsx',
                _decode_file(data), data.get('content_type'),
            )

        if method == 'POST' and len(path_parts) == 5 and path_parts[2] == 'setup-import':
            import_id = int(path_parts[3])
            action = path_parts[4]
            if action == 'extract':
                return service.extract(import_id, organization_id)
            if action == 'confirm':
                return service.confirm(import_id, organization_id, admin_id, data.get('preview'))
            if action == 'revert':
                return service.revert(import_id, organization_id)

        raise NotFoundException(f"Setup-import endpoint not found: {method} {'/'.join(path_parts)}")
    finally:
        if owns:
            session.close()
