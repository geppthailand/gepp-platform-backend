"""
ESG Ideas Service — Mock ideas/insights for dashboard
Future: daily cron generates AI insights from collected data
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class EsgIdeasService:
    """Returns mock business ideas/insights based on ESG data"""

    def __init__(self, db: Session):
        self.db = db

    def get_ideas(self, organization_id: int) -> Dict[str, Any]:
        """Return mock ideas. Future: cron-generated from actual data."""
        ideas = [
            {
                'id': 1,
                'title': 'Scope 3 Category 5 Data Gap',
                'description': 'Your waste management data coverage is below industry average. Consider implementing digital weighbridge integration for automatic data capture.',
                'priority': 'high',
                'category': 'data_gap',
                'pillar': 'E',
                'date': '2026-03-23',
            },
            {
                'id': 2,
                'title': 'Transportation Optimization Opportunity',
                'description': 'Based on your upstream transportation data, consolidating shipments from your top 5 suppliers could reduce Scope 3 Cat 4 emissions by an estimated 15-20%.',
                'priority': 'medium',
                'category': 'strategy',
                'pillar': 'E',
                'date': '2026-03-22',
            },
            {
                'id': 3,
                'title': 'Employee Commuting Survey Needed',
                'description': 'No employee commuting data (Scope 3 Cat 7) has been collected. A simple survey could establish your baseline and identify remote work opportunities.',
                'priority': 'medium',
                'category': 'data_gap',
                'pillar': 'E',
                'date': '2026-03-21',
            },
            {
                'id': 4,
                'title': 'Recycling Rate Above Industry Average',
                'description': 'Your landfill diversion rate of 68% exceeds the industry average of 45%. This is a strong ESG story for stakeholder communications.',
                'priority': 'low',
                'category': 'highlight',
                'pillar': 'E',
                'date': '2026-03-20',
            },
            {
                'id': 5,
                'title': 'Supplier Engagement Campaign',
                'description': 'Engaging your top 20 suppliers (covering 80% of procurement spend) on emissions data sharing could significantly improve your Scope 3 Cat 1 reporting accuracy.',
                'priority': 'high',
                'category': 'strategy',
                'pillar': 'E',
                'date': '2026-03-19',
            },
            {
                'id': 6,
                'title': 'Business Travel Carbon Offset',
                'description': 'Your Q1 business travel emissions are 12.5 tCO2e. Consider implementing a carbon offset program or encouraging virtual meetings for domestic trips.',
                'priority': 'low',
                'category': 'strategy',
                'pillar': 'E',
                'date': '2026-03-18',
            },
        ]

        return {
            'success': True,
            'ideas': ideas,
            'meta': {
                'total': len(ideas),
                'last_generated': '2026-03-23T00:00:00Z',
                'is_mock': True,
            }
        }
