"""
Supplier Portal Service — Magic Link Authentication
"""

import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import logging

from GEPPPlatform.models.esg.supplier_magic_links import EsgSupplierMagicLink
from GEPPPlatform.models.esg.suppliers import EsgSupplier
from GEPPPlatform.models.esg.supplier_submissions import EsgSupplierSubmission

logger = logging.getLogger(__name__)

# Tier 1 business-level questions (simple form)
TIER1_SCHEMA = {
    'type': 'tier1',
    'title': 'Supplier Emissions Data Collection (Tier 1)',
    'fields': [
        {'key': 'electricity_kwh', 'label': 'Electricity consumption (kWh)', 'type': 'number', 'required': True},
        {'key': 'electricity_thb', 'label': 'Electricity cost (THB)', 'type': 'number', 'required': False},
        {'key': 'fuel_liters', 'label': 'Fuel consumption (liters)', 'type': 'number', 'required': True},
        {'key': 'fuel_type', 'label': 'Fuel type', 'type': 'select', 'options': ['diesel', 'gasoline', 'lpg', 'natural_gas'], 'required': True},
        {'key': 'water_m3', 'label': 'Water consumption (m3)', 'type': 'number', 'required': False},
        {'key': 'waste_kg', 'label': 'Waste generated (kg)', 'type': 'number', 'required': False},
        {'key': 'transport_km', 'label': 'Transport distance to buyer (km)', 'type': 'number', 'required': False},
        {'key': 'transport_mode', 'label': 'Transport mode', 'type': 'select', 'options': ['road', 'rail', 'sea', 'air'], 'required': False},
        {'key': 'employees', 'label': 'Number of employees', 'type': 'number', 'required': False},
        {'key': 'revenue_thb', 'label': 'Annual revenue (THB)', 'type': 'number', 'required': False},
        {'key': 'reporting_period_start', 'label': 'Period start', 'type': 'date', 'required': True},
        {'key': 'reporting_period_end', 'label': 'Period end', 'type': 'date', 'required': True},
        {'key': 'notes', 'label': 'Additional notes', 'type': 'textarea', 'required': False},
    ],
}

# Tier 2 — CSV upload schema
TIER2_SCHEMA = {
    'type': 'tier2',
    'title': 'Supplier Emissions Data Collection (Tier 2 — CSV Upload)',
    'fields': [
        {'key': 'csv_file', 'label': 'Upload CSV file', 'type': 'file', 'accept': '.csv,.xlsx', 'required': True},
        {'key': 'reporting_period_start', 'label': 'Period start', 'type': 'date', 'required': True},
        {'key': 'reporting_period_end', 'label': 'Period end', 'type': 'date', 'required': True},
        {'key': 'notes', 'label': 'Additional notes', 'type': 'textarea', 'required': False},
    ],
    'csv_columns': [
        'activity_type', 'activity_description', 'quantity', 'unit',
        'emission_factor', 'emission_factor_source', 'tco2e',
    ],
}


class SupplierPortalService:
    """Supplier-facing portal: magic link auth, form schemas, submission."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Magic link
    # ------------------------------------------------------------------

    def create_magic_link(
        self,
        supplier_id: int,
        org_id: int,
        email: Optional[str] = None,
        expires_days: int = 30,
    ) -> Dict[str, Any]:
        """Generate a 64-char magic-link token for a supplier."""
        token = secrets.token_urlsafe(48)[:64]
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        link = EsgSupplierMagicLink(
            supplier_id=supplier_id,
            organization_id=org_id,
            token=token,
            email=email,
            expires_at=expires_at,
            status='active',
        )
        self.session.add(link)
        self.session.flush()

        portal_url = f'/supplier-portal?token={token}'
        return {
            'token': token,
            'url': portal_url,
            'expires_at': expires_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Token verification
    # ------------------------------------------------------------------

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify a magic-link token. Returns supplier context or error."""
        link = self.session.query(EsgSupplierMagicLink).filter(
            EsgSupplierMagicLink.token == token,
        ).first()

        if not link:
            return {'valid': False, 'error': 'Token not found'}

        if link.status != 'active':
            return {'valid': False, 'error': 'Token has already been used'}

        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            return {'valid': False, 'error': 'Token has expired'}

        supplier = self.session.query(EsgSupplier).filter(
            EsgSupplier.id == link.supplier_id,
            EsgSupplier.is_active == True,
        ).first()

        if not supplier:
            return {'valid': False, 'error': 'Supplier not found'}

        return {
            'valid': True,
            'supplier': supplier.to_dict(),
            'organization_id': link.organization_id,
            'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        }

    # ------------------------------------------------------------------
    # Form schema
    # ------------------------------------------------------------------

    def get_form_schema(self, token: str) -> Optional[Dict[str, Any]]:
        """Return the form schema appropriate for the supplier's tier."""
        verification = self.verify_token(token)
        if not verification.get('valid'):
            return None

        supplier = verification['supplier']
        tier = supplier.get('data_collection_level', 'tier1')

        schema = TIER1_SCHEMA if tier == 'tier1' else TIER2_SCHEMA

        return {
            'supplier': supplier,
            'schema': schema,
        }

    # ------------------------------------------------------------------
    # Submit data
    # ------------------------------------------------------------------

    def submit_data(self, token: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a supplier submission and mark the token as used."""
        verification = self.verify_token(token)
        if not verification.get('valid'):
            return {'error': verification.get('error', 'Invalid token')}

        link = self.session.query(EsgSupplierMagicLink).filter(
            EsgSupplierMagicLink.token == token,
        ).first()

        supplier_id = link.supplier_id
        org_id = link.organization_id

        # Determine reporting year from data or current year
        reporting_year = data.get('reporting_year', datetime.now(timezone.utc).year)

        submission = EsgSupplierSubmission(
            supplier_id=supplier_id,
            organization_id=org_id,
            reporting_year=reporting_year,
            raw_data=data,
            status='submitted',
        )
        self.session.add(submission)

        # Mark token as used
        link.status = 'used'
        link.used_at = datetime.now(timezone.utc)
        self.session.flush()

        return {
            'submission_id': submission.id,
            'status': 'submitted',
            'message': 'Data submitted successfully',
        }

    # ------------------------------------------------------------------
    # Submission history
    # ------------------------------------------------------------------

    def get_submission_history(self, token: str) -> Optional[List[Dict[str, Any]]]:
        """Return past submissions for the supplier associated with the token."""
        link = self.session.query(EsgSupplierMagicLink).filter(
            EsgSupplierMagicLink.token == token,
        ).first()

        if not link:
            return None

        # Allow viewing history even if token is used (but not expired)
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            return None

        submissions = (
            self.session.query(EsgSupplierSubmission)
            .filter(EsgSupplierSubmission.supplier_id == link.supplier_id)
            .order_by(EsgSupplierSubmission.created_date.desc())
            .limit(50)
            .all()
        )
        return [s.to_dict() for s in submissions]
