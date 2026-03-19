"""
ESG Calculation Service — GHG calculations and summary aggregation
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from datetime import datetime
from decimal import Decimal
import logging

from ...models.esg.waste_records import EsgWasteRecord
from ...models.esg.summaries import EsgScope3Summary

logger = logging.getLogger(__name__)


class EsgCalculationService:
    """Handles GHG calculations and summary generation"""

    def __init__(self, db: Session):
        self.db = db

    def recalculate_summary(self, organization_id: int, year: int, month: int = None) -> Dict[str, Any]:
        """
        Recalculate and upsert a summary for the given period.
        If month is None, calculates yearly summary.
        """
        period_type = 'monthly' if month else 'yearly'

        # Base query for the period
        query = self.db.query(EsgWasteRecord).filter(
            EsgWasteRecord.organization_id == organization_id,
            EsgWasteRecord.is_active == True,
            EsgWasteRecord.deleted_date.is_(None),
            extract('year', EsgWasteRecord.record_date) == year
        )
        if month:
            query = query.filter(extract('month', EsgWasteRecord.record_date) == month)

        records = query.all()

        # Aggregations
        total_waste_kg = sum(float(r.weight_kg or 0) for r in records)
        total_co2e_kg = sum(float(r.co2e_kg or 0) for r in records)
        total_records = len(records)

        # Breakdown by waste type
        by_waste_type = {}
        for r in records:
            wt = r.waste_type or 'unknown'
            if wt not in by_waste_type:
                by_waste_type[wt] = {'kg': 0, 'co2e': 0, 'count': 0}
            by_waste_type[wt]['kg'] += float(r.weight_kg or 0)
            by_waste_type[wt]['co2e'] += float(r.co2e_kg or 0)
            by_waste_type[wt]['count'] += 1

        # Breakdown by treatment
        by_treatment = {}
        for r in records:
            tm = r.treatment_method or 'unknown'
            if tm not in by_treatment:
                by_treatment[tm] = {'kg': 0, 'co2e': 0, 'count': 0}
            by_treatment[tm]['kg'] += float(r.weight_kg or 0)
            by_treatment[tm]['co2e'] += float(r.co2e_kg or 0)
            by_treatment[tm]['count'] += 1

        # Breakdown by location
        by_location = {}
        for r in records:
            loc = str(r.origin_location_id) if r.origin_location_id else 'unknown'
            if loc not in by_location:
                by_location[loc] = {'kg': 0, 'co2e': 0, 'count': 0}
            by_location[loc]['kg'] += float(r.weight_kg or 0)
            by_location[loc]['co2e'] += float(r.co2e_kg or 0)
            by_location[loc]['count'] += 1

        # Quality metrics
        verified_count = sum(1 for r in records if r.verification_status == 'verified')
        measured_count = sum(1 for r in records if r.data_quality == 'measured')
        verified_pct = (verified_count / total_records * 100) if total_records > 0 else 0
        measured_pct = (measured_count / total_records * 100) if total_records > 0 else 0

        # Upsert summary
        summary = self.db.query(EsgScope3Summary).filter(
            EsgScope3Summary.organization_id == organization_id,
            EsgScope3Summary.period_type == period_type,
            EsgScope3Summary.period_year == year,
            EsgScope3Summary.period_month == month
        ).first()

        if not summary:
            summary = EsgScope3Summary(
                organization_id=organization_id,
                period_type=period_type,
                period_year=year,
                period_month=month,
            )
            self.db.add(summary)

        summary.total_waste_kg = total_waste_kg
        summary.total_co2e_kg = total_co2e_kg
        summary.total_records = total_records
        summary.by_waste_type = by_waste_type
        summary.by_treatment = by_treatment
        summary.by_location = by_location
        summary.verified_percent = verified_pct
        summary.measured_percent = measured_pct
        summary.calculated_at = datetime.utcnow()

        self.db.flush()

        return {
            'success': True,
            'message': f'Summary recalculated for {year}' + (f'-{month:02d}' if month else ''),
            'summary': summary.to_dict()
        }

    def recalculate_all_summaries(self, organization_id: int, year: int) -> Dict[str, Any]:
        """Recalculate all monthly + yearly summaries for a year"""
        results = []
        for month in range(1, 13):
            result = self.recalculate_summary(organization_id, year, month)
            results.append(result)

        yearly = self.recalculate_summary(organization_id, year)
        results.append(yearly)

        return {
            'success': True,
            'message': f'All summaries recalculated for {year}',
            'summaries_count': len(results)
        }
