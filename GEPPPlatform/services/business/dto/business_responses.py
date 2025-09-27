"""
Business Service Response DTOs
Placeholder DTOs for future business operations
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class BusinessProfileResponse:
    """
    DTO for business profile data
    """
    id: str
    company_name: str
    business_type: Optional[str] = None
    business_industry: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class BusinessSettingsResponse:
    """
    DTO for business settings data
    """
    category: str
    settings: Dict[str, Any]
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class BusinessMetricsResponse:
    """
    DTO for business metrics data
    """
    metrics: Dict[str, Any]
    period: str
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class BusinessReportResponse:
    """
    DTO for business report generation results
    """
    report_id: str
    report_type: str
    format: str
    download_url: Optional[str] = None
    expires_at: Optional[str] = None
    status: str = "completed"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}