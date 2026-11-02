"""Back-office PDF Editor — projects, source PDF, element-bar assets, saved state.

The editor itself runs in the browser (pdf.js to render, pdf-lib to export). This
service keeps what must survive a reload and signs the S3 traffic:

* **Source PDF is write-once.** Saved deletions of original-page objects are
  addressed by operator index in that exact file; replacing it would re-point
  every one of them. A different PDF is a different project.
* **Saves are optimistic-locked.** Two admins on one project must not silently
  overwrite each other: the client sends the `version` it loaded, a mismatch is a
  409 and the UI asks whether to reload or overwrite (`force`).
* **Every save is a revision.** History lives in the browser session (and is
  persisted with the save, capped); revisions are what survive beyond it. Unnamed
  revisions are pruned to the newest `KEEP_UNNAMED_REVISIONS`; named ones never.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text as _t

from GEPPPlatform.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from . import storage

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_ASSET_BYTES = 10 * 1024 * 1024
#: The browser converts anything else (webp, gif, heic via canvas) to PNG before
#: upload — pdf-lib can embed exactly these two.
ASSET_MIME_TYPES = {'image/png': 'png', 'image/jpeg': 'jpg'}
ASSET_KINDS = ('image', 'signature', 'thumbnail')
#: Upper bound on one saved payload (doc + history). API Gateway stops at 6 MB;
#: failing here gives the editor a message it can show.
MAX_STATE_BYTES = 5 * 1024 * 1024
MAX_OBJECTS = 5000
MAX_HISTORY_ENTRIES = 200
KEEP_UNNAMED_REVISIONS = 30
#: Key of a removed original object: "12" = page content operator 12, "12>5" =
#: operator 5 of the form XObject drawn by operator 12 (nesting continues),
#: "a3" = annotation 3. Older states stored page operators as bare integers.
REMOVED_KEY_RE = re.compile(r'\d+(>\d+){0,8}|a\d+')


def _is_removed_key(key: Any) -> bool:
    if isinstance(key, bool):
        return False
    if isinstance(key, int):
        return key >= 0
    return isinstance(key, str) and len(key) <= 64 and REMOVED_KEY_RE.fullmatch(key) is not None


def _user_id(current_user: Optional[Dict[str, Any]]) -> Optional[int]:
    uid = (current_user or {}).get('user_id')
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _clean_name(raw: Any, field: str, required: bool = True) -> Optional[str]:
    value = raw.strip() if isinstance(raw, str) else ''
    if not value:
        if required:
            raise BadRequestException(f'{field} is required')
        return None
    return value[:255]


def _int_or_none(raw: Any) -> Optional[int]:
    try:
        return int(raw) if raw is not None and raw != '' else None
    except (TypeError, ValueError):
        return None


class PdfEditorService:
    def __init__(self, db_session, current_user: Optional[Dict[str, Any]] = None):
        self.db = db_session
        self.current_user = current_user or {}
        self.user_id = _user_id(current_user)

    # ── helpers ─────────────────────────────────────────────────────────

    def _user_names(self, ids) -> Dict[int, str]:
        ids = {int(i) for i in ids if i}
        if not ids:
            return {}
        try:
            rows = self.db.execute(_t(
                "SELECT id, display_name, email FROM user_locations WHERE id = ANY(:ids)"
            ), {'ids': list(ids)}).fetchall()
            return {int(r[0]): (r[1] or r[2] or f'#{r[0]}') for r in rows}
        except Exception:
            logger.warning('pdf-editor: could not resolve user names', exc_info=True)
            self.db.rollback()
            return {}

    def _project_row(self, project_id: int):
        row = self.db.execute(_t(
            "SELECT id, name, description, source_status, source_s3_bucket, source_s3_key, "
            "       source_file_name, source_file_size, page_count, thumbnail_asset_id, "
            "       state, history, version, created_by_id, updated_by_id, "
            "       created_date, updated_date "
            "  FROM pdf_editor_projects WHERE id = :id AND deleted_date IS NULL"
        ), {'id': project_id}).mappings().fetchone()
        if row is None:
            raise NotFoundException(f'PDF project {project_id} not found')
        return row

    def _asset_view(self, r, names: Dict[int, str]) -> Dict[str, Any]:
        url = None
        if r['status'] == 'ready':
            try:
                url = storage.presign_get(r['s3_key'], r['mime_type'], bucket=r['s3_bucket'])
            except Exception:
                logger.warning('pdf-editor: could not sign asset %s', r['id'], exc_info=True)
        return {
            'id': int(r['id']),
            'projectId': int(r['project_id']) if r['project_id'] else None,
            'scope': r['scope'],
            'kind': r['kind'],
            'name': r['name'],
            'status': r['status'],
            'mimeType': r['mime_type'],
            'fileSize': int(r['file_size']) if r['file_size'] is not None else None,
            'width': r['width'],
            'height': r['height'],
            'url': url,
            'createdById': r['created_by_id'],
            'createdByName': names.get(int(r['created_by_id'])) if r['created_by_id'] else None,
            'createdDate': _iso(r['created_date']),
        }

    def _asset_row(self, asset_id: int):
        row = self.db.execute(_t(
            "SELECT id, project_id, scope, kind, name, status, s3_bucket, s3_key, mime_type, "
            "       file_size, width, height, created_by_id, created_date "
            "  FROM pdf_editor_assets WHERE id = :id AND deleted_date IS NULL"
        ), {'id': asset_id}).mappings().fetchone()
        if row is None:
            raise NotFoundException(f'Asset {asset_id} not found')
        # A library asset is somebody's signature: only its owner sees or changes it.
        if row['scope'] == 'library' and row['created_by_id'] != self.user_id:
            raise NotFoundException(f'Asset {asset_id} not found')
        return row

    # ── projects ────────────────────────────────────────────────────────

    def list_projects(self, query: Dict[str, Any]) -> Dict[str, Any]:
        page = max(1, _int_or_none(query.get('page')) or 1)
        page_size = min(100, max(1, _int_or_none(query.get('pageSize')) or 24))
        search = (query.get('search') or '').strip()

        where = "p.deleted_date IS NULL"
        params: Dict[str, Any] = {'limit': page_size, 'offset': (page - 1) * page_size}
        if search:
            where += " AND (p.name ILIKE :q OR p.source_file_name ILIKE :q OR p.description ILIKE :q)"
            params['q'] = f'%{search}%'

        total = int(self.db.execute(_t(
            f"SELECT COUNT(*) FROM pdf_editor_projects p WHERE {where}"), params).scalar() or 0)

        rows = self.db.execute(_t(
            "SELECT p.id, p.name, p.description, p.source_status, p.source_file_name, "
            "       p.source_file_size, p.page_count, p.version, p.created_by_id, "
            "       p.updated_by_id, p.created_date, p.updated_date, "
            "       COALESCE(jsonb_array_length(CASE WHEN jsonb_typeof(p.state->'objects') = 'array' "
            "                THEN p.state->'objects' END), 0) AS object_count, "
            "       t.s3_key AS thumb_key, t.s3_bucket AS thumb_bucket, t.mime_type AS thumb_mime "
            "  FROM pdf_editor_projects p "
            "  LEFT JOIN pdf_editor_assets t "
            "         ON t.id = p.thumbnail_asset_id AND t.deleted_date IS NULL AND t.status = 'ready' "
            f" WHERE {where} "
            " ORDER BY p.updated_date DESC, p.id DESC "
            " LIMIT :limit OFFSET :offset"
        ), params).mappings().fetchall()

        names = self._user_names([r['created_by_id'] for r in rows] + [r['updated_by_id'] for r in rows])
        items = []
        for r in rows:
            thumb = None
            if r['thumb_key']:
                try:
                    thumb = storage.presign_get(r['thumb_key'], r['thumb_mime'], bucket=r['thumb_bucket'])
                except Exception:
                    thumb = None
            items.append({
                'id': int(r['id']),
                'name': r['name'],
                'description': r['description'],
                'sourceStatus': r['source_status'],
                'sourceFileName': r['source_file_name'],
                'sourceFileSize': int(r['source_file_size']) if r['source_file_size'] is not None else None,
                'pageCount': r['page_count'],
                'objectCount': int(r['object_count'] or 0),
                'version': r['version'],
                'thumbnailUrl': thumb,
                'createdByName': names.get(r['created_by_id']) if r['created_by_id'] else None,
                'updatedByName': names.get(r['updated_by_id']) if r['updated_by_id'] else None,
                'createdDate': _iso(r['created_date']),
                'updatedDate': _iso(r['updated_date']),
            })
        return {'items': items, 'total': total, 'page': page, 'pageSize': page_size}

    def create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = _clean_name(data.get('name'), 'name')
        description = data.get('description')
        description = description.strip()[:2000] if isinstance(description, str) and description.strip() else None
        row = self.db.execute(_t(
            "INSERT INTO pdf_editor_projects (name, description, created_by_id, updated_by_id) "
            "VALUES (:name, :description, :uid, :uid) RETURNING id"
        ), {'name': name, 'description': description, 'uid': self.user_id}).fetchone()
        self.db.commit()
        return self.get_project(int(row[0]))

    def get_project(self, project_id: int) -> Dict[str, Any]:
        p = self._project_row(project_id)
        source_url = None
        if p['source_status'] == 'ready' and p['source_s3_key']:
            source_url = storage.presign_get(
                p['source_s3_key'], 'application/pdf', bucket=p['source_s3_bucket'])
        names = self._user_names([p['created_by_id'], p['updated_by_id']])
        return {
            'id': int(p['id']),
            'name': p['name'],
            'description': p['description'],
            'sourceStatus': p['source_status'],
            'sourceFileName': p['source_file_name'],
            'sourceFileSize': int(p['source_file_size']) if p['source_file_size'] is not None else None,
            'sourceUrl': source_url,
            'pageCount': p['page_count'],
            'state': p['state'] or {},
            'history': p['history'],
            'version': p['version'],
            'createdByName': names.get(p['created_by_id']) if p['created_by_id'] else None,
            'updatedByName': names.get(p['updated_by_id']) if p['updated_by_id'] else None,
            'createdDate': _iso(p['created_date']),
            'updatedDate': _iso(p['updated_date']),
            'limits': {
                'maxPdfBytes': MAX_PDF_BYTES,
                'maxAssetBytes': MAX_ASSET_BYTES,
                'maxStateBytes': MAX_STATE_BYTES,
            },
        }

    def update_project(self, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        self._project_row(project_id)
        sets, params = [], {'id': project_id, 'uid': self.user_id}
        if 'name' in data:
            sets.append('name = :name')
            params['name'] = _clean_name(data.get('name'), 'name')
        if 'description' in data:
            d = data.get('description')
            sets.append('description = :description')
            params['description'] = d.strip()[:2000] if isinstance(d, str) and d.strip() else None
        if not sets:
            raise BadRequestException('Nothing to update (name, description)')
        self.db.execute(_t(
            f"UPDATE pdf_editor_projects SET {', '.join(sets)}, updated_by_id = :uid, "
            "       updated_date = NOW() WHERE id = :id"
        ), params)
        self.db.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> Dict[str, Any]:
        self._project_row(project_id)
        self.db.execute(_t(
            "UPDATE pdf_editor_projects SET deleted_date = NOW(), updated_by_id = :uid WHERE id = :id"
        ), {'id': project_id, 'uid': self.user_id})
        self.db.commit()
        return {'id': project_id, 'deleted': True}

    # ── source PDF ──────────────────────────────────────────────────────

    def start_source_upload(self, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        p = self._project_row(project_id)
        if p['source_status'] == 'ready':
            raise ConflictException(
                'This project already has its PDF. Create a new project to edit a different file.')

        file_name = (data.get('fileName') or '').strip()
        if not file_name.lower().endswith('.pdf'):
            raise BadRequestException('Only .pdf files can be used as the source document')
        size = _int_or_none(data.get('fileSize'))
        if size is not None and size > MAX_PDF_BYTES:
            raise BadRequestException(
                f'"{file_name}" is {size / (1024 * 1024):.1f} MB; the limit is '
                f'{MAX_PDF_BYTES // (1024 * 1024)} MB.')

        key = storage.new_key('projects', project_id, 'source', ext='pdf')
        signed = storage.presign_upload(key, 'application/pdf', MAX_PDF_BYTES)
        self.db.execute(_t(
            "UPDATE pdf_editor_projects "
            "   SET source_status = 'pending', source_s3_bucket = :bucket, source_s3_key = :key, "
            "       source_file_name = :fname, updated_by_id = :uid, updated_date = NOW() "
            " WHERE id = :id"
        ), {'id': project_id, 'bucket': storage.bucket_name(), 'key': key,
            'fname': file_name[:512], 'uid': self.user_id})
        self.db.commit()
        return {**signed, 'contentType': 'application/pdf', 'maxBytes': MAX_PDF_BYTES}

    def confirm_source(self, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        p = self._project_row(project_id)
        if p['source_status'] == 'ready':
            return self.get_project(project_id)
        if p['source_status'] != 'pending' or not p['source_s3_key']:
            raise BadRequestException('No upload was started for this project')

        # Sized from S3, never from the browser: a client that never uploaded
        # cannot talk its way into a "ready" project.
        size = storage.head_size(p['source_s3_key'], bucket=p['source_s3_bucket'])
        if not size:
            raise BadRequestException('The PDF did not reach storage. Please upload it again.')

        page_count = _int_or_none(data.get('pageCount'))
        if page_count is None or page_count < 1 or page_count > 10000:
            raise BadRequestException('pageCount must be between 1 and 10000')

        self.db.execute(_t(
            "UPDATE pdf_editor_projects "
            "   SET source_status = 'ready', source_file_size = :size, page_count = :pages, "
            "       updated_by_id = :uid, updated_date = NOW() "
            " WHERE id = :id"
        ), {'id': project_id, 'size': size, 'pages': page_count, 'uid': self.user_id})
        self.db.commit()
        return self.get_project(project_id)

    # ── state / history / revisions ─────────────────────────────────────

    @staticmethod
    def _validate_doc(doc: Any) -> Dict[str, Any]:
        if not isinstance(doc, dict):
            raise BadRequestException('doc must be an object')
        objects = doc.get('objects', [])
        removed = doc.get('removed', {})
        if not isinstance(objects, list):
            raise BadRequestException('doc.objects must be a list')
        if len(objects) > MAX_OBJECTS:
            raise BadRequestException(f'At most {MAX_OBJECTS} objects per project')
        if any(not isinstance(o, dict) or not isinstance(o.get('id'), str)
               or not isinstance(o.get('type'), str) for o in objects):
            raise BadRequestException('Every object needs a string id and type')
        if not isinstance(removed, dict):
            raise BadRequestException('doc.removed must be an object of page -> [object key]')
        for page, keys in removed.items():
            if _int_or_none(page) is None or not isinstance(keys, list) \
                    or not all(_is_removed_key(k) for k in keys):
                raise BadRequestException('doc.removed must map page numbers to lists of object keys')
        return doc

    @staticmethod
    def _validate_history(history: Any) -> Optional[Dict[str, Any]]:
        if history is None:
            return None
        if not isinstance(history, dict) or not isinstance(history.get('entries'), list):
            raise BadRequestException('history must be {entries: [], index}')
        entries = history['entries'][-MAX_HISTORY_ENTRIES:]
        index = _int_or_none(history.get('index'))
        index = len(entries) - 1 if index is None else max(0, min(index, len(entries) - 1))
        return {'entries': entries, 'index': index}

    def save_state(self, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        p = self._project_row(project_id)
        doc = self._validate_doc(data.get('doc'))
        history = self._validate_history(data.get('history'))

        doc_json = json.dumps(doc, separators=(',', ':'))
        history_json = json.dumps(history, separators=(',', ':')) if history is not None else None
        if len(doc_json) + len(history_json or '') > MAX_STATE_BYTES:
            raise BadRequestException(
                'This project is too large to save in one piece. Clear older history entries '
                'and try again.')

        base_version = _int_or_none(data.get('baseVersion'))
        if not data.get('force') and base_version is not None and base_version != p['version']:
            names = self._user_names([p['updated_by_id']])
            raise ConflictException(
                f"Someone else saved this project since you opened it "
                f"({names.get(p['updated_by_id'], 'another admin')}, version {p['version']}).")

        label = data.get('label')
        label = label.strip()[:255] if isinstance(label, str) and label.strip() else None
        named = bool(data.get('named')) and bool(label)

        # Row lock: two saves racing past the version check must still serialise.
        self.db.execute(_t("SELECT id FROM pdf_editor_projects WHERE id = :id FOR UPDATE"),
                        {'id': project_id})
        new_version = int(self.db.execute(_t(
            "UPDATE pdf_editor_projects "
            "   SET state = CAST(:doc AS jsonb), history = CAST(:history AS jsonb), "
            "       version = version + 1, updated_by_id = :uid, updated_date = NOW() "
            " WHERE id = :id RETURNING version"
        ), {'id': project_id, 'doc': doc_json, 'history': history_json,
            'uid': self.user_id}).scalar())

        removed_count = sum(len(v) for v in (doc.get('removed') or {}).values())
        rev = self.db.execute(_t(
            "INSERT INTO pdf_editor_revisions "
            "       (project_id, revision_no, label, is_named, doc, object_count, removed_count, created_by_id) "
            "SELECT :pid, COALESCE(MAX(revision_no), 0) + 1, :label, :named, CAST(:doc AS jsonb), "
            "       :objects, :removed, :uid "
            "  FROM pdf_editor_revisions WHERE project_id = :pid "
            "RETURNING id, revision_no, created_date"
        ), {'pid': project_id, 'label': label, 'named': named, 'doc': doc_json,
            'objects': len(doc.get('objects') or []), 'removed': removed_count,
            'uid': self.user_id}).fetchone()

        self.db.execute(_t(
            "DELETE FROM pdf_editor_revisions "
            " WHERE project_id = :pid AND is_named = FALSE AND id NOT IN ("
            "   SELECT id FROM pdf_editor_revisions "
            "    WHERE project_id = :pid AND is_named = FALSE "
            "    ORDER BY revision_no DESC LIMIT :keep)"
        ), {'pid': project_id, 'keep': KEEP_UNNAMED_REVISIONS})
        self.db.commit()

        return {
            'version': new_version,
            'revision': {
                'id': int(rev[0]),
                'revisionNo': int(rev[1]),
                'label': label,
                'isNamed': named,
                'createdDate': _iso(rev[2]),
            },
        }

    def list_revisions(self, project_id: int) -> Dict[str, Any]:
        self._project_row(project_id)
        rows = self.db.execute(_t(
            "SELECT id, revision_no, label, is_named, object_count, removed_count, "
            "       created_by_id, created_date "
            "  FROM pdf_editor_revisions WHERE project_id = :pid "
            " ORDER BY revision_no DESC LIMIT 100"
        ), {'pid': project_id}).mappings().fetchall()
        names = self._user_names([r['created_by_id'] for r in rows])
        return {'items': [{
            'id': int(r['id']),
            'revisionNo': int(r['revision_no']),
            'label': r['label'],
            'isNamed': bool(r['is_named']),
            'objectCount': int(r['object_count']),
            'removedCount': int(r['removed_count']),
            'createdByName': names.get(r['created_by_id']) if r['created_by_id'] else None,
            'createdDate': _iso(r['created_date']),
        } for r in rows]}

    def get_revision(self, project_id: int, revision_id: int) -> Dict[str, Any]:
        self._project_row(project_id)
        row = self.db.execute(_t(
            "SELECT id, revision_no, label, doc, created_date FROM pdf_editor_revisions "
            " WHERE id = :rid AND project_id = :pid"
        ), {'rid': revision_id, 'pid': project_id}).mappings().fetchone()
        if row is None:
            raise NotFoundException(f'Revision {revision_id} not found')
        return {
            'id': int(row['id']),
            'revisionNo': int(row['revision_no']),
            'label': row['label'],
            'doc': row['doc'],
            'createdDate': _iso(row['created_date']),
        }

    # ── assets (element bar) ────────────────────────────────────────────

    def list_assets(self, query: Dict[str, Any]) -> Dict[str, Any]:
        project_id = _int_or_none(query.get('projectId'))
        params: Dict[str, Any] = {'uid': self.user_id}
        clauses = ["(a.scope = 'library' AND a.created_by_id = :uid)"]
        if project_id:
            self._project_row(project_id)
            clauses.append("(a.scope = 'project' AND a.project_id = :pid)")
            params['pid'] = project_id
        rows = self.db.execute(_t(
            "SELECT a.id, a.project_id, a.scope, a.kind, a.name, a.status, a.s3_bucket, a.s3_key, "
            "       a.mime_type, a.file_size, a.width, a.height, a.created_by_id, a.created_date "
            "  FROM pdf_editor_assets a "
            f" WHERE a.deleted_date IS NULL AND a.status = 'ready' AND a.kind <> 'thumbnail' "
            f"   AND ({' OR '.join(clauses)}) "
            " ORDER BY a.created_date DESC, a.id DESC LIMIT 500"
        ), params).mappings().fetchall()
        names = self._user_names([r['created_by_id'] for r in rows])
        return {
            'items': [self._asset_view(r, names) for r in rows],
            'maxAssetBytes': MAX_ASSET_BYTES,
            'mimeTypes': sorted(ASSET_MIME_TYPES),
        }

    def start_asset_upload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.user_id:
            raise ForbiddenException('Cannot determine the uploading admin')
        kind = data.get('kind') if data.get('kind') in ASSET_KINDS else 'image'
        scope = 'library' if data.get('scope') == 'library' else 'project'
        project_id = _int_or_none(data.get('projectId'))
        if kind == 'thumbnail':
            scope = 'project'
        if scope == 'project':
            if not project_id:
                raise BadRequestException('projectId is required for a project asset')
            self._project_row(project_id)
        else:
            project_id = None

        mime = (data.get('mimeType') or '').lower()
        if mime not in ASSET_MIME_TYPES:
            raise BadRequestException('Images must be PNG or JPEG (the editor converts other formats)')
        size = _int_or_none(data.get('fileSize'))
        if size is not None and size > MAX_ASSET_BYTES:
            raise BadRequestException(
                f'Image is {size / (1024 * 1024):.1f} MB; the limit is {MAX_ASSET_BYTES // (1024 * 1024)} MB.')
        width = _int_or_none(data.get('width'))
        height = _int_or_none(data.get('height'))
        name = _clean_name(data.get('name'), 'name', required=False) or kind

        ext = ASSET_MIME_TYPES[mime]
        key = (storage.new_key('projects', project_id, 'thumb' if kind == 'thumbnail' else 'assets', ext=ext)
               if scope == 'project' else storage.new_key('library', self.user_id, ext=ext))
        row = self.db.execute(_t(
            "INSERT INTO pdf_editor_assets "
            "       (project_id, scope, kind, name, status, s3_bucket, s3_key, mime_type, "
            "        file_size, width, height, created_by_id) "
            "VALUES (:pid, :scope, :kind, :name, 'pending', :bucket, :key, :mime, :size, :w, :h, :uid) "
            "RETURNING id"
        ), {'pid': project_id, 'scope': scope, 'kind': kind, 'name': name,
            'bucket': storage.bucket_name(), 'key': key, 'mime': mime, 'size': size,
            'w': width, 'h': height, 'uid': self.user_id}).fetchone()
        self.db.commit()
        signed = storage.presign_upload(key, mime, MAX_ASSET_BYTES)
        return {'assetId': int(row[0]), **signed, 'contentType': mime}

    def confirm_asset(self, asset_id: int) -> Dict[str, Any]:
        a = self._asset_row(asset_id)
        if a['status'] != 'ready':
            size = storage.head_size(a['s3_key'], bucket=a['s3_bucket'])
            if not size:
                raise BadRequestException('The image did not reach storage. Please upload it again.')
            self.db.execute(_t(
                "UPDATE pdf_editor_assets SET status = 'ready', file_size = :size WHERE id = :id"
            ), {'id': asset_id, 'size': size})
            if a['kind'] == 'thumbnail' and a['project_id']:
                # Only the thumbnail pointer moves; updated_date stays, so making a
                # preview does not reorder the project list.
                self.db.execute(_t(
                    "UPDATE pdf_editor_projects SET thumbnail_asset_id = :aid WHERE id = :pid"
                ), {'aid': asset_id, 'pid': a['project_id']})
            self.db.commit()
            a = self._asset_row(asset_id)
        names = self._user_names([a['created_by_id']])
        return self._asset_view(a, names)

    def update_asset(self, asset_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        self._asset_row(asset_id)
        name = _clean_name(data.get('name'), 'name')
        self.db.execute(_t("UPDATE pdf_editor_assets SET name = :name WHERE id = :id"),
                        {'id': asset_id, 'name': name})
        self.db.commit()
        a = self._asset_row(asset_id)
        return self._asset_view(a, self._user_names([a['created_by_id']]))

    def delete_asset(self, asset_id: int) -> Dict[str, Any]:
        # Soft delete only: a saved state or revision may still place this image,
        # and its bytes must keep resolving for that state to open and export.
        self._asset_row(asset_id)
        self.db.execute(_t("UPDATE pdf_editor_assets SET deleted_date = NOW() WHERE id = :id"),
                        {'id': asset_id})
        self.db.commit()
        return {'id': asset_id, 'deleted': True}

    def resolve_assets(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Signed URLs for assets a saved state places, deleted-from-the-bar or not.

        The element bar lists live assets; a document may still reference one the
        bar no longer shows (removed from the bar, or another admin's library
        signature placed in a shared project). Rendering and export must not
        break because of that, so ids are resolved here without the owner filter
        — the caller already holds the project, and the id came from its state.
        """
        project_id = _int_or_none(data.get('projectId'))
        if not project_id:
            raise BadRequestException('projectId is required')
        p = self._project_row(project_id)
        state_ids = {o.get('assetId') for o in (p['state'] or {}).get('objects', [])
                     if isinstance(o, dict)}
        requested = data.get('ids') if isinstance(data.get('ids'), list) else []
        ids = [i for i in (_int_or_none(x) for x in requested[:500]) if i is not None]
        # Only ids the saved state (or this project) actually references, or ones
        # the caller can already see — not an open lookup of every asset by id.
        if not ids:
            return {'items': []}
        rows = self.db.execute(_t(
            "SELECT id, project_id, scope, kind, name, status, s3_bucket, s3_key, mime_type, "
            "       file_size, width, height, created_by_id, created_date "
            "  FROM pdf_editor_assets WHERE id = ANY(:ids) AND status = 'ready' "
            "   AND (project_id = :pid OR created_by_id = :uid OR id = ANY(:state_ids))"
        ), {'ids': ids, 'pid': project_id, 'uid': self.user_id,
            'state_ids': [i for i in state_ids if isinstance(i, int)]}).mappings().fetchall()
        names = self._user_names([r['created_by_id'] for r in rows])
        return {'items': [self._asset_view(r, names) for r in rows]}
