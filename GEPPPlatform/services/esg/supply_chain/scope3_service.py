"""
Scope 3 Category Management Service
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from GEPPPlatform.models.esg.scope3_categories import EsgScope3Category
from GEPPPlatform.models.esg.scope3_entries import EsgScope3Entry

logger = logging.getLogger(__name__)

# GHG Protocol Scope 3 categories (15 total)
SCOPE3_CATEGORIES = [
    {'number': 1, 'name': 'Purchased Goods and Services', 'direction': 'upstream'},
    {'number': 2, 'name': 'Capital Goods', 'direction': 'upstream'},
    {'number': 3, 'name': 'Fuel- and Energy-Related Activities', 'direction': 'upstream'},
    {'number': 4, 'name': 'Upstream Transportation and Distribution', 'direction': 'upstream'},
    {'number': 5, 'name': 'Waste Generated in Operations', 'direction': 'upstream'},
    {'number': 6, 'name': 'Business Travel', 'direction': 'upstream'},
    {'number': 7, 'name': 'Employee Commuting', 'direction': 'upstream'},
    {'number': 8, 'name': 'Upstream Leased Assets', 'direction': 'upstream'},
    {'number': 9, 'name': 'Downstream Transportation and Distribution', 'direction': 'downstream'},
    {'number': 10, 'name': 'Processing of Sold Products', 'direction': 'downstream'},
    {'number': 11, 'name': 'Use of Sold Products', 'direction': 'downstream'},
    {'number': 12, 'name': 'End-of-Life Treatment of Sold Products', 'direction': 'downstream'},
    {'number': 13, 'name': 'Downstream Leased Assets', 'direction': 'downstream'},
    {'number': 14, 'name': 'Franchises', 'direction': 'downstream'},
    {'number': 15, 'name': 'Investments', 'direction': 'downstream'},
]

# Placeholder spend-based emission factors (kgCO2e per THB) by category number
SPEND_BASED_FACTORS = {
    1: 0.35, 2: 0.40, 3: 0.50, 4: 0.25, 5: 0.20,
    6: 0.30, 7: 0.15, 8: 0.10, 9: 0.25, 10: 0.30,
    11: 0.35, 12: 0.15, 13: 0.10, 14: 0.20, 15: 0.10,
}


class Scope3Service:
    """Manage Scope 3 categories and emission entries."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Dict[str, Any]]:
        """Return all 15 GHG Protocol Scope 3 categories."""
        db_cats = self.session.query(EsgScope3Category).order_by(
            EsgScope3Category.category_number.asc()
        ).all()

        if db_cats:
            return [c.to_dict() for c in db_cats]

        # Fallback to built-in list if DB is empty
        return SCOPE3_CATEGORIES

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(
        self, org_id: int, year: Optional[int] = None
    ) -> Dict[str, Any]:
        """Aggregate entries by category and return summary."""
        query = self.session.query(EsgScope3Entry).filter(
            EsgScope3Entry.organization_id == org_id,
            EsgScope3Entry.is_active == True,
        )
        if year:
            query = query.filter(EsgScope3Entry.reporting_year == year)

        entries = query.all()

        # Build per-category summary
        cat_map: Dict[int, Dict[str, Any]] = {}
        grand_total = 0.0

        for entry in entries:
            cat_num = entry.category_number
            tco2e = float(entry.tco2e or 0)
            grand_total += tco2e

            if cat_num not in cat_map:
                cat_info = next(
                    (c for c in SCOPE3_CATEGORIES if c['number'] == cat_num),
                    {'name': f'Category {cat_num}', 'direction': 'unknown'},
                )
                cat_map[cat_num] = {
                    'category_number': cat_num,
                    'name': cat_info['name'],
                    'direction': cat_info['direction'],
                    'tco2e': 0.0,
                    'method': getattr(entry, 'calculation_method', None),
                    'entry_count': 0,
                    'supplier_ids': set(),
                }

            cat_map[cat_num]['tco2e'] += tco2e
            cat_map[cat_num]['entry_count'] += 1
            if entry.supplier_id:
                cat_map[cat_num]['supplier_ids'].add(entry.supplier_id)

        categories = []
        for cat_num in sorted(cat_map.keys()):
            item = cat_map[cat_num]
            item['supplier_count'] = len(item.pop('supplier_ids'))
            item['percentage'] = round(
                (item['tco2e'] / grand_total * 100) if grand_total > 0 else 0, 2
            )
            item['tco2e'] = round(item['tco2e'], 4)
            categories.append(item)

        return {
            'categories': categories,
            'total_tco2e': round(grand_total, 4),
            'year': year,
        }

    # ------------------------------------------------------------------
    # Entries CRUD
    # ------------------------------------------------------------------

    def list_entries(
        self,
        org_id: int,
        category: Optional[str] = None,
        year: Optional[int] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List Scope 3 entries with optional filters."""
        query = self.session.query(EsgScope3Entry).filter(
            EsgScope3Entry.organization_id == org_id,
            EsgScope3Entry.is_active == True,
        )

        if category:
            query = query.filter(EsgScope3Entry.category_number == int(category))
        if year:
            query = query.filter(EsgScope3Entry.reporting_year == year)
        if method:
            query = query.filter(EsgScope3Entry.calculation_method == method)

        total = query.count()
        entries = query.order_by(EsgScope3Entry.created_date.desc()).all()

        return {
            'entries': [e.to_dict() for e in entries],
            'total': total,
        }

    def create_entry(self, org_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Scope 3 entry and calculate tCO2e."""
        calc_method = data.get('calculation_method', 'spend_based')

        entry = EsgScope3Entry(
            organization_id=org_id,
            category_number=data['category_number'],
            reporting_year=data.get('reporting_year', datetime.now(timezone.utc).year),
            description=data.get('description'),
            calculation_method=calc_method,
            supplier_id=data.get('supplier_id'),
            spend_amount=data.get('spend_amount'),
            spend_currency=data.get('spend_currency', 'THB'),
            activity_data=data.get('activity_data'),
            activity_unit=data.get('activity_unit'),
            emission_factor=data.get('emission_factor'),
            emission_factor_source=data.get('emission_factor_source'),
        )

        # Calculate tCO2e
        if calc_method == 'spend_based' and entry.spend_amount:
            entry.tco2e = self._calculate_spend_based(
                float(entry.spend_amount),
                entry.spend_currency,
                entry.category_number,
            )
        elif calc_method == 'supplier_specific' and entry.supplier_id:
            entry.tco2e = self._calculate_supplier_specific(
                entry.supplier_id,
                entry.activity_data,
                entry.activity_unit,
            )
        elif entry.emission_factor and entry.activity_data:
            entry.tco2e = float(entry.activity_data) * float(entry.emission_factor) / 1000

        self.session.add(entry)
        self.session.flush()
        return entry.to_dict()

    def update_entry(
        self, entry_id: int, org_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a Scope 3 entry."""
        entry = self.session.query(EsgScope3Entry).filter(
            EsgScope3Entry.id == entry_id,
            EsgScope3Entry.organization_id == org_id,
            EsgScope3Entry.is_active == True,
        ).first()
        if not entry:
            return None

        updatable = [
            'category_number', 'description', 'calculation_method',
            'supplier_id', 'spend_amount', 'spend_currency',
            'activity_data', 'activity_unit', 'emission_factor',
            'emission_factor_source', 'tco2e', 'reporting_year',
        ]
        for field in updatable:
            if field in data:
                setattr(entry, field, data[field])

        # Recalculate if key inputs changed
        calc_method = entry.calculation_method or 'spend_based'
        if calc_method == 'spend_based' and entry.spend_amount:
            entry.tco2e = self._calculate_spend_based(
                float(entry.spend_amount),
                entry.spend_currency,
                entry.category_number,
            )

        entry.updated_date = datetime.now(timezone.utc)
        self.session.flush()
        return entry.to_dict()

    # ------------------------------------------------------------------
    # Category recalculation
    # ------------------------------------------------------------------

    def calculate_category(
        self, org_id: int, category_number: int, method: str = 'spend_based'
    ) -> Dict[str, Any]:
        """Recalculate all entries for a category using the specified method."""
        entries = (
            self.session.query(EsgScope3Entry)
            .filter(
                EsgScope3Entry.organization_id == org_id,
                EsgScope3Entry.category_number == category_number,
                EsgScope3Entry.is_active == True,
            )
            .all()
        )

        updated = 0
        total_tco2e = 0.0

        for entry in entries:
            if method == 'spend_based' and entry.spend_amount:
                entry.tco2e = self._calculate_spend_based(
                    float(entry.spend_amount),
                    entry.spend_currency,
                    category_number,
                )
                entry.calculation_method = 'spend_based'
                updated += 1
            elif method == 'supplier_specific' and entry.supplier_id:
                entry.tco2e = self._calculate_supplier_specific(
                    entry.supplier_id,
                    entry.activity_data,
                    entry.activity_unit,
                )
                entry.calculation_method = 'supplier_specific'
                updated += 1

            total_tco2e += float(entry.tco2e or 0)

        self.session.flush()
        return {
            'category_number': category_number,
            'method': method,
            'entries_updated': updated,
            'total_tco2e': round(total_tco2e, 4),
        }

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    def _calculate_spend_based(
        self, spend_amount: float, currency: str, category_number: int
    ) -> float:
        """Use spend-based emission factor. Returns tCO2e."""
        factor = SPEND_BASED_FACTORS.get(category_number, 0.25)
        # Factor is kgCO2e per THB; divide by 1000 to get tCO2e
        return round(spend_amount * factor / 1000, 6)

    def _calculate_supplier_specific(
        self,
        supplier_id: int,
        activity_data: Optional[float],
        activity_unit: Optional[str],
    ) -> float:
        """Use supplier-provided primary data to calculate tCO2e."""
        if not activity_data:
            return 0.0

        # In a full implementation, this would look up supplier-specific
        # emission factors from the supplier's verified submissions.
        # For now, use a generic factor.
        generic_factor = 0.5  # kgCO2e per unit (placeholder)
        return round(float(activity_data) * generic_factor / 1000, 6)
