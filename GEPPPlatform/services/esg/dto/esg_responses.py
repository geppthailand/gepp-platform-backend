"""
ESG Response DTOs
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class DashboardKPIsResponse:
    """Dashboard KPI response"""
    total_co2e_tons: float = 0
    total_waste_kg: float = 0
    landfill_diversion_rate: float = 0
    data_coverage_percent: float = 0
    total_records: int = 0
    verified_percent: float = 0
    total_documents: int = 0
    documents_by_category: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_co2e_tons': round(self.total_co2e_tons, 4),
            'total_waste_kg': round(self.total_waste_kg, 2),
            'landfill_diversion_rate': round(self.landfill_diversion_rate, 2),
            'data_coverage_percent': round(self.data_coverage_percent, 2),
            'total_records': self.total_records,
            'verified_percent': round(self.verified_percent, 2),
            'total_documents': self.total_documents,
            'documents_by_category': self.documents_by_category,
        }


@dataclass
class TrendDataPointResponse:
    """Single trend data point"""
    period: str
    total_co2e_kg: float = 0
    total_waste_kg: float = 0
    record_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'period': self.period,
            'total_co2e_kg': round(self.total_co2e_kg, 4),
            'total_waste_kg': round(self.total_waste_kg, 2),
            'record_count': self.record_count,
        }


@dataclass
class BreakdownItemResponse:
    """Breakdown item (by type or treatment)"""
    label: str
    total_kg: float = 0
    total_co2e_kg: float = 0
    percentage: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'label': self.label,
            'total_kg': round(self.total_kg, 2),
            'total_co2e_kg': round(self.total_co2e_kg, 4),
            'percentage': round(self.percentage, 2),
        }
