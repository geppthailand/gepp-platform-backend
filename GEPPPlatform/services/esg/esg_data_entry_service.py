"""
ESG Data Entry Service - CRUD operations for manual data submissions (UC 2.1)
"""

from datetime import date
from GEPPPlatform.models.esg.data_entries import EsgDataEntry
from GEPPPlatform.services.esg.esg_categorization_service import EsgCategorizationService


class EsgDataEntryService:

    def __init__(self, session):
        self.session = session
        self.categorization = EsgCategorizationService(session)

    def create_entry(self, organization_id: int, user_id: int, data: dict) -> dict:
        """Create a new data entry and auto-categorize it."""
        scope_tag = self.categorization.categorize(
            category_id=data.get('category_id'),
            subcategory_id=data.get('subcategory_id'),
        )

        entry = EsgDataEntry(
            organization_id=organization_id,
            user_id=user_id,
            category_id=data['category_id'],
            subcategory_id=data['subcategory_id'],
            datapoint_id=data.get('datapoint_id'),
            value=data['value'],
            unit=data['unit'],
            entry_date=data.get('entry_date'),
            notes=data.get('notes'),
            file_key=data.get('file_key'),
            file_name=data.get('file_name'),
            scope_tag=scope_tag,
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry.to_dict()

    def get_entry(self, entry_id: int, organization_id: int) -> dict | None:
        """Get a single data entry by ID."""
        entry = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.id == entry_id,
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .first()
        )
        return entry.to_dict() if entry else None

    def list_entries(self, organization_id: int, page: int = 1, size: int = 10) -> dict:
        """List data entries with pagination."""
        query = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .order_by(EsgDataEntry.created_date.desc())
        )
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
        """Update an existing data entry."""
        entry = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.id == entry_id,
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .first()
        )
        if not entry:
            return None

        for key, value in data.items():
            if hasattr(entry, key) and key not in ('id', 'organization_id', 'user_id', 'created_date'):
                setattr(entry, key, value)

        self.session.commit()
        self.session.refresh(entry)
        return entry.to_dict()

    def delete_entry(self, entry_id: int, organization_id: int) -> bool:
        """Soft-delete a data entry."""
        entry = (
            self.session.query(EsgDataEntry)
            .filter(
                EsgDataEntry.id == entry_id,
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
            )
            .first()
        )
        if not entry:
            return False
        entry.is_active = False
        self.session.commit()
        return True
