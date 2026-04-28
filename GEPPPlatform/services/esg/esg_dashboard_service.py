"""
ESG Dashboard Service — Summary KPIs + chart data for Executive Dashboard
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from ...models.esg.data_entries import EsgDataEntry, EntryStatus
from ...models.esg.emission_factors import EmissionFactor


class EsgDashboardService:

    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, organization_id: int) -> Dict[str, Any]:
        """
        GET /api/dashboard/summary
        Returns: total tCO2e, target %, scope breakdown, top emitters, entry counts.
        """
        base = self.db.query(EsgDataEntry).filter(
            EsgDataEntry.organization_id == organization_id,
            EsgDataEntry.is_active == True,
        )

        # Total tCO2e
        total_tco2e_row = base.with_entities(
            func.coalesce(func.sum(EsgDataEntry.calculated_tco2e), 0)
        ).scalar()
        total_tco2e = float(total_tco2e_row or 0)

        # Entry counts by status
        total_entries = base.count()
        verified_count = base.filter(EsgDataEntry.status == EntryStatus.VERIFIED).count()
        pending_count = base.filter(EsgDataEntry.status == EntryStatus.PENDING_VERIFY).count()

        # Scope breakdown
        scope_breakdown = []
        for scope_tag in ['Scope 1', 'Scope 2', 'Scope 3']:
            val = base.filter(EsgDataEntry.scope_tag == scope_tag).with_entities(
                func.coalesce(func.sum(EsgDataEntry.calculated_tco2e), 0)
            ).scalar()
            scope_breakdown.append({
                'scope': scope_tag,
                'tco2e': float(val or 0),
            })

        # Top 3 emission categories
        top_categories = (
            base
            .filter(EsgDataEntry.calculated_tco2e.isnot(None))
            .with_entities(
                EsgDataEntry.category,
                func.sum(EsgDataEntry.calculated_tco2e).label('total'),
            )
            .group_by(EsgDataEntry.category)
            .order_by(func.sum(EsgDataEntry.calculated_tco2e).desc())
            .limit(3)
            .all()
        )

        return {
            'total_tco2e': total_tco2e,
            'total_entries': total_entries,
            'verified_count': verified_count,
            'pending_count': pending_count,
            'scope_breakdown': scope_breakdown,
            'top_categories': [
                {'category': row[0] or 'Unknown', 'tco2e': float(row[1] or 0)}
                for row in top_categories
            ],
        }

    def get_charts(self, organization_id: int, year: int = None) -> Dict[str, Any]:
        """
        GET /api/dashboard/charts
        Returns: donut data (scope proportions), line chart data (monthly trends).
        """
        if not year:
            year = datetime.utcnow().year

        base = self.db.query(EsgDataEntry).filter(
            EsgDataEntry.organization_id == organization_id,
            EsgDataEntry.is_active == True,
        )

        # Donut chart: scope proportions
        donut_data = []
        for scope_tag in ['Scope 1', 'Scope 2', 'Scope 3']:
            val = base.filter(EsgDataEntry.scope_tag == scope_tag).with_entities(
                func.coalesce(func.sum(EsgDataEntry.calculated_tco2e), 0)
            ).scalar()
            donut_data.append({
                'label': scope_tag,
                'value': float(val or 0),
            })

        # Line chart: monthly tCO2e trend
        monthly_data = []
        for month in range(1, 13):
            val = (
                base
                .filter(
                    extract('year', EsgDataEntry.entry_date) == year,
                    extract('month', EsgDataEntry.entry_date) == month,
                )
                .with_entities(func.coalesce(func.sum(EsgDataEntry.calculated_tco2e), 0))
                .scalar()
            )
            monthly_data.append({
                'month': month,
                'label': datetime(year, month, 1).strftime('%b'),
                'tco2e': float(val or 0),
            })

        return {
            'year': year,
            'donut': donut_data,
            'monthly_trend': monthly_data,
        }
