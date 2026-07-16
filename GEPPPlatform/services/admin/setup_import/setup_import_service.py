"""
Import Organization Setup — back-office service.

One `organization_setup_imports` row per uploaded 5-tab xlsx. Flow mirrors the transaction
import (import_files/ImportService):
  upload   → store raw xlsx in S3 + create batch row (status='uploaded')
  extract  → parse + validate + build an editable preview (status='extracted')
  confirm  → create users/tags/tenants (INSERT) then origins/destinations (REPLACE: a new
             organization_setup version whose tree holds only the imported nodes; the previous
             tree's nodes stay active → become recycle-bin orphans). Records every created id on
             the batch so it can be reverted. (status='confirmed')
  revert   → soft-delete the created users/tags/tenants/locations + insert a new setup version
             with the imported nodeIds stripped out. (status='reverted')

Semantics (user-confirmed):
  - Email uniqueness is GLOBAL (whole system) — duplicates are blocking, fixed in the preview.
  - origins/destinations REPLACE the whole chart; users/tags/tenants INSERT (append).
  - revert only removes what the import created (no snapshot restore of the previous chart).

Composes existing creation logic: UserService.create_user, LocationTagService.create_tag,
TenantService.create_tenant. Origin/destination UserLocation rows are created directly (so tags/
tenants/materials/business_type + the node-level is_destination flag are all set — create_organization_
setup does not carry those) and the OrganizationSetup version is inserted the same way core does.
"""

from __future__ import annotations

import logging
import re
import secrets
import string
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ....models.organization_setup_import import OrganizationSetupImport
from ....models.subscriptions.organizations import OrganizationSetup, Organization
from ....models.users.user_location import UserLocation
from ....models.users.user_related import UserLocationTag, UserTenant
from ....models.cores.references import Material
from ...file_upload_service import S3FileUploadService
from . import parser as P

logger = logging.getLogger(__name__)

# xlsx Role label → OrganizationRole.key
_ROLE_MAP = {
    'admin': 'admin', 'administrator': 'admin',
    'datainputer': 'data_input', 'datainput': 'data_input', 'datainputspecialist': 'data_input',
    'dataauditor': 'auditor', 'auditor': 'auditor',
    'viewer': 'viewer',
}
# xlsx Business Type (Thai) → hub_type key. Unknown values fall back to the raw string
# (still non-null so the row is recognised as a destination: hub_type IS NOT NULL).
_HUB_TYPE_MAP = {
    'ผู้รวบรวม': 'Collectors',
    'ผู้คัดแยก': 'Sorters',
    'ผู้รวบรวมและคัดแยก': 'Aggregators',
    'สถานีขนถ่าย': 'Transfer Station',
    'อัดก้อน': 'Baler',
    'mrf': 'MRF',
    'โรงงานรีไซเคิล': 'Recycling Plant',
    'หลุมฝังกลบ': 'Landfill',
    'เตาเผาร่วม': 'Co-processing',
    'เตาเผา': 'Incinerator',
}

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _norm(s: Any) -> str:
    return re.sub(r'\s+', '', str(s or '').strip().lower())


def _role_key(role_label: str) -> Optional[str]:
    return _ROLE_MAP.get(_norm(role_label))


def _hub_type_key(business_type: str) -> str:
    return _HUB_TYPE_MAP.get(_norm(business_type)) or (business_type or '').strip() or 'Collectors'


