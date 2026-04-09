"""
MACC (Marginal Abatement Cost Curve) Service
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging

from GEPPPlatform.models.esg.macc import EsgMaccInitiative

logger = logging.getLogger(__name__)

# Global template library of abatement initiatives
TEMPLATE_LIBRARY = [
    {
        'name': 'LED Lighting Upgrade',
        'category': 'energy_efficiency',
        'scope': 'scope2',
        'difficulty': 'easy',
        'potential_tco2e': 50,
        'cost_per_tco2e': -20,
        'payback_years': 2,
        'description': 'Replace all lighting with LED fixtures.',
    },
    {
        'name': 'Solar PV Installation (Rooftop)',
        'category': 'renewable_energy',
        'scope': 'scope2',
        'difficulty': 'medium',
        'potential_tco2e': 200,
        'cost_per_tco2e': -10,
        'payback_years': 5,
        'description': 'Install rooftop solar panels to offset grid electricity.',
    },
    {
        'name': 'EV Fleet Transition',
        'category': 'transport',
        'scope': 'scope1',
        'difficulty': 'hard',
        'potential_tco2e': 150,
        'cost_per_tco2e': 30,
        'payback_years': 7,
        'description': 'Transition company fleet vehicles to electric.',
    },
    {
        'name': 'HVAC Optimization',
        'category': 'energy_efficiency',
        'scope': 'scope2',
        'difficulty': 'medium',
        'potential_tco2e': 80,
        'cost_per_tco2e': -5,
        'payback_years': 3,
        'description': 'Optimize HVAC systems with smart controls and efficient equipment.',
    },
    {
        'name': 'Waste Heat Recovery',
        'category': 'process',
        'scope': 'scope1',
        'difficulty': 'hard',
        'potential_tco2e': 120,
        'cost_per_tco2e': 15,
        'payback_years': 6,
        'description': 'Capture and reuse waste heat from industrial processes.',
    },
    {
        'name': 'Green Procurement Policy',
        'category': 'supply_chain',
        'scope': 'scope3',
        'difficulty': 'medium',
        'potential_tco2e': 300,
        'cost_per_tco2e': 5,
        'payback_years': 3,
        'description': 'Require suppliers to meet minimum emissions standards.',
    },
    {
        'name': 'Telecommuting Program',
        'category': 'transport',
        'scope': 'scope3',
        'difficulty': 'easy',
        'potential_tco2e': 40,
        'cost_per_tco2e': -30,
        'payback_years': 0,
        'description': 'Implement hybrid/remote work to reduce employee commuting.',
    },
    {
        'name': 'Carbon Offsets (Verified)',
        'category': 'offsets',
        'scope': 'scope1',
        'difficulty': 'easy',
        'potential_tco2e': 500,
        'cost_per_tco2e': 50,
        'payback_years': None,
        'description': 'Purchase verified carbon credits for residual emissions.',
    },
    {
        'name': 'Biogas from Wastewater',
        'category': 'renewable_energy',
        'scope': 'scope1',
        'difficulty': 'hard',
        'potential_tco2e': 180,
        'cost_per_tco2e': 10,
        'payback_years': 8,
        'description': 'Generate biogas from wastewater treatment for energy recovery.',
    },
    {
        'name': 'Supplier Engagement Program',
        'category': 'supply_chain',
        'scope': 'scope3',
        'difficulty': 'medium',
        'potential_tco2e': 250,
        'cost_per_tco2e': 8,
        'payback_years': 4,
        'description': 'Engage top suppliers on emission reduction targets.',
    },
]


class MaccService:
    """MACC (Marginal Abatement Cost Curve) initiatives and curve generation."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Template library
    # ------------------------------------------------------------------

    def get_library(
        self,
        category: Optional[str] = None,
        scope: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return global template initiatives with optional filters."""
        templates = TEMPLATE_LIBRARY

        if category:
            templates = [t for t in templates if t['category'] == category]
        if scope:
            templates = [t for t in templates if t['scope'] == scope]
        if difficulty:
            templates = [t for t in templates if t['difficulty'] == difficulty]

        return templates

    # ------------------------------------------------------------------
    # Org-specific initiatives
    # ------------------------------------------------------------------

    def list_initiatives(
        self, org_id: int, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return organization's MACC initiatives."""
        query = self.session.query(EsgMaccInitiative).filter(
            EsgMaccInitiative.organization_id == org_id,
            EsgMaccInitiative.is_active == True,
        )
        if status:
            query = query.filter(EsgMaccInitiative.status == status)

        initiatives = query.order_by(EsgMaccInitiative.cost_per_tco2e.asc()).all()
        return [i.to_dict() for i in initiatives]

    # ------------------------------------------------------------------
    # Create initiative
    # ------------------------------------------------------------------

    def create_initiative(
        self, org_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create an initiative from scratch or copy from a template."""
        # If template_index is provided, pre-fill from library
        template_idx = data.get('template_index')
        if template_idx is not None and 0 <= template_idx < len(TEMPLATE_LIBRARY):
            template = TEMPLATE_LIBRARY[template_idx]
            # Template values as defaults, data overrides
            merged = {**template, **{k: v for k, v in data.items() if v is not None}}
            data = merged

        initiative = EsgMaccInitiative(
            organization_id=org_id,
            name=data['name'],
            category=data.get('category'),
            scope=data.get('scope'),
            difficulty=data.get('difficulty'),
            description=data.get('description'),
            potential_tco2e=data.get('potential_tco2e', 0),
            cost_per_tco2e=data.get('cost_per_tco2e', 0),
            total_cost=data.get('total_cost'),
            payback_years=data.get('payback_years'),
            status=data.get('status', 'planned'),
            start_date=data.get('start_date'),
            target_date=data.get('target_date'),
        )

        # Calculate total_cost if not provided
        if not initiative.total_cost and initiative.potential_tco2e and initiative.cost_per_tco2e:
            initiative.total_cost = round(
                float(initiative.potential_tco2e) * float(initiative.cost_per_tco2e), 2
            )

        self.session.add(initiative)
        self.session.flush()
        return initiative.to_dict()

    # ------------------------------------------------------------------
    # Update initiative
    # ------------------------------------------------------------------

    def update_initiative(
        self, initiative_id: int, org_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing initiative."""
        initiative = self.session.query(EsgMaccInitiative).filter(
            EsgMaccInitiative.id == initiative_id,
            EsgMaccInitiative.organization_id == org_id,
            EsgMaccInitiative.is_active == True,
        ).first()
        if not initiative:
            return None

        updatable = [
            'name', 'category', 'scope', 'difficulty', 'description',
            'potential_tco2e', 'cost_per_tco2e', 'total_cost',
            'payback_years', 'status', 'start_date', 'target_date',
        ]
        for field in updatable:
            if field in data:
                setattr(initiative, field, data[field])

        # Recalculate total_cost if relevant inputs changed
        if initiative.potential_tco2e and initiative.cost_per_tco2e and 'total_cost' not in data:
            initiative.total_cost = round(
                float(initiative.potential_tco2e) * float(initiative.cost_per_tco2e), 2
            )

        initiative.updated_date = datetime.now(timezone.utc)
        self.session.flush()
        return initiative.to_dict()

    # ------------------------------------------------------------------
    # MACC curve generation
    # ------------------------------------------------------------------

    def generate_curve(self, org_id: int) -> Dict[str, Any]:
        """
        Generate MACC curve data sorted by cost_per_tco2e ascending.
        Returns the data needed by the frontend MACC chart.
        """
        initiatives = (
            self.session.query(EsgMaccInitiative)
            .filter(
                EsgMaccInitiative.organization_id == org_id,
                EsgMaccInitiative.is_active == True,
            )
            .order_by(EsgMaccInitiative.cost_per_tco2e.asc())
            .all()
        )

        curve_data: List[Dict[str, Any]] = []
        cumulative_tco2e = 0.0
        cumulative_cost = 0.0

        for init in initiatives:
            potential = float(init.potential_tco2e or 0)
            cost_per = float(init.cost_per_tco2e or 0)
            total = potential * cost_per

            cumulative_tco2e += potential
            cumulative_cost += total

            curve_data.append({
                'id': init.id,
                'name': init.name,
                'category': init.category,
                'scope': init.scope,
                'difficulty': init.difficulty,
                'status': init.status,
                'potential_tco2e': round(potential, 2),
                'cost_per_tco2e': round(cost_per, 2),
                'total_cost': round(total, 2),
                'cumulative_tco2e': round(cumulative_tco2e, 2),
                'cumulative_cost': round(cumulative_cost, 2),
            })

        # Summary statistics
        negative_cost = [d for d in curve_data if d['cost_per_tco2e'] < 0]
        positive_cost = [d for d in curve_data if d['cost_per_tco2e'] >= 0]

        return {
            'curve': curve_data,
            'total_potential_tco2e': round(cumulative_tco2e, 2),
            'total_cost': round(cumulative_cost, 2),
            'initiative_count': len(curve_data),
            'net_savings_initiatives': len(negative_cost),
            'net_cost_initiatives': len(positive_cost),
            'total_savings': round(
                sum(d['total_cost'] for d in negative_cost), 2
            ),
        }
