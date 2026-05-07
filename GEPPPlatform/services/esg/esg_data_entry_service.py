"""
ESG Data Entry Service — record-centric (esg_records).

The legacy `esg_data_entries` table has been retired. Every operation
now reads/writes `EsgRecord` rows whose datapoints live in a JSONB
column. The list/get response shape is preserved (one item per record)
so the LIFF history and admin pages don't need changes.
"""

from datetime import date, datetime, timezone
from sqlalchemy import or_, func

from GEPPPlatform.models.esg.records import EsgRecord, GhgStatus
from GEPPPlatform.models.esg.data_hierarchy import EsgDataCategory
from GEPPPlatform.services.esg.esg_carbon_service import EsgCarbonService
from GEPPPlatform.services.esg.esg_categorization_service import EsgCategorizationService


class EsgDataEntryService:

    def __init__(self, session):
        self.session = session
        self.categorization = EsgCategorizationService(session)
        self.carbon = EsgCarbonService(session)

    def create_entry(self, organization_id: int, user_id: int, data: dict,
                     entry_source: str = 'LIFF_MANUAL', line_user_id: str = None) -> dict:
        """
        LIFF / desktop manual entry. Becomes a single-datapoint
        EsgRecord. The LIFF form supplies category, value and unit;
        we wrap that into the JSONB datapoints array and run the same
        GHG sufficiency check as the LINE-image extractor.
        """
        category_name = data.get('category', '')
        category_id = data.get('category_id')

        # Resolve scope3_category_id + pillar
        scope3_id = None
        pillar = None
        if category_id:
            cat_row = self.session.query(EsgDataCategory).filter(
                EsgDataCategory.id == category_id,
            ).first()
            if cat_row:
                scope3_id = int(cat_row.scope3_category_id) if cat_row.scope3_category_id else None
                pillar = cat_row.pillar

        unit = (data.get('unit') or '').strip() or None
        value = data.get('value')
        dp_label = (data.get('datapoint_name') or category_name or 'value').strip()

        datapoints = [{
            'datapoint_id': data.get('datapoint_id'),
            'datapoint_name': dp_label,
            'canonical_name': None,
            'is_canonical': False,
            'value': value,
            'unit': unit,
            'confidence': 1.0,
            'tags': data.get('metadata', {}).get('tags', []) if isinstance(data.get('metadata'), dict) else [],
        }]

        ghg = self.carbon.evaluate_record_ghg(
            scope3_category_id=scope3_id,
            category_id=category_id,
            category_name=category_name,
            datapoints=datapoints,
        )

        entry_date = data.get('entry_date') or datetime.now(timezone.utc).date()
        record_label = (data.get('record_label')
                        or data.get('notes')
                        or dp_label
                        or 'รายการ')
        if isinstance(record_label, str):
            record_label = record_label[:255]

        rec = EsgRecord(
            organization_id=organization_id,
            line_user_id=line_user_id,
            user_id=user_id,
            extraction_id=None,
            evidence_image_url=data.get('evidence_image_url'),
            file_key=data.get('file_key'),
            category_id=category_id,
            subcategory_id=data.get('subcategory_id'),
            scope3_category_id=scope3_id,
            pillar=pillar,
            record_label=record_label,
            entry_date=entry_date,
            datapoints=datapoints,
            kgco2e=ghg.get('kgco2e'),
            ghg_status=ghg.get('status') or GhgStatus.PENDING,
            ghg_method=ghg.get('method'),
            ghg_missing_fields=ghg.get('missing_fields') or [],
            ghg_reason=ghg.get('reason'),
            currency=data.get('currency'),
            status='PENDING_VERIFY',
            entry_source='LINE_CHAT' if entry_source == 'LINE_CHAT' else 'LIFF_MANUAL',
            notes=data.get('notes'),
        )
        self.session.add(rec)
        self.session.commit()
        self.session.refresh(rec)
        return self._record_to_legacy_dict(rec)

    def verify_entry(self, entry_id: int, organization_id: int) -> dict | None:
        rec = self._get_active_record(entry_id, organization_id)
        if not rec:
            return None
        rec.status = 'VERIFIED'
        self.session.commit()
        self.session.refresh(rec)
        return self._record_to_legacy_dict(rec)

    def get_entry(self, entry_id: int, organization_id: int) -> dict | None:
        rec = self._get_active_record(entry_id, organization_id)
        return self._record_to_legacy_dict(rec) if rec else None

    def list_entries(self, organization_id: int, page: int = 1, size: int = 10,
                     status: str = None, user_id: int = None) -> dict:
        """
        List records as legacy-shaped entry dicts (one item per
        EsgRecord row). Per-user filter mirrors the legacy OR on
        user_id / line_user_id.
        """
        query = (
            self.session.query(EsgRecord)
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
            )
        )
        if user_id is not None:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            if line_uid:
                query = query.filter(or_(
                    EsgRecord.user_id == user_id,
                    EsgRecord.line_user_id == line_uid,
                ))
            else:
                query = query.filter(EsgRecord.user_id == user_id)
        if status:
            query = query.filter(EsgRecord.status == status)

        query = query.order_by(EsgRecord.created_date.desc())
        total = query.count()
        rows = query.offset((page - 1) * size).limit(size).all()
        return {
            'data': [self._record_to_legacy_dict(r) for r in rows],
            'meta': {
                'page': page,
                'size': size,
                'total': total,
                'has_more': (page * size) < total,
                'is_user_scoped': user_id is not None,
            },
        }

    def update_entry(self, entry_id: int, organization_id: int, data: dict) -> dict | None:
        rec = self._get_active_record(entry_id, organization_id)
        if not rec:
            return None

        # Direct fields on the record
        for key in ('record_label', 'entry_date', 'notes', 'status',
                    'currency', 'category_id', 'subcategory_id'):
            if key in data and data[key] is not None:
                setattr(rec, key, data[key])

        # Single-datapoint update — for the legacy LIFF form, value/unit
        # are top-level. We update the first datapoint in the JSONB
        # array (or insert one if empty) and re-evaluate GHG.
        if any(k in data for k in ('value', 'unit', 'datapoint_name')):
            datapoints = list(rec.datapoints or [])
            head = datapoints[0] if datapoints else {}
            if 'value' in data:
                head['value'] = data['value']
            if 'unit' in data:
                head['unit'] = data['unit']
            if 'datapoint_name' in data:
                head['datapoint_name'] = data['datapoint_name']
            if not datapoints:
                datapoints = [head]
            else:
                datapoints[0] = head
            rec.datapoints = datapoints
            ghg = self.carbon.evaluate_record_ghg(
                scope3_category_id=rec.scope3_category_id,
                category_id=rec.category_id,
                category_name=data.get('category', '') or '',
                datapoints=datapoints,
            )
            rec.kgco2e = ghg.get('kgco2e')
            rec.ghg_status = ghg.get('status') or GhgStatus.PENDING
            rec.ghg_method = ghg.get('method')
            rec.ghg_missing_fields = ghg.get('missing_fields') or []
            rec.ghg_reason = ghg.get('reason')

        self.session.commit()
        self.session.refresh(rec)
        return self._record_to_legacy_dict(rec)

    def delete_entry(self, entry_id: int, organization_id: int) -> bool:
        rec = self._get_active_record(entry_id, organization_id)
        if not rec:
            return False
        rec.is_active = False
        self.session.commit()
        return True

    def _get_active_record(self, entry_id: int, organization_id: int):
        return (
            self.session.query(EsgRecord)
            .filter(
                EsgRecord.id == entry_id,
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
            )
            .first()
        )

    def _record_to_legacy_dict(self, rec: 'EsgRecord') -> dict:
        """
        Project an EsgRecord into the response shape the LIFF history
        / desktop pages already consume — the legacy `EsgDataEntry`
        dict. Reads the head datapoint as the "value/unit/datapoint_id"
        of the entry; the full datapoints array is exposed under
        `metadata.datapoints` for richer detail views.
        """
        if rec is None:
            return None
        datapoints = rec.datapoints or []
        head = datapoints[0] if datapoints else {}
        meta = {
            'datapoints': datapoints,
            'record_label': rec.record_label,
            'ghg_status': rec.ghg_status,
            'ghg_method': rec.ghg_method,
            'ghg_missing_fields': rec.ghg_missing_fields or [],
            'ghg_reason': rec.ghg_reason,
        }
        kg = float(rec.kgco2e) if rec.kgco2e is not None else None
        return {
            'id': rec.id,
            'organization_id': rec.organization_id,
            'user_id': rec.user_id,
            'line_user_id': rec.line_user_id,
            'category_id': rec.category_id,
            'subcategory_id': rec.subcategory_id,
            'datapoint_id': head.get('datapoint_id'),
            'category': '',  # category name resolved via category_id by FE
            'value': head.get('value'),
            'unit': head.get('unit'),
            'calculated_tco2e': (kg / 1000.0) if kg is not None else None,
            'entry_date': str(rec.entry_date) if rec.entry_date else None,
            'record_date': str(rec.entry_date) if rec.entry_date else None,
            'notes': rec.notes,
            'file_key': rec.file_key,
            'file_name': None,
            'evidence_image_url': rec.evidence_image_url,
            'scope_tag': rec.pillar,
            'metadata': meta,
            'extra_data': meta,
            'currency': rec.currency,
            'entry_source': rec.entry_source,
            'status': rec.status,
            'is_active': rec.is_active,
            'created_date': rec.created_date.isoformat() if rec.created_date else None,
            'updated_date': rec.updated_date.isoformat() if rec.updated_date else None,
        }

    def _resolve_line_user_id(self, esg_user_id: int, organization_id: int = None) -> str | None:
        """
        Look up the LINE platform user ID for an EsgUser. Used by
        list_entries to OR the per-user filter on line_user_id, so legacy
        entries saved with user_id=0 (created before the EsgUser-id
        backfill in _create_entry_from_extraction) still surface.

        Defensive: when organization_id is supplied, also filter
        EsgUser.organization_id so a leaked / wrong-org JWT can't pull a
        LINE id from another org's user.
        """
        if not esg_user_id:
            return None
        try:
            from ...models.esg.esg_users import EsgUser
            q = (
                self.session.query(EsgUser)
                .filter(EsgUser.id == esg_user_id, EsgUser.platform == 'line')
            )
            if organization_id is not None:
                q = q.filter(EsgUser.organization_id == organization_id)
            row = q.first()
            return row.platform_user_id if row else None
        except Exception:
            return None
