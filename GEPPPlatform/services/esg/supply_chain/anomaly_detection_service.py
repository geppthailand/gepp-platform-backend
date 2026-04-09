"""
Anomaly Detection Service — Statistical + AI Validation
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

from GEPPPlatform.models.esg.supplier_submissions import EsgSupplierSubmission

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # Graceful fallback if numpy not available in Lambda layer


class AnomalyDetectionService:
    """Detect anomalies in supplier submissions using statistical methods."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Scan a single submission
    # ------------------------------------------------------------------

    def scan_submission(self, submission) -> List[Dict[str, Any]]:
        """Run statistical checks on a single submission. Returns list of anomaly flags."""
        flags: List[Dict[str, Any]] = []
        raw = submission.raw_data or {}

        # Z-score check against historical data for this supplier
        historical = self._get_historical_values(
            submission.supplier_id,
            getattr(submission, 'scope3_category', None),
        )

        for key, value in raw.items():
            if not isinstance(value, (int, float)) or value <= 0:
                continue

            z = self._z_score(value, historical.get(key, []))
            if abs(z) > 3:
                flags.append({
                    'type': 'statistical',
                    'method': 'z_score',
                    'field': key,
                    'z_score': round(z, 2),
                    'expected_range': f'{z:.1f} sigma',
                    'actual_value': value,
                    'severity': 'high' if abs(z) > 5 else 'medium',
                    'resolved': False,
                })

        # Year-over-year deviation check
        yoy_flags = self._check_yoy_deviation(submission)
        flags.extend(yoy_flags)

        return flags

    # ------------------------------------------------------------------
    # Z-score calculation
    # ------------------------------------------------------------------

    def _z_score(self, value: float, historical_values: List[float]) -> float:
        """Calculate z-score of value relative to historical values."""
        if len(historical_values) < 3:
            return 0.0

        if np is not None:
            mean = float(np.mean(historical_values))
            std = float(np.std(historical_values))
        else:
            mean = sum(historical_values) / len(historical_values)
            variance = sum((x - mean) ** 2 for x in historical_values) / len(historical_values)
            std = variance ** 0.5

        if std == 0:
            return 0.0
        return (value - mean) / std

    # ------------------------------------------------------------------
    # Historical data retrieval
    # ------------------------------------------------------------------

    def _get_historical_values(
        self, supplier_id: int, category: Optional[str] = None
    ) -> Dict[str, List[float]]:
        """Query past submissions for this supplier and extract numeric values by field."""
        query = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.supplier_id == supplier_id,
            EsgSupplierSubmission.status.in_(['approved', 'submitted']),
        )
        if category:
            query = query.filter(EsgSupplierSubmission.scope3_category == category)

        past = query.order_by(EsgSupplierSubmission.reporting_year.desc()).limit(10).all()

        result: Dict[str, List[float]] = {}
        for sub in past:
            raw = sub.raw_data or {}
            for key, val in raw.items():
                if isinstance(val, (int, float)) and val > 0:
                    result.setdefault(key, []).append(float(val))

        return result

    # ------------------------------------------------------------------
    # Year-over-year deviation
    # ------------------------------------------------------------------

    def _check_yoy_deviation(self, submission) -> List[Dict[str, Any]]:
        """Check if values deviate >300% from same period last year."""
        flags: List[Dict[str, Any]] = []
        raw = submission.raw_data or {}
        reporting_year = getattr(submission, 'reporting_year', None)
        if not reporting_year:
            return flags

        prev_year = reporting_year - 1
        prev_sub = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.supplier_id == submission.supplier_id,
            EsgSupplierSubmission.reporting_year == prev_year,
            EsgSupplierSubmission.status.in_(['approved', 'submitted']),
        ).order_by(EsgSupplierSubmission.created_date.desc()).first()

        if not prev_sub or not prev_sub.raw_data:
            return flags

        prev_raw = prev_sub.raw_data
        for key, value in raw.items():
            if not isinstance(value, (int, float)) or value <= 0:
                continue
            prev_value = prev_raw.get(key)
            if not isinstance(prev_value, (int, float)) or prev_value <= 0:
                continue

            ratio = value / prev_value
            if ratio > 3.0 or ratio < (1 / 3.0):
                flags.append({
                    'type': 'yoy_deviation',
                    'method': 'year_over_year',
                    'field': key,
                    'current_value': value,
                    'previous_value': prev_value,
                    'ratio': round(ratio, 2),
                    'severity': 'high' if ratio > 5.0 or ratio < 0.2 else 'medium',
                    'resolved': False,
                })

        return flags

    # ------------------------------------------------------------------
    # Bulk scan
    # ------------------------------------------------------------------

    def bulk_scan(
        self,
        org_id: int,
        submission_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Scan multiple submissions and return summary."""
        query = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.organization_id == org_id,
        )
        if submission_ids:
            query = query.filter(EsgSupplierSubmission.id.in_(submission_ids))
        else:
            query = query.filter(EsgSupplierSubmission.status == 'submitted')

        submissions = query.all()
        scanned = 0
        flagged = 0
        all_flags: List[Dict[str, Any]] = []
        severity_counts = {'high': 0, 'medium': 0, 'low': 0}

        for sub in submissions:
            flags = self.scan_submission(sub)
            scanned += 1
            if flags:
                flagged += 1
                for f in flags:
                    severity_counts[f.get('severity', 'medium')] += 1
                all_flags.extend(
                    [{**f, 'submission_id': sub.id} for f in flags]
                )

        return {
            'scanned': scanned,
            'flagged': flagged,
            'flags_by_severity': severity_counts,
            'flags': all_flags,
        }

    # ------------------------------------------------------------------
    # Get anomalies for a specific submission
    # ------------------------------------------------------------------

    def get_anomalies(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Return anomaly flags for a specific submission."""
        sub = self.session.query(EsgSupplierSubmission).filter(
            EsgSupplierSubmission.id == submission_id,
        ).first()
        if not sub:
            return None

        flags = self.scan_submission(sub)
        return {
            'submission_id': submission_id,
            'flags': flags,
            'total': len(flags),
        }
