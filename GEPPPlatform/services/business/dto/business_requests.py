"""
Business Service Request DTOs
Placeholder DTOs for future business operations
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class BusinessProfileRequest:
    """
    DTO for business profile operations
    """
    company_name: str
    business_type: Optional[str] = None
    business_industry: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class BusinessSettingsRequest:
    """
    DTO for business settings configuration
    """
    settings: Dict[str, Any]
    category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for settings operations"""
        result = {'settings': self.settings}
        if self.category:
            result['category'] = self.category
        return result


@dataclass
class BusinessMetricsRequest:
    """
    DTO for business metrics queries
    """
    metric_types: list[str]
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for metrics operations"""
        result = {'metric_types': self.metric_types}
        if self.date_from:
            result['date_from'] = self.date_from
        if self.date_to:
            result['date_to'] = self.date_to
        if self.filters:
            result['filters'] = self.filters
        return result


@dataclass
class BusinessReportRequest:
    """
    DTO for business report generation
    """
    report_type: str
    format: str = "pdf"
    parameters: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for report operations"""
        result = {
            'report_type': self.report_type,
            'format': self.format
        }
        if self.parameters:
            result['parameters'] = self.parameters
        return result