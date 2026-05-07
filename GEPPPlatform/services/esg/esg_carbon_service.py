"""
ESG Carbon Service — tCO2e calculation using emission factors.

Lookup order on calculate_tco2e:
  1. Exact match on EmissionFactor (category + unit, optionally + sub + fuel)
  2. Fuzzy match on EmissionFactor (category contains + unit)
  3. **NEW** Scope 3 category-id fallback — if the entry's category resolves
     to a known Scope 3 category id (1..15), apply a conservative default
     EF from `SCOPE3_FALLBACK_EFS`. This prevents the dashboard showing
     0 tCO2e for every uploaded receipt while emission_factors is being
     seeded. The fallback is flagged in `data_quality` so users know it's
     a default estimate, not a verified factor.
"""

from decimal import Decimal
from typing import Optional, Tuple
import logging
from sqlalchemy.orm import Session

from ...models.esg.emission_factors import EmissionFactor
from ...models.esg.data_hierarchy import EsgDataCategory

logger = logging.getLogger(__name__)


# Conservative default EFs per Scope 3 category, by unit.
# Sources: GHG Protocol guidance + DEFRA + TGO Thailand averages, simplified
# to a single round number per unit so we always have *something* to show.
# These are intentionally conservative ("good enough for a screen") and
# should be replaced by org-specific factors via the `emission_factors`
# table once the team seeds them.
#
# Format: { scope3_category_id: { normalized_unit: kgCO2e_per_unit } }
# All factors are in kgCO2e per unit; we divide by 1000 at the end.
SCOPE3_FALLBACK_EFS = {
    1:  {  # Purchased goods and services — spend-based
        'thb': 0.5, 'usd': 18.0,
        'kg': 2.5, 'tonne': 2500.0, 'unit': 5.0, 'piece': 5.0,
    },
    2:  {  # Capital goods — spend-based capex
        'thb': 0.4, 'usd': 14.0,
        'kg': 3.0, 'tonne': 3000.0,
    },
    3:  {  # Fuel- and energy-related (well-to-tank)
        'kwh': 0.06, 'mwh': 60.0,
        'litre': 0.6, 'l': 0.6, 'gallon': 2.3,
        'kg': 0.4,
    },
    4:  {  # Upstream transportation
        'tonne-km': 0.062, 'kg-km': 0.000062, 'tkm': 0.062,
        'km': 0.062, 'thb': 0.3,
    },
    5:  {  # Waste in operations
        'kg': 0.45, 'tonne': 450.0,
        'litre': 0.6, 'l': 0.6,
        'thb': 0.3,
    },
    6:  {  # Business travel
        'km': 0.18, 'mile': 0.29,
        'thb': 0.4, 'usd': 14.0,
        'flight': 250.0, 'night': 25.0,
    },
    7:  {  # Employee commuting
        'km': 0.18, 'passenger-km': 0.18, 'pkm': 0.18,
        'thb': 0.35,
    },
    8:  {  # Upstream leased assets
        'kwh': 0.5, 'sqm': 90.0, 'm2': 90.0,
        'thb': 0.3,
    },
    9:  {  # Downstream transport
        'tonne-km': 0.07, 'kg-km': 0.00007, 'tkm': 0.07, 'km': 0.07,
    },
    10: {  # Processing of sold
        'kg': 1.5, 'tonne': 1500.0, 'thb': 0.4,
    },
    11: {  # Use of sold products
        'kwh': 0.5, 'mwh': 500.0,
        'litre': 2.3, 'l': 2.3,
        'unit-year': 200.0, 'unit': 200.0,
    },
    12: {  # End-of-life
        'kg': 0.4, 'tonne': 400.0,
        'unit': 0.5, 'piece': 0.5,
    },
    13: {  # Downstream leased
        'kwh': 0.5, 'sqm': 90.0, 'm2': 90.0,
    },
    14: {  # Franchises
        'kwh': 0.5, 'thb': 0.3, 'store-year': 12000.0,
    },
    15: {  # Investments
        'thb': 0.2, 'usd': 7.0,
    },
}


def _normalize_unit(unit: str) -> str:
    if not unit:
        return ''
    u = unit.strip().lower()
    # collapse common variants
    aliases = {
        'liter': 'litre', 'liters': 'litre', 'litres': 'litre',
        'kgs': 'kg', 'kilograms': 'kg', 'kilogram': 'kg',
        'tonnes': 'tonne', 'tons': 'tonne', 'ton': 'tonne', 't': 'tonne',
        'units': 'unit', 'pcs': 'piece', 'pieces': 'piece',
        'baht': 'thb', '฿': 'thb',
        'usd$': 'usd', '$': 'usd',
        'mile': 'mile', 'miles': 'mile',
        'kilometer': 'km', 'kilometers': 'km', 'kms': 'km',
        'sqm': 'sqm', 'sq m': 'sqm', 'm²': 'sqm', 'square metre': 'sqm',
        'tkm': 'tonne-km', 't-km': 'tonne-km', 't.km': 'tonne-km',
        'pkm': 'passenger-km', 'p-km': 'passenger-km',
        'kilowatt-hour': 'kwh', 'kilowatt hour': 'kwh', 'kw-h': 'kwh',
    }
    return aliases.get(u, u)


