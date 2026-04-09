"""
Supplier Submission Service
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

from GEPPPlatform.models.esg.supplier_submissions import EsgSupplierSubmission

logger = logging.getLogger(__name__)

# Basic emission factors (tCO2e per unit) — placeholder values
EMISSION_FACTORS = {
    'electricity_kwh': 0.0005,      # Grid average Thailand ~0.5 kgCO2/kWh
    'fuel_liters_diesel': 0.00268,  # ~2.68 kgCO2/L
    'fuel_liters_gasoline': 0.00231,
    'fuel_liters_lpg': 0.00163,
    'fuel_liters_natural_gas': 0.00202,
    'water_m3': 0.000344,
    'waste_kg': 0.00058,
    'transport_km_road': 0.000105,  # per tonne-km
    'transport_km_rail': 0.000028,
    'transport_km_sea': 0.000016,
    'transport_km_air': 0.000602,
}


class SupplierSubmissionService:
    """Handle supplier data submissions, review, and tCO2e calculations."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_submission(
        self, supplier_id: int, org_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new submission record."""
        submission = EsgSupplierSubmission(
            supplier_id=supplier_id,
            organization_id=org_id,
            reporting_year=data.get('reporting_year', datetime.now(timezone.utc).year),
            raw_data=data.get('raw_data', data),
            status='submitted',
        )
        self.session.add(submission)
        self.session.flush()

        # Auto-calculate tCO2e
        tco2e = self.calculate_tco2e(submission)
        submission.tco2e_calculated = tco2e
        self.session.flush()

        return submission.to_dict()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_submissions(
        self,
        org_id: int,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """List submissions with optional filters."""
        query = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.organization_id == org_id,
        )

        if supplier_id:
            query = query.filter(EsgSupplierSubmission.supplier_id == int(supplier_id))
        if status:
            query = query.filter(EsgSupplierSubmission.status == status)
        if year:
            query = query.filter(EsgSupplierSubmission.reporting_year == year)

        total = query.count()
        submissions = (
            query.order_by(EsgSupplierSubmission.created_date.desc()).all()
        )

        return {
            'submissions': [s.to_dict() for s in submissions],
            'total': total,
        }

    # ------------------------------------------------------------------
    # Review (approve / reject)
    # ------------------------------------------------------------------

    def review_submission(
        self,
        submission_id: int,
        org_id: int,
        action: str,
        notes: Optional[str] = None,
        reviewer_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Approve or reject a submission."""
        submission = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.id == submission_id,
            EsgSupplierSubmission.organization_id == org_id,
        ).first()
        if not submission:
            return None

        if action == 'approve':
            submission.status = 'approved'
        elif action == 'reject':
            submission.status = 'rejected'
        else:
            submission.status = action

        submission.verified_by = reviewer_id
        submission.verified_at = datetime.now(timezone.utc)
        submission.review_notes = notes
        self.session.flush()

        return submission.to_dict()

    # ------------------------------------------------------------------
    # tCO2e calculation
    # ------------------------------------------------------------------

    def calculate_tco2e(self, submission) -> float:
        """Calculate tCO2e from raw_data using basic emission factors."""
        raw = submission.raw_data or {}
        total = 0.0

        # Electricity
        kwh = _to_float(raw.get('electricity_kwh'))
        if kwh:
            total += kwh * EMISSION_FACTORS['electricity_kwh']

        # Fuel
        fuel_liters = _to_float(raw.get('fuel_liters'))
        fuel_type = raw.get('fuel_type', 'diesel')
        fuel_key = f'fuel_liters_{fuel_type}'
        if fuel_liters and fuel_key in EMISSION_FACTORS:
            total += fuel_liters * EMISSION_FACTORS[fuel_key]

        # Water
        water = _to_float(raw.get('water_m3'))
        if water:
            total += water * EMISSION_FACTORS['water_m3']

        # Waste
        waste = _to_float(raw.get('waste_kg'))
        if waste:
            total += waste * EMISSION_FACTORS['waste_kg']

        # Transport
        transport_km = _to_float(raw.get('transport_km'))
        transport_mode = raw.get('transport_mode', 'road')
        transport_key = f'transport_km_{transport_mode}'
        if transport_km and transport_key in EMISSION_FACTORS:
            total += transport_km * EMISSION_FACTORS[transport_key]

        return round(total, 6)

    # ------------------------------------------------------------------
    # Bulk approve
    # ------------------------------------------------------------------

    def bulk_approve(
        self, org_id: int, submission_ids: List[int]
    ) -> Dict[str, Any]:
        """Approve multiple submissions at once."""
        approved = 0
        skipped = 0

        for sid in submission_ids:
            sub = self.session.query(EsgSupplierSubmission).filter(
                EsgSupplierSubmission.id == sid,
                EsgSupplierSubmission.organization_id == org_id,
            ).first()
            if not sub:
                skipped += 1
                continue
            if sub.status == 'approved':
                skipped += 1
                continue
            sub.status = 'approved'
            sub.verified_at = datetime.now(timezone.utc)
            approved += 1

        self.session.flush()
        return {
            'approved': approved,
            'skipped': skipped,
            'total': len(submission_ids),
        }


def _to_float(val) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
