"""
EU CBAM (Carbon Border Adjustment Mechanism) Compliance Service
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging

from GEPPPlatform.models.esg.cbam import EsgCbamProduct, EsgCbamReport

logger = logging.getLogger(__name__)

# EU default values by CN code prefix (tCO2e per tonne of product)
# Reference: EU CBAM Implementing Regulation default values
EU_DEFAULT_VALUES = {
    '7201': {'name': 'Pig iron', 'default_embedded': 1.60, 'unit': 'tCO2e/t'},
    '7207': {'name': 'Semi-finished iron/steel', 'default_embedded': 1.85, 'unit': 'tCO2e/t'},
    '7208': {'name': 'Flat-rolled iron/steel', 'default_embedded': 2.10, 'unit': 'tCO2e/t'},
    '7210': {'name': 'Coated flat-rolled steel', 'default_embedded': 2.30, 'unit': 'tCO2e/t'},
    '7304': {'name': 'Seamless steel tubes', 'default_embedded': 2.50, 'unit': 'tCO2e/t'},
    '7601': {'name': 'Unwrought aluminium', 'default_embedded': 6.70, 'unit': 'tCO2e/t'},
    '2523': {'name': 'Cement', 'default_embedded': 0.73, 'unit': 'tCO2e/t'},
    '3102': {'name': 'Nitrogen fertilizers', 'default_embedded': 3.00, 'unit': 'tCO2e/t'},
    '2716': {'name': 'Electrical energy', 'default_embedded': 0.45, 'unit': 'tCO2e/MWh'},
    '2804': {'name': 'Hydrogen', 'default_embedded': 9.30, 'unit': 'tCO2e/t'},
}


class CbamService:
    """EU CBAM compliance: product tracking, emission calculations, and reporting."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Products CRUD
    # ------------------------------------------------------------------

    def list_products(self, org_id: int) -> List[Dict[str, Any]]:
        """List all CBAM products for an organization."""
        products = (
            self.session.query(EsgCbamProduct)
            .filter(
                EsgCbamProduct.organization_id == org_id,
                EsgCbamProduct.is_active == True,
            )
            .order_by(EsgCbamProduct.created_date.desc())
            .all()
        )
        return [p.to_dict() for p in products]

    def get_product(self, product_id: int, org_id: int) -> Optional[Dict[str, Any]]:
        """Get a single CBAM product."""
        product = self.session.query(EsgCbamProduct).filter(
            EsgCbamProduct.id == product_id,
            EsgCbamProduct.organization_id == org_id,
            EsgCbamProduct.is_active == True,
        ).first()
        return product.to_dict() if product else None

    def create_product(self, org_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new CBAM product record."""
        product = EsgCbamProduct(
            organization_id=org_id,
            product_name=data['product_name'],
            cn_code=data.get('cn_code'),
            description=data.get('description'),
            production_volume=data.get('production_volume'),
            production_unit=data.get('production_unit', 'tonnes'),
            direct_emissions=data.get('direct_emissions'),
            indirect_emissions=data.get('indirect_emissions'),
            precursor_emissions=data.get('precursor_emissions', 0),
            country_of_origin=data.get('country_of_origin'),
            installation_name=data.get('installation_name'),
            reporting_year=data.get('reporting_year', datetime.now(timezone.utc).year),
        )
        self.session.add(product)
        self.session.flush()
        return product.to_dict()

    def update_product(
        self, product_id: int, org_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a CBAM product."""
        product = self.session.query(EsgCbamProduct).filter(
            EsgCbamProduct.id == product_id,
            EsgCbamProduct.organization_id == org_id,
            EsgCbamProduct.is_active == True,
        ).first()
        if not product:
            return None

        updatable = [
            'product_name', 'cn_code', 'description', 'production_volume',
            'production_unit', 'direct_emissions', 'indirect_emissions',
            'precursor_emissions', 'country_of_origin', 'installation_name',
            'reporting_year',
        ]
        for field in updatable:
            if field in data:
                setattr(product, field, data[field])

        product.updated_date = datetime.now(timezone.utc)
        self.session.flush()
        return product.to_dict()

    # ------------------------------------------------------------------
    # Emission calculation
    # ------------------------------------------------------------------

    def calculate_embedded_emissions(
        self, product_id: int, org_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate specific embedded emissions for a product:
        specific_embedded = (direct + indirect + precursor) / production_volume
        """
        product = self.session.query(EsgCbamProduct).filter(
            EsgCbamProduct.id == product_id,
            EsgCbamProduct.organization_id == org_id,
            EsgCbamProduct.is_active == True,
        ).first()
        if not product:
            return None

        direct = float(product.direct_emissions or 0)
        indirect = float(product.indirect_emissions or 0)
        precursor = float(product.precursor_emissions or 0)
        volume = float(product.production_volume or 1)

        total_embedded = direct + indirect + precursor
        specific_embedded = total_embedded / volume if volume > 0 else 0

        # Persist calculated value
        product.specific_embedded_emissions = round(specific_embedded, 6)
        product.total_embedded_emissions = round(total_embedded, 6)
        self.session.flush()

        return {
            'product_id': product_id,
            'product_name': product.product_name,
            'direct_emissions': direct,
            'indirect_emissions': indirect,
            'precursor_emissions': precursor,
            'total_embedded': round(total_embedded, 6),
            'production_volume': volume,
            'specific_embedded': round(specific_embedded, 6),
            'unit': f'tCO2e/{product.production_unit or "t"}',
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self, org_id: int, quarter: int, year: int
    ) -> Dict[str, Any]:
        """Generate a quarterly CBAM declaration report."""
        products = (
            self.session.query(EsgCbamProduct)
            .filter(
                EsgCbamProduct.organization_id == org_id,
                EsgCbamProduct.reporting_year == year,
                EsgCbamProduct.is_active == True,
            )
            .all()
        )

        product_entries = []
        total_embedded = 0.0

        for p in products:
            direct = float(p.direct_emissions or 0)
            indirect = float(p.indirect_emissions or 0)
            precursor = float(p.precursor_emissions or 0)
            volume = float(p.production_volume or 0)
            total = direct + indirect + precursor
            specific = total / volume if volume > 0 else 0

            total_embedded += total
            product_entries.append({
                'product_name': p.product_name,
                'cn_code': p.cn_code,
                'country_of_origin': p.country_of_origin,
                'production_volume': volume,
                'direct_emissions': direct,
                'indirect_emissions': indirect,
                'precursor_emissions': precursor,
                'total_embedded': round(total, 6),
                'specific_embedded': round(specific, 6),
            })

        # Save report record
        report = EsgCbamReport(
            organization_id=org_id,
            quarter=quarter,
            year=year,
            total_embedded_emissions=round(total_embedded, 6),
            product_count=len(products),
            report_data={'products': product_entries},
            status='draft',
        )
        self.session.add(report)
        self.session.flush()

        return {
            'report_id': report.id,
            'quarter': quarter,
            'year': year,
            'total_embedded_emissions': round(total_embedded, 6),
            'product_count': len(products),
            'products': product_entries,
            'status': 'draft',
        }

    # ------------------------------------------------------------------
    # EU default values
    # ------------------------------------------------------------------

    def get_default_values(
        self, cn_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return EU default values, optionally filtered by CN code prefix."""
        if cn_code:
            # Match by prefix (first 4 digits)
            prefix = cn_code[:4]
            match = EU_DEFAULT_VALUES.get(prefix)
            if match:
                return [{'cn_code': prefix, **match}]
            return []

        return [
            {'cn_code': code, **vals}
            for code, vals in EU_DEFAULT_VALUES.items()
        ]

    # ------------------------------------------------------------------
    # Compare with defaults
    # ------------------------------------------------------------------

    def compare_with_defaults(
        self, product_id: int, org_id: int
    ) -> Optional[Dict[str, Any]]:
        """Compare actual embedded emissions vs EU default values."""
        product = self.session.query(EsgCbamProduct).filter(
            EsgCbamProduct.id == product_id,
            EsgCbamProduct.organization_id == org_id,
            EsgCbamProduct.is_active == True,
        ).first()
        if not product:
            return None

        cn_prefix = (product.cn_code or '')[:4]
        default = EU_DEFAULT_VALUES.get(cn_prefix)

        direct = float(product.direct_emissions or 0)
        indirect = float(product.indirect_emissions or 0)
        precursor = float(product.precursor_emissions or 0)
        volume = float(product.production_volume or 1)
        specific_actual = (direct + indirect + precursor) / volume if volume > 0 else 0

        result = {
            'product_id': product_id,
            'product_name': product.product_name,
            'cn_code': product.cn_code,
            'specific_actual': round(specific_actual, 6),
            'default_available': default is not None,
        }

        if default:
            default_val = default['default_embedded']
            savings = default_val - specific_actual
            result.update({
                'default_embedded': default_val,
                'default_unit': default['unit'],
                'savings_tco2e_per_unit': round(savings, 6),
                'savings_pct': round(
                    (savings / default_val * 100) if default_val > 0 else 0, 2
                ),
                'uses_primary_data': specific_actual > 0,
                'recommendation': (
                    'Primary data shows lower emissions than EU defaults. '
                    'Continue using actual data for CBAM declarations.'
                    if savings > 0
                    else 'Actual emissions exceed EU defaults. '
                         'Consider using default values or improving processes.'
                ),
            })

        return result
