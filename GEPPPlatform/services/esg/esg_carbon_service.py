"""
ESG Carbon Service — tCO2e calculation using emission factors
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from ...models.esg.emission_factors import EmissionFactor


class EsgCarbonService:

    def __init__(self, db: Session):
        self.db = db

    def calculate_tco2e(self, category: str, amount: float, unit: str,
                        subcategory: str = None, fuel_type: str = None) -> Optional[float]:
        """
        Look up emission factor and calculate tCO2e.
        Returns None if no matching factor found.
        """
        factor = self._find_factor(category, unit, subcategory, fuel_type)
        if not factor:
            return None

        tco2e = Decimal(str(amount)) * factor.factor_value
        return float(tco2e)

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

    def _find_factor(self, category: str, unit: str,
                     subcategory: str = None, fuel_type: str = None) -> Optional[EmissionFactor]:
        """Find the best matching emission factor."""
        query = self.db.query(EmissionFactor).filter(
            EmissionFactor.is_active == True,
        )

        # Normalize for matching
        cat_lower = category.lower().strip()

        # Try exact match first
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

        # Fallback: match category + unit only
        fallback = query.filter(
            EmissionFactor.category.ilike(f'%{cat_lower}%'),
            EmissionFactor.unit.ilike(unit.strip()),
        ).first()

        return fallback