def _gen_password(length: int = 10) -> str:
    """Readable random password for users imported without one (letters+digits, no ambigu/symbols)."""
    alphabet = ''.join(c for c in (string.ascii_letters + string.digits) if c not in 'Il1O0')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class SetupImportService:
    def __init__(self, db):
        self.db = db

    # ── 1. Upload ────────────────────────────────────────────────────────────────
    def upload(self, organization_id: int, admin_id: Optional[int], filename: str,
               file_bytes: bytes, content_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            s3 = S3FileUploadService()
            uploaded = s3.upload_import_file(
                file_data=file_bytes, filename=filename, content_type=content_type,
                import_type='organization_setup', organization_id=organization_id,
            )
            row = OrganizationSetupImport(
                organization_id=organization_id, uploaded_by_id=admin_id,
                original_filename=filename,
                s3_key=(uploaded or {}).get('s3_key'), s3_bucket=(uploaded or {}).get('s3_bucket'),
                file_size=(uploaded or {}).get('file_size'),
                mime_type=(uploaded or {}).get('content_type') or content_type,
                status='uploaded',
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': self._row_meta(row)}
        except Exception as e:
            self.db.rollback()
            logger.error(f"setup-import upload error: {e}")
            return {'success': False, 'message': 'Upload failed', 'errors': [str(e)]}

    # ── 2. Extract + validate → preview ──────────────────────────────────────────
    def extract(self, import_id: int, organization_id: int) -> Dict[str, Any]:
        row = self._get_row(import_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import not found'}
        try:
            row.status = 'extracting'
            self.db.commit()

            s3 = S3FileUploadService()
            file_bytes = s3.download_file(row.s3_key) if row.s3_key else None
            if not file_bytes:
                raise ValueError('Could not read the uploaded file from storage')

            parsed = P.parse_setup_workbook(file_bytes)
            preview = self._build_preview(parsed, organization_id)

            row.preview_payload = preview
            row.summary = preview['summary']
            row.status = 'extracted'
            row.error = None
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': {**self._row_meta(row), **preview}}
        except Exception as e:
            self.db.rollback()
            self._mark_failed(import_id, organization_id, str(e))
            logger.error(f"setup-import extract error: {e}")
            return {'success': False, 'message': 'Extraction failed', 'errors': [str(e)]}

    def get_preview(self, import_id: int, organization_id: int) -> Dict[str, Any]:
        row = self._get_row(import_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import not found'}
        return {'success': True, 'data': {**self._row_meta(row), **(row.preview_payload or {})}}

    def _build_preview(self, parsed: Dict[str, Any], organization_id: int) -> Dict[str, Any]:
        """Validate every section and produce an editable preview. Blocking errors gate confirm."""
        # Names available to resolve Members against: imported users (by display_name).
        imported_user_names = {_norm(u['display_name']) for u in parsed['users'] if u['display_name']}
        # Existing active org users (members may reference people already in the org).
        existing_users = self.db.query(UserLocation).filter(
            UserLocation.organization_id == organization_id, UserLocation.is_user == True,  # noqa: E712
            UserLocation.is_active == True, UserLocation.deleted_date.is_(None),  # noqa: E712
        ).all()
        existing_user_names = {
            _norm(n) for u in existing_users
            for n in [u.display_name, u.name_en, u.name_th] if n
        }
        known_member_names = imported_user_names | existing_user_names

        # Material names → resolvable (global or this org).
        materials = self.db.query(Material).filter(
            Material.is_active == True,  # noqa: E712
            (Material.is_global == True) | (Material.organization_id == organization_id),  # noqa: E712
        ).all()
        known_material_names = {_norm(n) for m in materials for n in [m.name_en, m.name_th] if n}

        # Existing destination (hub) names — new destinations must not collide.
        existing_dest_names = {
            _norm(u.display_name) for u in self.db.query(UserLocation).filter(
                UserLocation.organization_id == organization_id, UserLocation.hub_type.isnot(None),
                UserLocation.deleted_date.is_(None),
            ).all() if u.display_name
        }

        blocking = 0

        # -- Users --
        users_out, seen_emails = [], {}
        for u in parsed['users']:
            errors = []
            email = (u['email'] or '').strip()
            if not email:
                errors.append('email_required')
            elif not _EMAIL_RE.match(email):
                errors.append('email_invalid')
            else:
                key = email.lower()
                if key in seen_emails:
                    errors.append('email_duplicate_in_file')
                seen_emails[key] = True
                if self._email_exists(email):
                    errors.append('email_exists')  # GLOBAL uniqueness
            role_key = _role_key(u['role'])
            if not role_key:
                errors.append('role_unknown')
            if not u['display_name']:
                errors.append('display_name_required')
            # Blank password → generate one now (stored in the preview so the admin can see +
            # export it before confirm, and confirm reuses this exact value).
            pwd = u.get('password')
            password_generated = not pwd
            if password_generated:
                pwd = _gen_password()
            blocking += len(errors)
            users_out.append({
                **u, 'password': pwd, 'password_generated': password_generated,
                'role_key': role_key, 'errors': errors,
            })

        # -- Tags / Tenants (INSERT; only name required; members are warnings) --
        def _named(section):
            out = []
            for t in parsed[section]:
                errors, warnings = [], []
                if not t['name']:
                    errors.append('name_required')
                unmatched = [m for m in t['members'] if _norm(m) not in known_member_names]
                if unmatched:
                    warnings.append('members_unmatched')
                blocking_local = len(errors)
                out.append({**t, 'unmatched_members': unmatched, 'errors': errors, 'warnings': warnings})
                nonlocal_blocking[0] += blocking_local
            return out
        nonlocal_blocking = [0]
        tags_out = _named('tags')
        tenants_out = _named('tenants')
        blocking += nonlocal_blocking[0]

        # -- Origins (REPLACE) — sibling-name uniqueness + reference checks --
        origins_out = []
        by_parent: Dict[Tuple[str, ...], set] = {}
        origin_tag_names = {_norm(t['name']) for t in parsed['tags'] if t['name']}
        origin_tenant_names = {_norm(t['name']) for t in parsed['tenants'] if t['name']}
        for o in parsed['origins']:
            errors, warnings = [], []
            if o['malformed']:
                errors.append('malformed_path')
            # Siblings (same parent path) must have unique names; different parents may repeat.
            pkey = tuple(_norm(x) for x in o['parent_path'])
            sib = by_parent.setdefault(pkey, set())
            nkey = _norm(o['name'])
            if nkey in sib:
                errors.append('duplicate_sibling')
            sib.add(nkey)
            if [m for m in o['members'] if _norm(m) not in known_member_names]:
                warnings.append('members_unmatched')
            if [t for t in o['tags'] if _norm(t) not in origin_tag_names]:
                warnings.append('tags_unmatched')
            if [t for t in o['tenants'] if _norm(t) not in origin_tenant_names]:
                warnings.append('tenants_unmatched')
            if [m for m in o['materials'] if _norm(m) not in known_material_names]:
                warnings.append('materials_unmatched')
            blocking += len(errors)
            origins_out.append({**o, 'errors': errors, 'warnings': warnings})

        # -- Destinations (REPLACE) — unique name (vs existing + in-file), business type --
        dests_out, seen_dest = [], []
        for d in parsed['destinations']:
            errors, warnings = [], []
            if not d['name']:
                errors.append('name_required')
            nkey = _norm(d['name'])
            if nkey in seen_dest:
                errors.append('duplicate_in_file')
            seen_dest.append(nkey)
            if nkey in existing_dest_names:
                errors.append('name_exists')
            if [m for m in d['members'] if _norm(m) not in known_member_names]:
                warnings.append('members_unmatched')
            if [m for m in d['materials'] if _norm(m) not in known_material_names]:
                warnings.append('materials_unmatched')
            blocking += len(errors)
            dests_out.append({**d, 'hub_type_key': _hub_type_key(d['business_type']),
                              'errors': errors, 'warnings': warnings})

        summary = {
            'users': len(users_out), 'tags': len(tags_out), 'tenants': len(tenants_out),
            'origins': len(origins_out), 'destinations': len(dests_out),
            'blocking_errors': blocking,
        }
        return {
            'users': users_out, 'tags': tags_out, 'tenants': tenants_out,
            'origins': origins_out, 'destinations': dests_out,
            'summary': summary, 'can_confirm': blocking == 0,
        }

    # ── 3. Confirm → create everything ───────────────────────────────────────────
    def confirm(self, import_id: int, organization_id: int, admin_id: Optional[int],
                edited: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        row = self._get_row(import_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import not found'}
        if row.status == 'confirmed':
            return {'success': False, 'message': 'This import has already been confirmed'}

        preview = edited or row.preview_payload or {}
        # Re-validate emails on the (possibly edited) payload — the admin may have fixed dups.
        revalidation = self._revalidate_users(preview.get('users', []))
        if revalidation:
            return {'success': False, 'message': 'Validation failed', 'errors': revalidation}

        created = {'users': [], 'tags': [], 'tenants': [], 'locations': []}
        try:
            row.status = 'confirming'
            self.db.commit()

            from ...cores.users.user_service import UserService
            from ...cores.users.location_tag_service import LocationTagService
            from ...cores.users.tenant_service import TenantService
            usvc, tagsvc, tensvc = UserService(self.db), LocationTagService(self.db), TenantService(self.db)

            # 1) Users (INSERT). display_name(norm) → new user id.
            user_by_name: Dict[str, int] = {}
            for u in preview.get('users', []):
                res = usvc.create_user({
                    'display_name': u['display_name'], 'email': (u['email'] or '').strip(),
                    'password': u.get('password') or None, 'role': u.get('role_key') or _role_key(u.get('role')) or 'viewer',
                    'first_name': u.get('first_name'), 'last_name': u.get('last_name'),
                    'qr_name': u.get('qr_name'), 'organization_id': organization_id,
                    'is_user': True,
                }, created_by_id=admin_id, auto_generate_credentials=True)
                if not res.get('success'):
                    raise RuntimeError(res.get('message') or 'User creation failed')
                uid = int(res['user']['id'])
                created['users'].append(uid)
                if u.get('display_name'):
                    user_by_name[_norm(u['display_name'])] = uid

            # Existing org users can also be referenced as members.
            for eu in self.db.query(UserLocation).filter(
                UserLocation.organization_id == organization_id, UserLocation.is_user == True,  # noqa: E712
                UserLocation.is_active == True, UserLocation.deleted_date.is_(None),  # noqa: E712
            ).all():
                for n in [eu.display_name, eu.name_en, eu.name_th]:
                    if n:
                        user_by_name.setdefault(_norm(n), int(eu.id))

            def member_objs(names): return [{'user_id': user_by_name[_norm(n)]}
                                            for n in names if _norm(n) in user_by_name]
            def member_ids(names): return [user_by_name[_norm(n)] for n in names if _norm(n) in user_by_name]

            # 2) Tags (INSERT). name(norm) → id.
            tag_by_name: Dict[str, int] = {}
            for t in preview.get('tags', []):
                res = tagsvc.create_tag(organization_id, {
                    'name': t['name'], 'note': t.get('description'),
                    'start_date': t.get('start_date'), 'end_date': t.get('end_date'),
                    'members': member_ids(t.get('members', [])),
                }, created_by_id=admin_id)
                tid = self._extract_id(res)
                created['tags'].append(tid)
                tag_by_name[_norm(t['name'])] = tid

            # 3) Tenants (INSERT). name(norm) → id.
            tenant_by_name: Dict[str, int] = {}
            for t in preview.get('tenants', []):
                res = tensvc.create_tenant(organization_id, {
                    'name': t['name'], 'note': t.get('description'),
                    'start_date': t.get('start_date'), 'end_date': t.get('end_date'),
                    'members': member_ids(t.get('members', [])),
                }, created_by_id=admin_id)
                tid = self._extract_id(res)
                created['tenants'].append(tid)
                tenant_by_name[_norm(t['name'])] = tid

            # Material name → id.
            mat_by_name: Dict[str, int] = {}
            for m in self.db.query(Material).filter(
                Material.is_active == True,  # noqa: E712
                (Material.is_global == True) | (Material.organization_id == organization_id),  # noqa: E712
            ).all():
                for n in [m.name_en, m.name_th]:
                    if n:
                        mat_by_name.setdefault(_norm(n), int(m.id))
            def material_ids(names): return [mat_by_name[_norm(n)] for n in names if _norm(n) in mat_by_name]

            # 4) Origins (REPLACE). Create rows parents-first; build root_nodes with is_destination.
            origins = sorted(preview.get('origins', []), key=lambda o: o.get('depth', 1))
            node_by_path: Dict[Tuple[str, ...], Dict[str, Any]] = {}
            root_nodes: List[Dict[str, Any]] = []
            for o in origins:
                loc = UserLocation(
                    organization_id=organization_id, is_location=True, is_user=False,
                    display_name=o['name'], name_en=o['name'], name_th=o['name'],
                    type=o['type'], address=o.get('address') or None,
                    members=member_objs(o.get('members', [])),
                    tags=[tag_by_name[_norm(t)] for t in o.get('tags', []) if _norm(t) in tag_by_name],
                    tenants=[tenant_by_name[_norm(t)] for t in o.get('tenants', []) if _norm(t) in tenant_by_name],
                    materials=material_ids(o.get('materials', [])),
                    platform='GEPP_BUSINESS_WEB',
                )
                self.db.add(loc)
                self.db.flush()
                created['locations'].append(int(loc.id))
                node = {'nodeId': int(loc.id), 'children': []}
                if o.get('is_destination'):
                    node['is_destination'] = True
                node_by_path[tuple(_norm(x) for x in o['path'])] = node
                parent = node_by_path.get(tuple(_norm(x) for x in o['parent_path'])) if o.get('parent_path') else None
                (parent['children'] if parent else root_nodes).append(node)

            # 5) Destinations (REPLACE) → hub_node.children.
            hub_children: List[Dict[str, Any]] = []
            for d in preview.get('destinations', []):
                loc = UserLocation(
                    organization_id=organization_id, is_location=True, is_user=False,
                    display_name=d['name'], name_en=d['name'], name_th=d['name'],
                    type='hub', hub_type=d.get('hub_type_key') or _hub_type_key(d.get('business_type', '')),
                    business_type=d.get('business_type') or None, address=d.get('address') or None,
                    members=member_objs(d.get('members', [])),
                    materials=material_ids(d.get('materials', [])),
                    platform='GEPP_BUSINESS_WEB',
                )
                self.db.add(loc)
                self.db.flush()
                created['locations'].append(int(loc.id))
                hub_children.append({'nodeId': int(loc.id), 'children': []})

            # 6) New setup version (REPLACE) — carry over level names; trigger deactivates prior.
            prev = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
            ).order_by(OrganizationSetup.created_date.desc()).first()
            hub_node = dict(prev.hub_node) if (prev and isinstance(prev.hub_node, dict)) else {}
            hub_node['children'] = hub_children
            new_setup = OrganizationSetup(
                organization_id=organization_id, version=self._next_version(prev), is_active=True,
                root_nodes=root_nodes, hub_node=hub_node,
                branch_level_name=getattr(prev, 'branch_level_name', None),
                building_level_name=getattr(prev, 'building_level_name', None),
                floor_level_name=getattr(prev, 'floor_level_name', None),
                room_level_name=getattr(prev, 'room_level_name', None),
            )
            self.db.add(new_setup)
            self.db.flush()

            row.created_user_ids = created['users']
            row.created_tag_ids = created['tags']
            row.created_tenant_ids = created['tenants']
            row.created_location_ids = created['locations']
            row.created_setup_version_id = int(new_setup.id)
            row.status = 'confirmed'
            row.confirmed_date = datetime.now()
            row.summary = {**(row.summary or {}), 'created': {
                'users': len(created['users']), 'tags': len(created['tags']),
                'tenants': len(created['tenants']), 'locations': len(created['locations']),
            }}
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': self._row_meta(row)}
        except Exception as e:
            self.db.rollback()
            logger.error(f"setup-import confirm error: {e} — compensating")
            self._soft_delete(created)  # remove anything already created (individual commits)
            self._mark_failed(import_id, organization_id, str(e))
            return {'success': False, 'message': 'Import failed and was rolled back', 'errors': [str(e)]}

    # ── 4. History + revert ──────────────────────────────────────────────────────
    def list_history(self, organization_id: int) -> Dict[str, Any]:
        rows = self.db.query(OrganizationSetupImport).filter(
            OrganizationSetupImport.organization_id == organization_id,
            OrganizationSetupImport.deleted_date.is_(None),
        ).order_by(OrganizationSetupImport.created_date.desc()).all()
        return {'success': True, 'data': [self._row_meta(r) for r in rows]}

    def revert(self, import_id: int, organization_id: int) -> Dict[str, Any]:
        row = self._get_row(import_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import not found'}
        if row.status != 'confirmed':
            return {'success': False, 'message': 'Only a confirmed import can be reverted'}
        try:
            created_locs = set(int(x) for x in (row.created_location_ids or []))
            # Soft-delete created users/tags/tenants/locations.
            self._soft_delete({
                'users': row.created_user_ids or [], 'tags': row.created_tag_ids or [],
                'tenants': row.created_tenant_ids or [], 'locations': list(created_locs),
            })
            # Strip the imported nodeIds from the active tree → new version (leaves the
            # pre-import orphans in the recycle bin, untouched).
            active = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True,  # noqa: E712
            ).order_by(OrganizationSetup.created_date.desc()).first()
            if active:
                new_root = self._strip_nodes(active.root_nodes or [], created_locs)
                hub = dict(active.hub_node) if isinstance(active.hub_node, dict) else {}
                hub['children'] = self._strip_nodes(hub.get('children') or [], created_locs)
                new_setup = OrganizationSetup(
                    organization_id=organization_id, version=self._next_version(active), is_active=True,
                    root_nodes=new_root, hub_node=hub,
                    branch_level_name=active.branch_level_name, building_level_name=active.building_level_name,
                    floor_level_name=active.floor_level_name, room_level_name=active.room_level_name,
                )
                self.db.add(new_setup)
                self.db.flush()
            row.status = 'reverted'
            row.reverted_date = datetime.now()
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': self._row_meta(row)}
        except Exception as e:
            self.db.rollback()
            logger.error(f"setup-import revert error: {e}")
            return {'success': False, 'message': 'Revert failed', 'errors': [str(e)]}

    # ── internals ────────────────────────────────────────────────────────────────
    def _get_row(self, import_id: int, organization_id: int) -> Optional[OrganizationSetupImport]:
        return self.db.query(OrganizationSetupImport).filter(
            OrganizationSetupImport.id == import_id,
            OrganizationSetupImport.organization_id == organization_id,
            OrganizationSetupImport.deleted_date.is_(None),
        ).first()

    def _mark_failed(self, import_id: int, organization_id: int, error: str) -> None:
        try:
            r = self._get_row(import_id, organization_id)
            if r:
                r.status = 'failed'
                r.error = (error or '')[:2000]
                self.db.commit()
        except Exception:
            self.db.rollback()

    def _email_exists(self, email: str) -> bool:
        from sqlalchemy import func
        return self.db.query(UserLocation.id).filter(
            func.lower(UserLocation.email) == email.strip().lower(),
            UserLocation.is_user == True,  # noqa: E712
            UserLocation.deleted_date.is_(None),
        ).first() is not None

    def _revalidate_users(self, users: List[Dict[str, Any]]) -> List[str]:
        errors, seen = [], set()
        for u in users:
            email = (u.get('email') or '').strip()
            if not email or not _EMAIL_RE.match(email):
                errors.append(f"Row {u.get('row_index')}: invalid email")
                continue
            k = email.lower()
            if k in seen:
                errors.append(f"Row {u.get('row_index')}: duplicate email in file ({email})")
            seen.add(k)
            if self._email_exists(email):
                errors.append(f"Row {u.get('row_index')}: email already exists ({email})")
            if not (u.get('role_key') or _role_key(u.get('role'))):
                errors.append(f"Row {u.get('row_index')}: unknown role")
        return errors

    @staticmethod
    def _extract_id(res: Any) -> int:
        """Pull the created id from a create_tag/create_tenant result (tolerant of envelope shape)."""
        if isinstance(res, dict):
            for k in ('data', 'tag', 'tenant'):
                v = res.get(k)
                if isinstance(v, dict) and v.get('id') is not None:
                    return int(v['id'])
            if res.get('id') is not None:
                return int(res['id'])
        return int(getattr(res, 'id'))

    def _soft_delete(self, ids: Dict[str, List[int]]) -> None:
        now = datetime.now()
        loc_ids = [int(x) for x in (ids.get('users') or [])] + [int(x) for x in (ids.get('locations') or [])]
        if loc_ids:
            self.db.query(UserLocation).filter(UserLocation.id.in_(loc_ids)).update(
                {UserLocation.is_active: False, UserLocation.deleted_date: now}, synchronize_session=False)
        if ids.get('tags'):
            self.db.query(UserLocationTag).filter(UserLocationTag.id.in_([int(x) for x in ids['tags']])).update(
                {UserLocationTag.is_active: False, UserLocationTag.deleted_date: now}, synchronize_session=False)
        if ids.get('tenants'):
            self.db.query(UserTenant).filter(UserTenant.id.in_([int(x) for x in ids['tenants']])).update(
                {UserTenant.is_active: False, UserTenant.deleted_date: now}, synchronize_session=False)
        self.db.commit()

    @staticmethod
    def _strip_nodes(nodes: List[Dict[str, Any]], remove_ids: set) -> List[Dict[str, Any]]:
        """Drop any node whose nodeId is in remove_ids (its whole subtree goes with it)."""
        out = []
        for n in nodes or []:
            try:
                nid = int(n.get('nodeId'))
            except (TypeError, ValueError):
                nid = None
            if nid in remove_ids:
                continue
            kept = dict(n)
            kept['children'] = SetupImportService._strip_nodes(n.get('children') or [], remove_ids)
            out.append(kept)
        return out

    @staticmethod
    def _next_version(prev) -> str:
        if not prev:
            return '1.0'
        try:
            return str(round(float(prev.version) + 0.1, 1))
        except (ValueError, TypeError):
            return '1.1'

    def _row_meta(self, r: OrganizationSetupImport) -> Dict[str, Any]:
        return {
            'id': r.id, 'organization_id': r.organization_id, 'status': r.status,
            'original_filename': r.original_filename, 'file_size': r.file_size,
            'summary': r.summary, 'error': r.error,
            'created_date': r.created_date.isoformat() if r.created_date else None,
            'confirmed_date': r.confirmed_date.isoformat() if r.confirmed_date else None,
            'reverted_date': r.reverted_date.isoformat() if r.reverted_date else None,
        }