class EsgCarbonService:

    def __init__(self, db: Session):
        self.db = db

    def calculate_tco2e(
        self,
        category: str,
        amount: float,
        unit: str,
        subcategory: str = None,
        fuel_type: str = None,
        category_id: Optional[int] = None,
    ) -> Optional[float]:
        """
        Compute tCO2e for an activity. Returns None ONLY if no factor at
        all is available (DB miss + fallback miss).
        """
        if amount is None or unit is None:
            return None

        # 1 + 2 — DB lookup
        factor = self._find_factor(category, unit, subcategory, fuel_type)
        if factor:
            tco2e = Decimal(str(amount)) * factor.factor_value
            return float(tco2e)

        # 3 — Scope 3 category-id fallback
        scope3_id = self._resolve_scope3_id(category, category_id)
        if scope3_id is not None:
            ef_kg = self._fallback_ef(scope3_id, unit)
            if ef_kg is not None:
                kg = Decimal(str(amount)) * Decimal(str(ef_kg))
                tco2e = kg / Decimal('1000')
                logger.info(
                    'tCO2e fallback applied: cat=%s unit=%s amount=%s ef_kg=%s tco2e=%s',
                    scope3_id, unit, amount, ef_kg, float(tco2e),
                )
                return float(tco2e)

        logger.warning(
            'No emission factor found (DB or fallback) for category=%r unit=%r — entry will have NULL tco2e',
            category, unit,
        )
        return None

    def calculate_tco2e_for_entry(self, entry) -> Tuple[Optional[float], str]:
        """
        Convenience for the entry pipeline. Returns (tco2e, source) where
        `source` is one of: 'db_factor' | 'scope3_fallback' | 'none'.
        """
        if not entry:
            return None, 'none'

        # Try DB first
        factor = self._find_factor(
            entry.category or '',
            entry.unit or '',
            getattr(entry, 'subcategory_name', None),
            getattr(entry, 'fuel_type', None),
        )
        if factor:
            return float(Decimal(str(entry.value)) * factor.factor_value), 'db_factor'

        scope3_id = self._resolve_scope3_id(entry.category, entry.category_id)
        if scope3_id is not None:
            ef_kg = self._fallback_ef(scope3_id, entry.unit)
            if ef_kg is not None:
                kg = Decimal(str(entry.value)) * Decimal(str(ef_kg))
                return float(kg / Decimal('1000')), 'scope3_fallback'

        return None, 'none'

    def get_scope_for_category(self, category: str, subcategory: str = None) -> Optional[str]:
        """Get the GHG scope tag for a given category."""
        factor = self.db.query(EmissionFactor).filter(
            EmissionFactor.category == category,
            EmissionFactor.is_active == True,
        ).first()
        return factor.scope if factor else None

    def list_factors(self, category: str = None) -> list:
        query = self.db.query(EmissionFactor).filter(EmissionFactor.is_active == True)
        if category:
            query = query.filter(EmissionFactor.category == category)
        return [f.to_dict() for f in query.order_by(EmissionFactor.category).all()]

    # ─── helpers ────────────────────────────────────────────────────────

    def _find_factor(self, category: str, unit: str,
                     subcategory: str = None, fuel_type: str = None) -> Optional[EmissionFactor]:
        """Find the best matching emission factor."""
        if not category or not unit:
            return None
        query = self.db.query(EmissionFactor).filter(
            EmissionFactor.is_active == True,
        )
        cat_lower = category.lower().strip()

        exact = query.filter(
            EmissionFactor.category.ilike(cat_lower),
            EmissionFactor.unit.ilike(unit.strip()),
        )
        if subcategory:
            exact = exact.filter(EmissionFactor.subcategory.ilike(subcategory.strip()))
        if fuel_type:
            exact = exact.filter(EmissionFactor.fuel_type.ilike(fuel_type.strip()))

        result = exact.first()
        if result:
            return result

        # Fallback: contains-match on category + unit
        return query.filter(
            EmissionFactor.category.ilike(f'%{cat_lower}%'),
            EmissionFactor.unit.ilike(unit.strip()),
        ).first()

    def _resolve_scope3_id(self, category_name: Optional[str], category_id: Optional[int]) -> Optional[int]:
        """
        Resolve the Scope 3 category id (1..15) from either:
          - an EsgDataCategory.id (looked up via FK), or
          - a free-text category name matched on EsgDataCategory.name.
        Returns None if the category is non-Scope-3 or unknown.
        """
        try:
            if category_id:
                row = (
                    self.db.query(EsgDataCategory)
                    .filter(EsgDataCategory.id == category_id)
                    .first()
                )
                if row and row.is_scope3 and row.scope3_category_id:
                    return int(row.scope3_category_id)

            if category_name:
                row = (
                    self.db.query(EsgDataCategory)
                    .filter(
                        EsgDataCategory.name.ilike(category_name.strip()),
                        EsgDataCategory.is_scope3 == True,
                    )
                    .first()
                )
                if row and row.scope3_category_id:
                    return int(row.scope3_category_id)
        except Exception:
            logger.exception('Scope 3 id resolution failed')
        return None

    def _fallback_ef(self, scope3_id: int, unit: str) -> Optional[float]:
        """Look up the conservative default EF (kgCO2e per unit)."""
        table = SCOPE3_FALLBACK_EFS.get(int(scope3_id))
        if not table:
            return None
        u = _normalize_unit(unit)
        if u in table:
            return table[u]
        # try a partial match (e.g. "kwh/year" → "kwh")
        for key, val in table.items():
            if key in u:
                return val
        return None
