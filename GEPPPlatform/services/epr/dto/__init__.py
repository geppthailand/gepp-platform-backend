"""
EPR (Extended Producer Responsibility) Service DTOs
Data Transfer Objects for EPR compliance and reporting operations
"""

from .epr_requests import (
    EPRReportRequest,
    EPRComplianceRequest,
    EPRSubmissionRequest,
    EPRCertificateRequest
)

from .epr_responses import (
    EPRReportResponse,
    EPRComplianceResponse,
    EPRSubmissionResponse,
    EPRCertificateResponse,
    EPRStatusResponse
)

__all__ = [
    # Request DTOs
    'EPRReportRequest',
    'EPRComplianceRequest',
    'EPRSubmissionRequest',
    'EPRCertificateRequest',

    # Response DTOs
    'EPRReportResponse',
    'EPRComplianceResponse',
    'EPRSubmissionResponse',
    'EPRCertificateResponse',
    'EPRStatusResponse'
]