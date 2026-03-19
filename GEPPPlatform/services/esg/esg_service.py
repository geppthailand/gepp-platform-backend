"""
ESG Service — CRUD for settings, waste records, emission factors, dashboard KPIs
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from datetime import datetime, date
from decimal import Decimal
import logging

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.emission_factors import EsgEmissionFactor
from ...models.esg.waste_records import EsgWasteRecord
from ...models.esg.documents import EsgDocument
from ...models.esg.summaries import EsgScope3Summary

logger = logging.getLogger(__name__)


class EsgService:
    """ESG business logic service"""

    def __init__(self, db: Session):
        self.db = db

    # ========== SETTINGS ==========

    def get_settings(self, organization_id: int) -> Dict[str, Any]:
        """Get or create ESG settings for organization"""
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.organization_id == organization_id,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            # Create default settings
            settings = EsgOrganizationSettings(organization_id=organization_id)
            self.db.add(settings)
            self.db.flush()

        return {'success': True, 'settings': settings.to_dict()}

    def update_settings(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update ESG settings for organization"""
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.organization_id == organization_id,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            settings = EsgOrganizationSettings(organization_id=organization_id)
            self.db.add(settings)

        # Update fields
        updatable_fields = [
            'reporting_year', 'methodology', 'organizational_boundary',
            'base_year', 'reduction_target_percent', 'reduction_target_year',
            'line_channel_id', 'line_channel_secret', 'line_channel_token',
            'line_webhook_url', 'line_rich_menu_id'
        ]
        for field in updatable_fields:
            if field in data and data[field] is not None:
                setattr(settings, field, data[field])

        self.db.flush()
        return {'success': True, 'message': 'Settings updated', 'settings': settings.to_dict()}

    # ========== EMISSION FACTORS ==========

    def list_emission_factors(self, waste_type: str = None, treatment_method: str = None, source: str = None) -> Dict[str, Any]:
        """List emission factors with optional filters"""
        query = self.db.query(EsgEmissionFactor).filter(EsgEmissionFactor.is_active == True)

        if waste_type:
            query = query.filter(EsgEmissionFactor.waste_type == waste_type)
        if treatment_method:
            query = query.filter(EsgEmissionFactor.treatment_method == treatment_method)
        if source:
            query = query.filter(EsgEmissionFactor.source == source)

        factors = query.order_by(EsgEmissionFactor.waste_type, EsgEmissionFactor.treatment_method).all()
        return {'success': True, 'emission_factors': [f.to_dict() for f in factors]}

    def get_emission_factor(self, waste_type: str, treatment_method: str, country_code: str = 'TH') -> Optional[EsgEmissionFactor]:
        """Get best matching emission factor"""
        # Try country-specific first, then global
        factor = self.db.query(EsgEmissionFactor).filter(
            EsgEmissionFactor.waste_type == waste_type,
            EsgEmissionFactor.treatment_method == treatment_method,
            EsgEmissionFactor.country_code == country_code,
            EsgEmissionFactor.is_active == True
        ).first()

        if not factor:
            # Fallback to global (country_code IS NULL)
            factor = self.db.query(EsgEmissionFactor).filter(
                EsgEmissionFactor.waste_type == waste_type,
                EsgEmissionFactor.treatment_method == treatment_method,
                EsgEmissionFactor.country_code.is_(None),
                EsgEmissionFactor.is_active == True
            ).first()

        if not factor:
            # Fallback to general waste type
            factor = self.db.query(EsgEmissionFactor).filter(
                EsgEmissionFactor.waste_type == 'general',
                EsgEmissionFactor.treatment_method == treatment_method,
                EsgEmissionFactor.country_code == country_code,
                EsgEmissionFactor.is_active == True
            ).first()

        return factor

    # ========== WASTE RECORDS ==========

    def create_waste_record(self, organization_id: int, data: Dict[str, Any], created_by_id: int = None) -> Dict[str, Any]:
        """Create a waste record with automatic CO2e calculation"""
        record = EsgWasteRecord(
            organization_id=organization_id,
            record_date=data['record_date'],
            waste_type=data['waste_type'],
            waste_category=data.get('waste_category'),
            treatment_method=data['treatment_method'],
            weight_kg=data['weight_kg'],
            data_quality=data.get('data_quality', 'estimated'),
            source=data.get('source', 'manual'),
            origin_location_id=data.get('origin_location_id'),
            vendor_name=data.get('vendor_name'),
            cost=data.get('cost'),
            currency=data.get('currency', 'THB'),
            notes=data.get('notes'),
            document_id=data.get('document_id'),
            created_by_id=created_by_id,
        )

        # Auto-calculate CO2e
        factor = self.get_emission_factor(record.waste_type, record.treatment_method)
        if factor:
            record.emission_factor_id = factor.id
            record.emission_factor_value = factor.factor_value
            record.calculate_co2e()

        self.db.add(record)
        self.db.flush()

        return {'success': True, 'message': 'Waste record created', 'waste_record': record.to_dict()}

    def bulk_create_waste_records(self, organization_id: int, document_id: int, records_data: List[Dict[str, Any]], created_by_id: int = None) -> Dict[str, Any]:
        """Bulk create waste records from AI extraction"""
        created = []
        for data in records_data:
            data['document_id'] = document_id
            data['source'] = 'ai'
            result = self.create_waste_record(organization_id, data, created_by_id)
            if result['success']:
                created.append(result['waste_record'])

        return {
            'success': True,
            'message': f'Created {len(created)} waste records',
            'waste_records': created,
            'count': len(created)
        }

    def list_waste_records(
        self, organization_id: int,
        page: int = 1, page_size: int = 20,
        waste_type: str = None, treatment_method: str = None,
        date_from: str = None, date_to: str = None,
        verification_status: str = None
    ) -> Dict[str, Any]:
        """List waste records with filtering and pagination"""
        query = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True,
            EsgWasteRecord.deleted_date.is_(None)
        )

        if waste_type:
            query = query.filter(EsgWasteRecord.waste_type == waste_type)
        if treatment_method:
            query = query.filter(EsgWasteRecord.treatment_method == treatment_method)
        if date_from:
            query = query.filter(EsgWasteRecord.record_date >= date_from)
        if date_to:
            query = query.filter(EsgWasteRecord.record_date <= date_to)
        if verification_status:
            query = query.filter(EsgWasteRecord.verification_status == verification_status)

        total = query.count()
        records = query.order_by(EsgWasteRecord.record_date.desc(), EsgWasteRecord.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return {
            'success': True,
            'waste_records': [r.to_dict() for r in records],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            }
        }

    def get_waste_record(self, record_id: int, organization_id: int) -> Dict[str, Any]:
        """Get a single waste record"""
        record = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.id == record_id,
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True
        ).first()

        if not record:
            return {'success': False, 'message': 'Waste record not found'}
        return {'success': True, 'waste_record': record.to_dict()}

    def update_waste_record(self, record_id: int, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a waste record"""
        record = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.id == record_id,
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True
        ).first()

        if not record:
            return {'success': False, 'message': 'Waste record not found'}

        updatable = [
            'record_date', 'waste_type', 'waste_category', 'treatment_method',
            'weight_kg', 'data_quality', 'verification_status',
            'origin_location_id', 'vendor_name', 'cost', 'currency', 'notes'
        ]
        recalculate = False
        for field in updatable:
            if field in data:
                setattr(record, field, data[field])
                if field in ('waste_type', 'treatment_method', 'weight_kg'):
                    recalculate = True

        if recalculate:
            factor = self.get_emission_factor(record.waste_type, record.treatment_method)
            if factor:
                record.emission_factor_id = factor.id
                record.emission_factor_value = factor.factor_value
                record.calculate_co2e()

        self.db.flush()
        return {'success': True, 'message': 'Waste record updated', 'waste_record': record.to_dict()}

    def delete_waste_record(self, record_id: int, organization_id: int) -> Dict[str, Any]:
        """Soft delete a waste record"""
        record = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.id == record_id,
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True
        ).first()

        if not record:
            return {'success': False, 'message': 'Waste record not found'}

        record.is_active = False
        record.deleted_date = datetime.utcnow()
        self.db.flush()
        return {'success': True, 'message': 'Waste record deleted'}

    # ========== DOCUMENTS ==========

    def create_document(self, organization_id: int, data: Dict[str, Any], uploaded_by_id: int = None) -> Dict[str, Any]:
        """Create a document record"""
        doc = EsgDocument(
            organization_id=organization_id,
            file_name=data['file_name'],
            file_url=data['file_url'],
            file_type=data.get('file_type'),
            file_size_bytes=data.get('file_size_bytes'),
            esg_category=data.get('esg_category'),
            esg_subcategory=data.get('esg_subcategory'),
            document_type=data.get('document_type'),
            reporting_year=data.get('reporting_year'),
            source=data.get('source', 'upload'),
            uploaded_by_id=uploaded_by_id,
            notes=data.get('notes'),
            ai_classification_status='pending',
        )
        self.db.add(doc)
        self.db.flush()
        return {'success': True, 'message': 'Document created', 'document': doc.to_dict()}

    def list_documents(
        self, organization_id: int,
        page: int = 1, page_size: int = 20,
        esg_category: str = None, document_type: str = None,
        ai_status: str = None, source: str = None
    ) -> Dict[str, Any]:
        """List documents with filtering"""
        query = self.db.query(EsgDocument).filter(
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True,
            EsgDocument.deleted_date.is_(None)
        )

        if esg_category:
            query = query.filter(EsgDocument.esg_category == esg_category)
        if document_type:
            query = query.filter(EsgDocument.document_type == document_type)
        if ai_status:
            query = query.filter(EsgDocument.ai_classification_status == ai_status)
        if source:
            query = query.filter(EsgDocument.source == source)

        total = query.count()
        docs = query.order_by(EsgDocument.created_date.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return {
            'success': True,
            'documents': [d.to_dict() for d in docs],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            }
        }

    def get_document(self, document_id: int, organization_id: int) -> Dict[str, Any]:
        """Get a single document"""
        doc = self.db.query(EsgDocument).filter(
            EsgDocument.id == document_id,
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True
        ).first()

        if not doc:
            return {'success': False, 'message': 'Document not found'}
        return {'success': True, 'document': doc.to_dict()}

    # ========== DASHBOARD ==========

    def get_dashboard_kpis(self, organization_id: int, year: int = None) -> Dict[str, Any]:
        """Get dashboard KPIs for the organization"""
        if not year:
            year = datetime.utcnow().year

        # Waste records query for the year
        base_query = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True,
            EsgWasteRecord.deleted_date.is_(None),
            extract('year', EsgWasteRecord.record_date) == year
        )

        # Total waste and CO2e
        totals = base_query.with_entities(
            func.coalesce(func.sum(EsgWasteRecord.weight_kg), 0).label('total_kg'),
            func.coalesce(func.sum(EsgWasteRecord.co2e_kg), 0).label('total_co2e'),
            func.count(EsgWasteRecord.id).label('total_records')
        ).first()

        total_kg = float(totals.total_kg)
        total_co2e = float(totals.total_co2e)
        total_records = totals.total_records

        # Landfill diversion rate
        landfill_kg = float(base_query.filter(
            EsgWasteRecord.treatment_method == 'landfill'
        ).with_entities(
            func.coalesce(func.sum(EsgWasteRecord.weight_kg), 0)
        ).scalar() or 0)

        diversion_rate = ((total_kg - landfill_kg) / total_kg * 100) if total_kg > 0 else 0

        # Verified percentage
        verified_count = base_query.filter(
            EsgWasteRecord.verification_status == 'verified'
        ).count()
        verified_percent = (verified_count / total_records * 100) if total_records > 0 else 0

        # Documents count by category
        doc_counts = self.db.query(
            EsgDocument.esg_category,
            func.count(EsgDocument.id)
        ).filter(
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True,
            EsgDocument.deleted_date.is_(None)
        ).group_by(EsgDocument.esg_category).all()

        docs_by_category = {cat or 'uncategorized': count for cat, count in doc_counts}
        total_documents = sum(docs_by_category.values())

        return {
            'success': True,
            'kpis': {
                'total_co2e_tons': round(total_co2e / 1000, 4),
                'total_waste_kg': round(total_kg, 2),
                'landfill_diversion_rate': round(diversion_rate, 2),
                'total_records': total_records,
                'verified_percent': round(verified_percent, 2),
                'total_documents': total_documents,
                'documents_by_category': docs_by_category,
                'year': year,
            }
        }

    def get_dashboard_trends(self, organization_id: int, year: int = None) -> Dict[str, Any]:
        """Get monthly CO2e trends for the year"""
        if not year:
            year = datetime.utcnow().year

        monthly = self.db.query(
            extract('month', EsgWasteRecord.record_date).label('month'),
            func.coalesce(func.sum(EsgWasteRecord.weight_kg), 0).label('total_kg'),
            func.coalesce(func.sum(EsgWasteRecord.co2e_kg), 0).label('total_co2e'),
            func.count(EsgWasteRecord.id).label('count')
        ).filter(
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True,
            EsgWasteRecord.deleted_date.is_(None),
            extract('year', EsgWasteRecord.record_date) == year
        ).group_by('month').order_by('month').all()

        trends = []
        for row in monthly:
            trends.append({
                'period': f'{year}-{int(row.month):02d}',
                'month': int(row.month),
                'total_waste_kg': round(float(row.total_kg), 2),
                'total_co2e_kg': round(float(row.total_co2e), 4),
                'record_count': row.count,
            })

        return {'success': True, 'trends': trends, 'year': year}

    def get_dashboard_breakdown(self, organization_id: int, year: int = None, group_by: str = 'treatment_method') -> Dict[str, Any]:
        """Get breakdown by waste type or treatment method"""
        if not year:
            year = datetime.utcnow().year

        if group_by == 'waste_type':
            group_col = EsgWasteRecord.waste_type
        else:
            group_col = EsgWasteRecord.treatment_method

        rows = self.db.query(
            group_col.label('label'),
            func.coalesce(func.sum(EsgWasteRecord.weight_kg), 0).label('total_kg'),
            func.coalesce(func.sum(EsgWasteRecord.co2e_kg), 0).label('total_co2e'),
        ).filter(
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True,
            EsgWasteRecord.deleted_date.is_(None),
            extract('year', EsgWasteRecord.record_date) == year
        ).group_by('label').order_by(func.sum(EsgWasteRecord.co2e_kg).desc()).all()

        grand_total = sum(float(r.total_kg) for r in rows) or 1

        breakdown = []
        for row in rows:
            total_kg = float(row.total_kg)
            breakdown.append({
                'label': row.label,
                'total_kg': round(total_kg, 2),
                'total_co2e_kg': round(float(row.total_co2e), 4),
                'percentage': round(total_kg / grand_total * 100, 2),
            })

        return {'success': True, 'breakdown': breakdown, 'group_by': group_by, 'year': year}
