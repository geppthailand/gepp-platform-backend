"""
Import service — Excel bulk-import of waste transactions.

Flow (one row in `import_files` per upload):
  1. upload_file    → store the raw .xlsx in S3 + create the import_files row (status='uploaded').
  2. extract        → parse the Waste Data sheet, fuzzy-match each row's location/tag/tenant/
                      waste-type to the org's data, build ready-to-insert review rows, store
                      them in preview_payload (status='extracted').
  3. get_preview    → return preview_payload for the review step (names, not ids; editable).
  4. confirm        → group the (possibly edited) rows by header (origin,date,tag,tenant) and
                      create one Transaction per group, each tagged with import_file_id.
  5. history/revert → list past uploads; soft-delete an entire upload's transactions.

Matching is char-trigram cosine (see matching.py), argmax, no threshold. Grouping is by the
transaction HEADER (origin/date/tag/tenant are header-level columns on Transaction; only
material+weight are per-record), so "one upload" becomes N header-grouped transactions that
all share import_file_id and revert together.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

from ....models.import_file import ImportFile
from ....models.subscriptions.organizations import OrganizationSetup
from ....models.users.user_location import UserLocation
from ....models.users.user_related import UserLocationTag, UserTenant
from ....models.cores.references import Material
from ....models.transactions.transactions import Transaction
from ....models.transactions.transaction_records import TransactionRecord
from ...file_upload_service import S3FileUploadService
from ..transactions.transaction_service import TransactionService
from . import matching as M

logger = logging.getLogger(__name__)

# Unit strings that count as "kilogram" — used to bias waste-type matching toward kg materials.
_KG_TOKENS = {'กิโลกรัม', 'กก', 'กก.', 'กิโล', 'kilogram', 'kilograms', 'kg', 'kgs', 'kilo'}


def _is_kg_unit(unit_th: str, unit_en: str) -> bool:
    return M._normalize(unit_th) in {M._normalize(t) for t in _KG_TOKENS} \
        or M._normalize(unit_en) in {M._normalize(t) for t in _KG_TOKENS}


class ImportService:
    def __init__(self, db):
        self.db = db

    # ── 1. Upload ─────────────────────────────────────────────────────────────
    def upload_file(
        self,
        organization_id: int,
        user_id: int,
        import_type: str,
        filename: str,
        file_bytes: bytes,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store the raw file in S3 and create the import_files row (status='uploaded')."""
        try:
            s3 = S3FileUploadService()
            uploaded = s3.upload_import_file(
                file_data=file_bytes,
                filename=filename,
                content_type=content_type,
                import_type=import_type or 'transaction',
                organization_id=organization_id,
            )
            row = ImportFile(
                organization_id=organization_id,
                uploaded_by_id=user_id,
                type=import_type or 'transaction',
                original_filename=filename,
                s3_key=(uploaded or {}).get('s3_key'),
                s3_bucket=(uploaded or {}).get('s3_bucket'),
                file_size=(uploaded or {}).get('file_size'),
                mime_type=(uploaded or {}).get('content_type') or content_type,
                status='uploaded',
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': self._row_meta(row)}
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"import upload db error: {e}")
            return {'success': False, 'message': 'Database error', 'errors': [str(e)]}
        except Exception as e:
            self.db.rollback()
            logger.error(f"import upload error: {e}")
            return {'success': False, 'message': 'Upload failed', 'errors': [str(e)]}

    # ── 2. Extract + match ──────────────────────────────────────────────────────
    def extract(self, import_file_id: int, organization_id: int) -> Dict[str, Any]:
        """Download the file, parse Waste Data, fuzzy-match, build + store preview_payload."""
        row = self._get_row(import_file_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import file not found'}
        try:
            row.status = 'extracting'
            self.db.commit()

            s3 = S3FileUploadService()
            file_bytes = s3.download_file(row.s3_key) if row.s3_key else None
            if not file_bytes:
                raise ValueError('Could not read the uploaded file from storage')

            parsed = M.parse_waste_data(file_bytes, row.original_filename)
            ctx = self._load_org_context(organization_id)
            review_rows = [self._build_review_row(r, ctx) for r in parsed]

            summary = self._summarize(review_rows)
            preview = {'review_rows': review_rows, 'options': ctx['options'], 'summary': summary}

            row.preview_payload = preview
            row.summary = summary
            row.status = 'extracted'
            row.error = None
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': {**self._row_meta(row), **preview}}
        except SQLAlchemyError as e:
            self.db.rollback()
            self._mark_failed(import_file_id, organization_id, str(e))
            return {'success': False, 'message': 'Database error', 'errors': [str(e)]}
        except Exception as e:
            self.db.rollback()
            logger.error(f"import extract error: {e}")
            self._mark_failed(import_file_id, organization_id, str(e))
            return {'success': False, 'message': 'Extraction failed', 'errors': [str(e)]}

    # ── 3. Preview (for the review step / reopen) ───────────────────────────────
    def get_preview(self, import_file_id: int, organization_id: int) -> Dict[str, Any]:
        row = self._get_row(import_file_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import file not found'}
        payload = row.preview_payload or {}
        return {'success': True, 'data': {**self._row_meta(row), **payload}}

    # ── 4. Confirm → create grouped transactions ────────────────────────────────
    def confirm(
        self,
        import_file_id: int,
        organization_id: int,
        user_id: int,
        rows: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create transactions from the (possibly edited) review rows. Groups by header
        (origin_id, transaction_date, tag_id, tenant_id) → one Transaction per group, each
        tagged with import_file_id. Excluded / invalid rows are skipped. On ANY failure the
        whole batch is reverted (soft-deleted) so the upload is all-or-nothing.
        """
        row = self._get_row(import_file_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import file not found'}
        if row.status == 'confirmed':
            return {'success': False, 'message': 'This import has already been confirmed'}

        # Prefer the edited rows sent by the client; fall back to the stored preview.
        review_rows = rows if rows is not None else (row.preview_payload or {}).get('review_rows', [])
        usable = [r for r in review_rows if self._row_is_confirmable(r)]
        if not usable:
            return {'success': False, 'message': 'No valid rows to import'}

        # Group by header tuple.
        groups: Dict[Tuple, List[Dict[str, Any]]] = {}
        for r in usable:
            key = (
                int(r['origin_id']),
                str(r.get('date') or ''),
                r.get('tag_id'),
                r.get('tenant_id'),
            )
            groups.setdefault(key, []).append(r)

        tx_service = TransactionService(self.db)
        created_ids: List[int] = []
        try:
            row.status = 'confirming'
            self.db.commit()

            for (origin_id, date_iso, tag_id, tenant_id), grp in groups.items():
                tx_dt = M.parse_datetime(date_iso) or datetime.now()
                transaction_data = {
                    'organization_id': organization_id,
                    'origin_id': origin_id,
                    'created_by_id': user_id,
                    'transaction_method': 'origin',
                    'status': 'pending',
                    'transaction_date': tx_dt,
                    'tag_id': tag_id,
                    'tenant_id': tenant_id,
                    'import_file_id': import_file_id,
                }
                records = []
                for r in grp:
                    weight = float(r.get('weight') or 0)
                    unit_weight = float(r.get('unit_weight') or 1) or 1
                    records.append({
                        'transaction_type': 'manual_input',
                        'material_id': r.get('material_id'),
                        'main_material_id': r.get('main_material_id'),
                        'category_id': r.get('category_id'),
                        'unit': r.get('unit'),
                        'origin_weight_kg': weight,
                        'origin_quantity': (weight / unit_weight) if unit_weight else weight,
                        'origin_price_per_unit': 0,
                        'total_amount': 0,
                        # Optional destination (matched from the "Destination" column). create_transaction
                        # collects these per record into Transaction.destination_ids + sets each record's
                        # destination_id. None → no destination for that record.
                        'destination_id': r.get('destination_id'),
                        'created_by_id': user_id,
                        'transaction_date': tx_dt,
                    })
                result = tx_service.create_transaction(transaction_data, records)
                if not result.get('success'):
                    raise RuntimeError(result.get('message') or 'Transaction creation failed')
                tx_obj = result.get('data') or result.get('transaction') or {}
                tx_id = tx_obj.get('id') if isinstance(tx_obj, dict) else getattr(tx_obj, 'id', None)
                if tx_id:
                    created_ids.append(tx_id)

            summary = dict(row.summary or {})
            summary.update({
                'created_transactions': len(created_ids),
                'created_transaction_ids': created_ids,
                'confirmed_records': sum(len(g) for g in groups.values()),
            })
            row.status = 'confirmed'
            row.confirmed_date = datetime.now()
            row.summary = summary
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': self._row_meta(row)}
        except Exception as e:
            self.db.rollback()
            logger.error(f"import confirm error: {e} — reverting batch")
            # Compensating action: soft-delete anything already created so the upload is atomic.
            self._revert_transactions(import_file_id)
            self._mark_failed(import_file_id, organization_id, str(e))
            return {'success': False, 'message': 'Import failed and was rolled back', 'errors': [str(e)]}

    # ── 5. History + revert ─────────────────────────────────────────────────────
    def list_history(self, organization_id: int, import_type: Optional[str] = None) -> Dict[str, Any]:
        q = self.db.query(ImportFile).filter(
            ImportFile.organization_id == organization_id,
            ImportFile.deleted_date.is_(None),
        )
        if import_type:
            q = q.filter(ImportFile.type == import_type)
        rows = q.order_by(ImportFile.created_date.desc()).all()
        return {'success': True, 'data': [self._row_meta(r) for r in rows]}

    def revert(self, import_file_id: int, organization_id: int) -> Dict[str, Any]:
        row = self._get_row(import_file_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import file not found'}
        if row.status != 'confirmed':
            return {'success': False, 'message': 'Only a confirmed import can be reverted'}
        try:
            reverted = self._revert_transactions(import_file_id)
            row.status = 'reverted'
            row.reverted_date = datetime.now()
            summary = dict(row.summary or {})
            summary['reverted_transactions'] = reverted
            row.summary = summary
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': {**self._row_meta(row), 'reverted_transactions': reverted}}
        except Exception as e:
            self.db.rollback()
            logger.error(f"import revert error: {e}")
            return {'success': False, 'message': 'Revert failed', 'errors': [str(e)]}

    def reimport(self, import_file_id: int, organization_id: int) -> Dict[str, Any]:
        """
        Re-import a reverted upload = **undo the soft-delete** (restore the exact transactions the
        revert removed), rather than creating duplicates. Import transactions are pending/origin
        with no traceability groups, so restoring is just flipping is_active back on the
        transactions + their records. If nothing is left to restore (edge), fall back to creating
        fresh from the stored preview.
        """
        row = self._get_row(import_file_id, organization_id)
        if not row:
            return {'success': False, 'message': 'Import file not found'}
        if row.status != 'reverted':
            return {'success': False, 'message': 'Only a reverted import can be re-imported'}
        try:
            restored = self._restore_transactions(import_file_id)
            if restored == 0:
                # Nothing soft-deleted to bring back → recreate from the stored preview.
                return self.confirm(
                    import_file_id, organization_id, row.uploaded_by_id,
                    (row.preview_payload or {}).get('review_rows'),
                )
            row.status = 'confirmed'
            row.confirmed_date = datetime.now()
            row.reverted_date = None
            summary = dict(row.summary or {})
            summary['created_transactions'] = restored
            summary.pop('reverted_transactions', None)
            row.summary = summary
            self.db.commit()
            self.db.refresh(row)
            return {'success': True, 'data': {**self._row_meta(row), 'restored_transactions': restored}}
        except Exception as e:
            self.db.rollback()
            logger.error(f"import reimport error: {e}")
            return {'success': False, 'message': 'Re-import failed', 'errors': [str(e)]}

    # ── Template ────────────────────────────────────────────────────────────────
    def get_template(self, with_destination: bool = False) -> Dict[str, Any]:
        """
        Build a blank .xlsx import template (headers + one example row) and return it as
        base64 (the Lambda dispatcher is JSON-only). Two variants: with vs without the
        optional trailing "Destination" column — the caller picks based on the org's
        input_destination setting.
        """
        import io
        import base64
        from openpyxl import Workbook

        headers = [
            'Date', 'Level 1 (Branch)', 'Level 2 (Building)', 'Level 3 (Floor)',
            'Level 4 (Room)', 'Tag (Event)', 'Tenant (Company)', 'Waste Type', 'Weight (kg.)',
        ]
        example = [
            '2026-06-01 09:30', 'Branch A', 'Building 1', 'Floor 2', 'Room 201',
            '-', '-', 'ขยะทั่วไป', 12.5,
        ]
        if with_destination:
            headers.append('Destination')
            example.append('โรงคัดแยกวัสดุรีไซเคิล')

        wb = Workbook()
        ws = wb.active
        ws.title = M.WASTE_DATA_SHEET  # "Waste Data" — the only sheet the parser reads
        ws.append(headers)
        ws.append(example)
        buf = io.BytesIO()
        wb.save(buf)

        filename = 'GEPP_Import_Template_with_destination.xlsx' if with_destination \
            else 'GEPP_Import_Template.xlsx'
        return {
            'success': True,
            'data': {
                'filename': filename,
                'content_base64': base64.b64encode(buf.getvalue()).decode('ascii'),
                'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            },
        }

    # ── Internal helpers ────────────────────────────────────────────────────────
    def _get_row(self, import_file_id: int, organization_id: int) -> Optional[ImportFile]:
        return self.db.query(ImportFile).filter(
            ImportFile.id == import_file_id,
            ImportFile.organization_id == organization_id,
            ImportFile.deleted_date.is_(None),
        ).first()

    def _mark_failed(self, import_file_id: int, organization_id: int, error: str) -> None:
        try:
            row = self._get_row(import_file_id, organization_id)
            if row:
                row.status = 'failed'
                row.error = error[:2000]
                self.db.commit()
        except Exception:
            self.db.rollback()

    def _revert_transactions(self, import_file_id: int) -> int:
        """Soft-delete every transaction created by this import (reuses delete_transaction)."""
        tx_service = TransactionService(self.db)
        ids = [
            t.id for t in self.db.query(Transaction.id).filter(
                Transaction.import_file_id == import_file_id,
                Transaction.is_active == True,  # noqa: E712
            ).all()
        ]
        count = 0
        for tid in ids:
            res = tx_service.delete_transaction(tid, soft_delete=True)
            if res.get('success'):
                count += 1
        return count

    def _restore_transactions(self, import_file_id: int) -> int:
        """Undo the soft-delete for this import: flip is_active back on its transactions + records."""
        tx_rows = self.db.query(Transaction).filter(
            Transaction.import_file_id == import_file_id,
            Transaction.is_active == False,  # noqa: E712
            Transaction.deleted_date.isnot(None),
        ).all()
        if not tx_rows:
            return 0
        tx_ids = [t.id for t in tx_rows]
        for tx in tx_rows:
            tx.is_active = True
            tx.deleted_date = None
        self.db.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id.in_(tx_ids)
        ).update(
            {TransactionRecord.is_active: True, TransactionRecord.deleted_date: None},
            synchronize_session=False,
        )
        return len(tx_ids)

    def _row_meta(self, row: ImportFile) -> Dict[str, Any]:
        return {
            'id': row.id,
            'type': row.type,
            'status': row.status,
            'original_filename': row.original_filename,
            'file_size': row.file_size,
            'summary': row.summary,
            'error': row.error,
            'created_date': row.created_date.isoformat() if row.created_date else None,
            'confirmed_date': row.confirmed_date.isoformat() if row.confirmed_date else None,
            'reverted_date': row.reverted_date.isoformat() if row.reverted_date else None,
        }

    # ── Org context + matching ──────────────────────────────────────────────────
    def _load_org_context(self, organization_id: int) -> Dict[str, Any]:
        """Load the org's location tree, materials, tags and tenants + build edit-option lists."""
        setup = self.db.query(OrganizationSetup).filter(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.is_active == True,  # noqa: E712
        ).order_by(OrganizationSetup.id.desc()).first()
        root_nodes = (setup.root_nodes if setup else None) or []

        locations = self.db.query(UserLocation).filter(
            UserLocation.organization_id == organization_id,
            UserLocation.is_active == True,  # noqa: E712
        ).all()
        loc_by_id: Dict[int, Dict[str, Any]] = {}
        for loc in locations:
            loc_by_id[int(loc.id)] = {
                'id': int(loc.id),
                'names': [n for n in [loc.display_name, loc.name_th, loc.name_en] if n],
                'display': loc.display_name or loc.name_th or loc.name_en or str(loc.id),
                'type': loc.type,
                'tag_ids': [int(x) for x in (loc.tags or []) if isinstance(x, (int, float))],
                'tenant_ids': [int(x) for x in (loc.tenants or []) if isinstance(x, (int, float))],
            }

        tags = self.db.query(UserLocationTag).filter(
            UserLocationTag.organization_id == organization_id,
            UserLocationTag.is_active == True,  # noqa: E712
        ).all()
        tag_by_id = {int(t.id): t.name for t in tags}
        tenants = self.db.query(UserTenant).filter(
            UserTenant.organization_id == organization_id,
            UserTenant.is_active == True,  # noqa: E712
        ).all()
        tenant_by_id = {int(t.id): t.name for t in tenants}

        materials = self.db.query(Material).filter(
            Material.is_active == True,  # noqa: E712
        ).filter(
            (Material.is_global == True) | (Material.organization_id == organization_id)  # noqa: E712
        ).all()
        mat_list = []
        for mt in materials:
            unit_th = mt.unit_name_th or ''
            unit_en = mt.unit_name_en or ''
            mat_list.append({
                'id': int(mt.id),
                'name_th': mt.name_th or '',
                'name_en': mt.name_en or '',
                'main_material_id': int(mt.main_material_id) if mt.main_material_id else None,
                'category_id': int(mt.category_id) if mt.category_id else None,
                'unit_name_th': unit_th,
                'unit_name_en': unit_en,
                'unit_weight': float(mt.unit_weight) if mt.unit_weight is not None else 1.0,
                'is_kg': _is_kg_unit(unit_th, unit_en),
            })

        # Tree metadata for the location edit dropdown: full path (search), ancestor path
        # (shown under the selected value), and depth (indentation in the option list).
        path_labels: Dict[int, str] = {}      # full path incl. leaf, e.g. "BranchA › Bldg1"
        ancestor_labels: Dict[int, str] = {}  # path WITHOUT the leaf, e.g. "BranchA"
        depth_by_id: Dict[int, int] = {}      # 0-based level
        tree_order: List[int] = []            # pre-order so the option list reads top-down

        def _walk(nodes, prefix_labels, depth):
            for node in nodes or []:
                try:
                    nid = int(node.get('nodeId'))
                except (TypeError, ValueError):
                    continue
                disp = loc_by_id.get(nid, {}).get('display', str(nid))
                full = prefix_labels + [disp]
                path_labels[nid] = ' › '.join(full)
                ancestor_labels[nid] = ' › '.join(prefix_labels)
                depth_by_id[nid] = depth
                tree_order.append(nid)
                _walk(node.get('children'), full, depth + 1)

        _walk(root_nodes, [], 0)

        # Destination candidates = the same universe as the app's destination picker:
        #   (1) hub-type locations, and (2) origin nodes flagged is_destination in root_nodes.
        # Matched against a row's optional "Destination" column by name (th/en/display).
        dest_ids: set = set()
        for lid, info in loc_by_id.items():
            if info.get('type') == 'hub':
                dest_ids.add(lid)

        def _collect_dest(nodes):
            for node in nodes or []:
                if node.get('is_destination'):
                    try:
                        dest_ids.add(int(node.get('nodeId')))
                    except (TypeError, ValueError):
                        pass
                _collect_dest(node.get('children'))
        _collect_dest(root_nodes)

        destinations: List[Dict[str, Any]] = []
        for lid in dest_ids:
            info = loc_by_id.get(lid)
            if not info:
                continue
            destinations.append({
                'id': lid,
                'names': info['names'],
                'display': info['display'],
                'path': ancestor_labels.get(lid, ''),  # hubs live outside root_nodes → ''
            })
        # Origins (in the tree) first in pre-order; hubs (not in tree) after.
        destinations.sort(key=lambda d: tree_order.index(d['id']) if d['id'] in tree_order else 10**9)

        # Order locations in tree pre-order (parents before children); any not in the tree last.
        ordered_ids = [lid for lid in tree_order if lid in loc_by_id]
        ordered_ids += [lid for lid in loc_by_id if lid not in depth_by_id]

        options = {
            'locations': [
                {
                    'id': lid,
                    'label': path_labels.get(lid, loc_by_id[lid]['display']),  # full path (search)
                    'name': loc_by_id[lid]['display'],                          # leaf name (selected value)
                    'path': ancestor_labels.get(lid, ''),                       # ancestors, shown beneath
                    'depth': depth_by_id.get(lid, 0),                           # indentation in the list
                    'type': loc_by_id[lid]['type'],
                    'tag_ids': loc_by_id[lid]['tag_ids'],
                    'tenant_ids': loc_by_id[lid]['tenant_ids'],
                }
                for lid in ordered_ids
            ],
            'materials': mat_list,
            'tags': [{'id': tid, 'name': name} for tid, name in tag_by_id.items()],
            'tenants': [{'id': tid, 'name': name} for tid, name in tenant_by_id.items()],
            'destinations': [
                {'id': d['id'], 'name': d['display'], 'path': d['path']} for d in destinations
            ],
        }

        return {
            'root_nodes': root_nodes,
            'loc_by_id': loc_by_id,
            'tag_by_id': tag_by_id,
            'tenant_by_id': tenant_by_id,
            'materials': mat_list,
            'destinations': destinations,
            'path_labels': path_labels,
            'options': options,
        }

    def _match_location(self, raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[int], str, List[str]]:
        """
        Walk levels 1→4 against the tree, matching each level's name to the children of the
        previously-matched node. Stops at the first blank/'-' level (that node = origin) or when
        the tree runs out of children. Returns (origin_id, path_label, matched_level_labels).
        """
        loc_by_id = ctx['loc_by_id']
        current_nodes = ctx['root_nodes'] or []
        origin_id: Optional[int] = None
        labels: List[str] = []
        for level_key in ('level1', 'level2', 'level3', 'level4'):
            value = raw.get(level_key)
            if M.is_blank(value):
                break  # this level ends the path
            candidates = []
            for node in current_nodes:
                try:
                    nid = int(node.get('nodeId'))
                except (TypeError, ValueError):
                    continue
                names = loc_by_id.get(nid, {}).get('names', [])
                if names:
                    candidates.append((nid, names))
                # remember children keyed by nid for the descend step
            if not candidates:
                break  # nothing to match at this level
            matched, _score = M.best_candidate(str(value), candidates)
            if matched is None:
                break
            origin_id = matched
            labels.append(loc_by_id.get(matched, {}).get('display', str(matched)))
            # descend into the matched node's children for the next level
            children = []
            for node in current_nodes:
                try:
                    if int(node.get('nodeId')) == matched:
                        children = node.get('children') or []
                        break
                except (TypeError, ValueError):
                    continue
            current_nodes = children
            if not current_nodes:
                break  # cannot go deeper
        path_label = ' › '.join(labels)
        return origin_id, path_label, labels

    def _build_review_row(self, raw: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        loc_by_id = ctx['loc_by_id']
        tag_by_id = ctx['tag_by_id']
        tenant_by_id = ctx['tenant_by_id']

        # Date
        dt = M.parse_datetime(raw.get('date'))
        # Location path
        origin_id, path_label, _labels = self._match_location(raw, ctx)
        # Weight
        weight = M.parse_weight(raw.get('weight'))
        # Material (prefer kg)
        mat_candidates = [(m['id'], [m['name_th'], m['name_en']]) for m in ctx['materials']]
        prefer = {m['id']: m['is_kg'] for m in ctx['materials']}
        material_id, _ = M.best_candidate(str(raw.get('waste_type') or ''), mat_candidates, prefer)
        mat = next((m for m in ctx['materials'] if m['id'] == material_id), None)

        # Tag / tenant — matched against the resolved location's available options only.
        tag_id = tenant_id = None
        if origin_id is not None:
            loc_info = loc_by_id.get(origin_id, {})
            tag_cands = [(tid, [tag_by_id[tid]]) for tid in loc_info.get('tag_ids', []) if tid in tag_by_id]
            tag_id, _ = M.best_candidate(str(raw.get('tag') or ''), tag_cands)
            tenant_cands = [(tid, [tenant_by_id[tid]]) for tid in loc_info.get('tenant_ids', []) if tid in tenant_by_id]
            tenant_id, _ = M.best_candidate(str(raw.get('tenant') or ''), tenant_cands)

        # Destination (optional) — matched against hubs + is_destination origins by name.
        # Blank / no column → None (destination is optional and never causes exclusion).
        destination_id = None
        dest_val = raw.get('destination')
        if not M.is_blank(dest_val) and ctx.get('destinations'):
            dest_cands = [(d['id'], d['names']) for d in ctx['destinations']]
            destination_id, _ = M.best_candidate(str(dest_val), dest_cands)
        destination_label = None
        if destination_id is not None:
            destination_label = next(
                (d['display'] for d in ctx['destinations'] if d['id'] == destination_id), None)

        # Exclusion: a row must resolve to a location + material + positive weight + a date.
        reason = None
        if origin_id is None:
            reason = 'no_location'
        elif dt is None:
            reason = 'missing_date'
        elif mat is None:
            reason = 'no_waste_type'
        elif weight is None or weight <= 0:
            reason = 'missing_weight'

        return {
            'row_index': raw.get('row_index'),
            'excluded': reason is not None,
            'reason': reason,
            'date': dt.isoformat() if dt else None,
            'origin_id': origin_id,
            'origin_label': path_label or (loc_by_id.get(origin_id, {}).get('display') if origin_id else ''),
            'tag_id': tag_id,
            'tag_label': tag_by_id.get(tag_id) if tag_id else None,
            'tenant_id': tenant_id,
            'tenant_label': tenant_by_id.get(tenant_id) if tenant_id else None,
            'material_id': material_id,
            'main_material_id': mat['main_material_id'] if mat else None,
            'category_id': mat['category_id'] if mat else None,
            'unit': (mat['unit_name_th'] or mat['unit_name_en']) if mat else None,
            'unit_weight': mat['unit_weight'] if mat else 1.0,
            'material_label': (mat['name_th'] or mat['name_en']) if mat else None,
            'unit_label': (mat['unit_name_th'] or mat['unit_name_en']) if mat else None,
            'weight': weight,
            'destination_id': destination_id,
            'destination_label': destination_label,
            'raw': {
                'level1': M._clean(raw.get('level1')), 'level2': M._clean(raw.get('level2')),
                'level3': M._clean(raw.get('level3')), 'level4': M._clean(raw.get('level4')),
                'tag': M._clean(raw.get('tag')), 'tenant': M._clean(raw.get('tenant')),
                'waste_type': M._clean(raw.get('waste_type')), 'weight': M._clean(raw.get('weight')),
                'date': M._clean(raw.get('date')), 'destination': M._clean(raw.get('destination')),
            },
        }

    @staticmethod
    def _row_is_confirmable(r: Dict[str, Any]) -> bool:
        if r.get('excluded'):
            return False
        try:
            weight = float(r.get('weight') or 0)
        except (TypeError, ValueError):
            return False
        return bool(
            r.get('origin_id') and r.get('main_material_id')
            and r.get('category_id') and r.get('unit') and r.get('date') and weight > 0
        )

    @staticmethod
    def _summarize(review_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        usable = [r for r in review_rows if not r.get('excluded')]
        excluded = [r for r in review_rows if r.get('excluded')]
        keys = {
            (r.get('origin_id'), r.get('date'), r.get('tag_id'), r.get('tenant_id'))
            for r in usable
        }
        return {
            'total_rows': len(review_rows),
            'records': len(usable),
            'excluded': len(excluded),
            'transactions': len(keys),
        }
