"""
EPR Service Request DTOs
Data Transfer Objects for Extended Producer Responsibility operations
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class EPRReportType(str, Enum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"


class ComplianceStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class EPRReportRequest:
    """
    DTO for EPR report generation and submission
    """
    report_type: EPRReportType
    reporting_period: str  # YYYY-MM or YYYY-Q# or YYYY format
    waste_data: Dict[str, Any]
    recycling_data: Optional[Dict[str, Any]] = None
    disposal_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for report operations"""
        result = {
            'report_type': self.report_type.value,
            'reporting_period': self.reporting_period,
            'waste_data': self.waste_data
        }

        if self.recycling_data:
            result['recycling_data'] = self.recycling_data
        if self.disposal_data:
            result['disposal_data'] = self.disposal_data
        if self.notes:
            result['notes'] = self.notes

        return result


@dataclass
class EPRComplianceRequest:
    """
    DTO for EPR compliance checking and validation
    """
    organization_id: str
    compliance_year: int
    target_requirements: Dict[str, Any]
    actual_performance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compliance operations"""
        return {
            'organization_id': self.organization_id,
            'compliance_year': self.compliance_year,
            'target_requirements': self.target_requirements,
            'actual_performance': self.actual_performance
        }


@dataclass
class EPRSubmissionRequest:
    """
    DTO for EPR regulatory submission
    """
    report_id: str
    regulatory_body: str
    submission_deadline: str
    supporting_documents: Optional[List[str]] = None
    contact_person: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for submission operations"""
        result = {
            'report_id': self.report_id,
            'regulatory_body': self.regulatory_body,
            'submission_deadline': self.submission_deadline
        }

        if self.supporting_documents:
            result['supporting_documents'] = self.supporting_documents
        if self.contact_person:
            result['contact_person'] = self.contact_person

        return result


@dataclass
class EPRCertificateRequest:
    """
    DTO for EPR certificate generation
    """
    organization_id: str
    certificate_type: str
    validity_period: str
    compliance_data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for certificate operations"""
        return {
            'organization_id': self.organization_id,
            'certificate_type': self.certificate_type,
            'validity_period': self.validity_period,
            'compliance_data': self.compliance_data
        }