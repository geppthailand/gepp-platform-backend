"""
Supplier CRUD Service
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timezone
import logging

from GEPPPlatform.models.esg.suppliers import EsgSupplier
from GEPPPlatform.models.esg.supplier_submissions import EsgSupplierSubmission

logger = logging.getLogger(__name__)


class SupplierService:
    """Manage supplier records for an organization."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_suppliers(
        self,
        org_id: int,
        status: Optional[str] = None,
        tier: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        size: int = 50,
    ) -> Dict[str, Any]:
        """Return paginated supplier list with optional filters."""
        query = self.session.query(EsgSupplier).filter(
            EsgSupplier.organization_id == org_id,
            EsgSupplier.is_active == True,
        )

        if status:
            query = query.filter(EsgSupplier.status == status)
        if tier:
            query = query.filter(EsgSupplier.data_collection_level == tier)
        if search:
            like = f'%{search}%'
            query = query.filter(
                or_(
                    EsgSupplier.company_name.ilike(like),
                    EsgSupplier.contact_email.ilike(like),
                    EsgSupplier.tax_id.ilike(like),
                )
            )

        total = query.count()
        suppliers = (
            query.order_by(EsgSupplier.created_date.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        return {
            'suppliers': [s.to_dict() for s in suppliers],
            'total': total,
            'page': page,
            'size': size,
            'pages': (total + size - 1) // size if size else 1,
        }

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def get_supplier(self, org_id: int, supplier_id: int) -> Optional[Dict[str, Any]]:
        """Return a single supplier dict or None."""
        supplier = self.session.query(EsgSupplier).filter(
            EsgSupplier.id == supplier_id,
            EsgSupplier.organization_id == org_id,
            EsgSupplier.is_active == True,
        ).first()
        return supplier.to_dict() if supplier else None

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_supplier(self, org_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new supplier and return its dict representation."""
        supplier = EsgSupplier(
            organization_id=org_id,
            company_name=data['company_name'],
            tax_id=data.get('tax_id'),
            contact_name=data.get('contact_name'),
            contact_email=data.get('contact_email'),
            contact_phone=data.get('contact_phone'),
            country=data.get('country'),
            industry=data.get('industry'),
            data_collection_level=data.get('data_collection_level', 'tier1'),
            scope3_category=data.get('scope3_category'),
            annual_spend_thb=data.get('annual_spend_thb'),
            status=data.get('status', 'pending'),
        )
        self.session.add(supplier)
        self.session.flush()
        return supplier.to_dict()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_supplier(
        self, org_id: int, supplier_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update supplier fields. Returns updated dict or None."""
        supplier = self.session.query(EsgSupplier).filter(
            EsgSupplier.id == supplier_id,
            EsgSupplier.organization_id == org_id,
            EsgSupplier.is_active == True,
        ).first()
        if not supplier:
            return None

        updatable = [
            'company_name', 'tax_id', 'contact_name', 'contact_email',
            'contact_phone', 'country', 'industry', 'data_collection_level',
            'scope3_category', 'annual_spend_thb', 'status',
        ]
        for field in updatable:
            if field in data:
                setattr(supplier, field, data[field])

        supplier.updated_date = datetime.now(timezone.utc)
        self.session.flush()
        return supplier.to_dict()

    # ------------------------------------------------------------------
    # Soft delete
    # ------------------------------------------------------------------

    def delete_supplier(self, org_id: int, supplier_id: int) -> bool:
        """Soft-delete a supplier (set is_active=False)."""
        supplier = self.session.query(EsgSupplier).filter(
            EsgSupplier.id == supplier_id,
            EsgSupplier.organization_id == org_id,
            EsgSupplier.is_active == True,
        ).first()
        if not supplier:
            return False

        supplier.is_active = False
        supplier.deleted_date = datetime.now(timezone.utc)
        self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Bulk import
    # ------------------------------------------------------------------

    def bulk_import(
        self, org_id: int, suppliers_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create multiple suppliers. Returns summary with error details."""
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        for idx, row in enumerate(suppliers_data):
            try:
                if not row.get('company_name'):
                    raise ValueError('company_name is required')
                self.create_supplier(org_id, row)
                success += 1
            except Exception as e:
                failed += 1
                errors.append({'row': idx, 'error': str(e)})

        self.session.flush()
        return {
            'total': len(suppliers_data),
            'success': success,
            'failed': failed,
            'errors': errors,
        }

    # ------------------------------------------------------------------
    # Submission status (traffic-light)
    # ------------------------------------------------------------------

    def get_submission_status(self, org_id: int) -> Dict[str, Any]:
        """
        Return traffic-light summary of supplier submission status.
        green  = submitted & approved within current year
        amber  = submitted but pending review
        red    = no submission this year
        """
        suppliers = (
            self.session.query(EsgSupplier)
            .filter(
                EsgSupplier.organization_id == org_id,
                EsgSupplier.is_active == True,
            )
            .all()
        )

        current_year = datetime.now(timezone.utc).year
        green, amber, red = 0, 0, 0
        details: List[Dict[str, Any]] = []

        for s in suppliers:
            latest = (
                self.session.query(EsgSupplierSubmission)
                .filter(
                    EsgSupplierSubmission.supplier_id == s.id,
                    EsgSupplierSubmission.reporting_year == current_year,
                )
                .order_by(EsgSupplierSubmission.created_date.desc())
                .first()
            )

            if latest and latest.status == 'approved':
                color = 'green'
                green += 1
            elif latest and latest.status in ('submitted', 'pending'):
                color = 'amber'
                amber += 1
            else:
                color = 'red'
                red += 1

            details.append({
                'supplier_id': s.id,
                'company_name': s.company_name,
                'color': color,
                'last_submission': latest.to_dict() if latest else None,
            })

        return {
            'total': len(suppliers),
            'green': green,
            'amber': amber,
            'red': red,
            'suppliers': details,
        }
