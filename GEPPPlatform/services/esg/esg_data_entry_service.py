"""
ESG Data Entry Service - CRUD with tCO2e auto-calculation and status management
"""

from datetime import date
from GEPPPlatform.models.esg.data_entries import EsgDataEntry, EntrySource, EntryStatus
from GEPPPlatform.services.esg.esg_carbon_service import EsgCarbonService
from GEPPPlatform.services.esg.esg_categorization_service import EsgCategorizationService


class EsgDataEntryService:

    def __init__(self, session):
        self.session = session
        self.categorization = EsgCategorizationService(session)
        self.carbon = EsgCarbonService(session)

    def create_entry(self, organization_id: int, user_id: int, data: dict,
                     entry_source: str = 'LIFF_MANUAL', line_user_id: str = None) -> dict:
        """Create a new data entry with auto tCO2e calculation."""
        category_name = data.get('category', '')
        scope_tag = self.categorization.categorize(
            category_id=data.get('category_id'),
            subcategory_id=data.get('subcategory_id'),
        )

        # Calculate tCO2e — pass category_id so the carbon service can resolve
        # the Scope 3 category id and apply the conservative default EF when
        # no DB factor matches (prevents the dashboard showing 0).
        calculated_tco2e = None
        if data.get('value') is not None and data.get('unit'):
            calculated_tco2e = self.carbon.calculate_tco2e(
                category=category_name,
                amount=float(data['value']),
                unit=data['unit'],
                category_id=data.get('category_id'),
            )
            if calculated_tco2e is None and scope_tag:
                calculated_tco2e = self.carbon.calculate_tco2e(
                    category=scope_tag,
                    amount=float(data['value']),
                    unit=data['unit'],
                    category_id=data.get('category_id'),
                )

        source_enum = EntrySource.LINE_CHAT if entry_source == 'LINE_CHAT' else EntrySource.LIFF_MANUAL

        entry = EsgDataEntry(
            organization_id=organization_id,
            user_id=user_id,
            line_user_id=line_user_id,
            category_id=data.get('category_id'),
            subcategory_id=data.get('subcategory_id'),
            datapoint_id=data.get('datapoint_id'),
            category=category_name,
            value=data['value'],
            unit=data['unit'],
            calculated_tco2e=calculated_tco2e,
            entry_date=data.get('entry_date'),
            record_date=data.get('record_date') or data.get('entry_date'),
            notes=data.get('notes'),
            file_key=data.get('file_key'),
            file_name=data.get('file_name'),
            evidence_image_url=data.get('evidence_image_url'),
            scope_tag=scope_tag,
            extra_data=data.get('metadata', {}),
            currency=data.get('currency'),
            entry_source=source_enum,
            status=EntryStatus.PENDING_VERIFY,
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry.to_dict()

    def verify_entry(self, entry_id: int, organization_id: int) -> dict | None:
        """Set entry status to VERIFIED."""
        entry = self._get_active_entry(entry_id, organization_id)
        if not entry:
            return None
        entry.status = EntryStatus.VERIFIED
        self.session.commit()
        self.session.refresh(entry)
        return entry.to_dict()

    def get_entry(self, entry_id: int, organization_id: int) -> dict | None:
        entry = self._get_active_entry(entry_id, organization_id)
        return entry.to_dict() if entry else None

    def list_entries(self, organization_id: int, page: int = 1, size: int = 10,
                     status: str = None, user_id: int = None) -> dict:
        """
        List entries.

        - desktop / admin callers: leave user_id=None → all org entries.
        - LIFF /api/esg/liff/entries: pass current EsgUser.id → only that
          LINE user's entries are returned. Each user sees their own
          history; the org-wide view stays on the desktop platform.

        Per-user filter is OR'd between EsgDataEntry.user_id and
        EsgDataEntry.line_user_id so legacy entries that were saved with
        user_id=0 (created via the LINE webhook before the EsgUser-id
        backfill landed) still surface for the right LIFF user.
        """
        query = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
        )
        if user_id is not None:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            if line_uid:
                from sqlalchemy import or_
                query = query.filter(or_(
                    EsgDataEntry.user_id == user_id,
                    EsgDataEntry.line_user_id == line_uid,
                ))
            else:
                query = query.filter(EsgDataEntry.user_id == user_id)
        if status:
            query = query.filter(EsgDataEntry.status == status)

        query = query.order_by(EsgDataEntry.created_date.desc())
        total = query.count()
        entries = query.offset((page - 1) * size).limit(size).all()
        return {
            'data': [e.to_dict() for e in entries],
            'meta': {
                'page': page,
                'size': size,
                'total': total,
                'has_more': (page * size) < total,
                'is_user_scoped': user_id is not None,
            },
        }

    def update_entry(self, entry_id: int, organization_id: int, data: dict) -> dict | None:
        entry = self._get_active_entry(entry_id, organization_id)
        if not entry:
            return None

        protected = ('id', 'organization_id', 'user_id', 'created_date', 'entry_source')
        for key, value in data.items():
            if hasattr(entry, key) and key not in protected:
                setattr(entry, key, value)

        # Recalculate tCO2e if value/unit/category changed
        if any(k in data for k in ('value', 'unit', 'category')):
            cat = data.get('category', entry.category)
            val = float(data.get('value', entry.value))
            unit = data.get('unit', entry.unit)
            if cat and val and unit:
                entry.calculated_tco2e = self.carbon.calculate_tco2e(cat, val, unit)

        self.session.commit()
        self.session.refresh(entry)
        return entry.to_dict()

    def delete_entry(self, entry_id: int, organization_id: int) -> bool:
        entry = self._get_active_entry(entry_id, organization_id)
        if not entry:
            return False
        entry.is_active = False
        self.session.commit()
        return True

    def _get_active_entry(self, entry_id: int, organization_id: int):
        return (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.id == entry_id,
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .first()
        )

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
