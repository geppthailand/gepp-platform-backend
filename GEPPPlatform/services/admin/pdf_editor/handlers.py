"""
Route dispatch for the back-office PDF Editor (Documents tab).

  GET    /admin/pdf-editor/projects                         list (?search, page, pageSize)
  POST   /admin/pdf-editor/projects                         create {name, description?}
  GET    /admin/pdf-editor/projects/{id}                    project + signed source URL + state + history
  PUT    /admin/pdf-editor/projects/{id}                    rename {name?, description?}
  DELETE /admin/pdf-editor/projects/{id}                    soft delete
  POST   /admin/pdf-editor/projects/{id}/source             presigned POST for the source PDF {fileName, fileSize}
  POST   /admin/pdf-editor/projects/{id}/source/confirm     HEAD-verified → ready {pageCount}
  PUT    /admin/pdf-editor/projects/{id}/state              save {doc, history, baseVersion, label?, named?, force?}
  GET    /admin/pdf-editor/projects/{id}/revisions          saved versions
  GET    /admin/pdf-editor/projects/{id}/revisions/{rid}    one version's doc
  GET    /admin/pdf-editor/assets                           element bar (?projectId) = project + my library
  POST   /admin/pdf-editor/assets                           presigned POST {projectId?, scope, kind, name, mimeType, fileSize, width, height}
  POST   /admin/pdf-editor/assets/resolve                   signed URLs for ids a state places {projectId, ids}
  POST   /admin/pdf-editor/assets/{id}/confirm              HEAD-verified → ready
  PUT    /admin/pdf-editor/assets/{id}                      rename {name}
  DELETE /admin/pdf-editor/assets/{id}                      soft delete

Contract: gepp-new-webapp/src/pages/v3-documents-pdf-editor/api.ts
"""

from typing import Any, Dict, List, Optional

from ....exceptions import NotFoundException
from .service import PdfEditorService


def _int(v: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise NotFoundException('PDF editor endpoint not found')


def handle_pdf_editor_route(
    method: str,
    path_parts: List[str],
    data: Dict[str, Any],
    query_params: Dict[str, Any],
    db_session,
    current_user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """`path_parts` is the /api/admin-stripped segments, e.g. ['pdf-editor', 'projects', '3', 'state']."""
    svc = PdfEditorService(db_session, current_user)
    data = data or {}
    query_params = query_params or {}
    sub = path_parts[1] if len(path_parts) > 1 else ''
    rest = path_parts[2:]

    if sub == 'projects':
        if not rest:
            if method == 'GET':
                return svc.list_projects(query_params)
            if method == 'POST':
                return svc.create_project(data)
        else:
            pid = _int(rest[0])
            tail = rest[1:]
            if not tail:
                if method == 'GET':
                    return svc.get_project(pid)
                if method == 'PUT':
                    return svc.update_project(pid, data)
                if method == 'DELETE':
                    return svc.delete_project(pid)
            elif tail == ['source'] and method == 'POST':
                return svc.start_source_upload(pid, data)
            elif tail == ['source', 'confirm'] and method == 'POST':
                return svc.confirm_source(pid, data)
            elif tail == ['state'] and method == 'PUT':
                return svc.save_state(pid, data)
            elif tail == ['revisions'] and method == 'GET':
                return svc.list_revisions(pid)
            elif len(tail) == 2 and tail[0] == 'revisions' and method == 'GET':
                return svc.get_revision(pid, _int(tail[1]))

    elif sub == 'assets':
        if not rest:
            if method == 'GET':
                return svc.list_assets(query_params)
            if method == 'POST':
                return svc.start_asset_upload(data)
        elif rest == ['resolve'] and method == 'POST':
            return svc.resolve_assets(data)
        else:
            aid = _int(rest[0])
            tail = rest[1:]
            if tail == ['confirm'] and method == 'POST':
                return svc.confirm_asset(aid)
            if not tail and method == 'PUT':
                return svc.update_asset(aid, data)
            if not tail and method == 'DELETE':
                return svc.delete_asset(aid)

    raise NotFoundException(f"PDF editor endpoint not found: {method} /{'/'.join(path_parts)}")
