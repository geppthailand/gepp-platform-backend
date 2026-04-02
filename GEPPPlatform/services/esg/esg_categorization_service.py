"""
ESG Categorization Service - Auto-categorize data entries into ESG scope frameworks (UC 3.1)
"""

from GEPPPlatform.models.esg.data_hierarchy import EsgDataCategory as DataCategory, EsgDataSubcategory


class EsgCategorizationService:

    # Mapping of subcategory patterns to ESG scope tags
    SCOPE_MAPPINGS = {
        # Scope 1 - Direct emissions
        'direct_emissions': 'Scope 1',
        'fugitive_emissions': 'Scope 1',
        'company_vehicles': 'Scope 1',
        'stationary_combustion': 'Scope 1',
        # Scope 2 - Indirect emissions (purchased energy)
        'purchased_electricity': 'Scope 2',
        'purchased_heat': 'Scope 2',
        'purchased_steam': 'Scope 2',
        # Scope 3 - Value chain emissions
        'purchased_goods': 'Scope 3',
        'capital_goods': 'Scope 3',
        'fuel_energy_related': 'Scope 3',
        'upstream_transportation': 'Scope 3',
        'waste_in_operations': 'Scope 3',
        'business_travel': 'Scope 3',
        'employee_commuting': 'Scope 3',
        'upstream_leased_assets': 'Scope 3',
        'downstream_transportation': 'Scope 3',
        'processing_sold_products': 'Scope 3',
        'use_of_sold_products': 'Scope 3',
        'end_of_life_treatment': 'Scope 3',
        'downstream_leased_assets': 'Scope 3',
        'franchises': 'Scope 3',
        'investments': 'Scope 3',
    }

    def __init__(self, session):
        self.session = session

    def categorize(self, category_id: int = None, subcategory_id: int = None) -> str | None:
        """
        Determine the ESG scope tag for a data entry based on its category/subcategory.

        Returns a scope tag string (e.g., "Scope 1", "Scope 2", "Scope 3") or None.
        """
        if not subcategory_id:
            return None

        subcategory = (
            self.session.query(EsgDataSubcategory)
            .filter(EsgDataSubcategory.id == subcategory_id)
            .first()
        )
        if not subcategory:
            return None

        # Normalize name to match pattern
        name_key = subcategory.name.lower().replace(' ', '_').replace('-', '_').replace('&', 'and')

        # Try direct match
        for pattern, scope in self.SCOPE_MAPPINGS.items():
            if pattern in name_key:
                return scope

        # Fallback: check pillar for non-Environmental categories
        if subcategory.pillar == 'S':
            return 'Social'
        elif subcategory.pillar == 'G':
            return 'Governance'

        return None
