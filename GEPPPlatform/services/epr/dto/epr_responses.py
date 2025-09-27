"""
EPR Service Response DTOs
Data Transfer Objects for Extended Producer Responsibility operations
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class EPRReportResponse:
    """
    DTO for EPR report data and status
    """
    report_id: str
    report_type: str
    reporting_period: str
    status: str
    created_at: str
    submitted_at: Optional[str] = None
    approved_at: Optional[str] = None
    download_url: Optional[str] = None
    waste_summary: Optional[Dict[str, Any]] = None
    compliance_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EPRComplianceResponse:
    """
    DTO for EPR compliance assessment results
    """
    organization_id: str
    compliance_year: int
    overall_score: float
    compliance_status: str
    target_met: bool
    areas_of_concern: List[str]
    recommendations: List[str]
    next_review_date: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class EPRSubmissionResponse:
    """
    DTO for EPR regulatory submission results
    """
    submission_id: str
    report_id: str
    regulatory_body: str
    submitted_at: str
    status: str
    confirmation_number: Optional[str] = None
    feedback: Optional[str] = None
    next_action_required: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EPRCertificateResponse:
    """
    DTO for EPR certificate information
    """
    certificate_id: str
    organization_id: str
    certificate_type: str
    issued_date: str
    valid_until: str
    status: str
    download_url: Optional[str] = None
    verification_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EPRStatusResponse:
    """
    DTO for overall EPR status and dashboard data
    """
    organization_id: str
    current_year: int
    compliance_status: str
    pending_reports: int
    overdue_submissions: int
    upcoming_deadlines: List[Dict[str, Any]]
    recent_activities: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__