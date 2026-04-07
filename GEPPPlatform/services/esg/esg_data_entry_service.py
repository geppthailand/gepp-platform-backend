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

        # Calculate tCO2e
        calculated_tco2e = None
        if category_name and data.get('value') and data.get('unit'):
            calculated_tco2e = self.carbon.calculate_tco2e(
                category=category_name,
                amount=float(data['value']),
                unit=data['unit'],
            )
            if calculated_tco2e is None and scope_tag:
                calculated_tco2e = self.carbon.calculate_tco2e(
                    category=scope_tag,
                    amount=float(data['value']),
                    unit=data['unit'],
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
                     status: str = None) -> dict:
        query = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
        )
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
