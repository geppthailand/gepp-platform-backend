"""
ESG Request DTOs
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class UpdateEsgSettingsRequest:
    """DTO for updating ESG organization settings"""
    reporting_year: Optional[int] = None
    methodology: Optional[str] = None
    organizational_boundary: Optional[str] = None
    base_year: Optional[int] = None
    reduction_target_percent: Optional[float] = None
    reduction_target_year: Optional[int] = None
    line_channel_id: Optional[str] = None
    line_channel_secret: Optional[str] = None
    line_channel_token: Optional[str] = None

    def validate(self) -> List[str]:
        errors = []
        if self.methodology and self.methodology not in ('ghg_protocol', 'tgo_cfo', 'iso_14064'):
            errors.append('methodology must be one of: ghg_protocol, tgo_cfo, iso_14064')
        if self.organizational_boundary and self.organizational_boundary not in ('operational_control', 'financial_control', 'equity_share'):
            errors.append('organizational_boundary must be one of: operational_control, financial_control, equity_share')
        if self.reporting_year and (self.reporting_year < 2000 or self.reporting_year > 2100):
            errors.append('reporting_year must be between 2000 and 2100')
        if self.reduction_target_percent is not None and (self.reduction_target_percent < 0 or self.reduction_target_percent > 100):
            errors.append('reduction_target_percent must be between 0 and 100')
        return errors


@dataclass
class UploadDocumentRequest:
    """DTO for document upload metadata"""
    file_name: str
    file_url: str
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    source: str = 'upload'
    esg_category: Optional[str] = None
    esg_subcategory: Optional[str] = None
    document_type: Optional[str] = None
    reporting_year: Optional[int] = None
    notes: Optional[str] = None

    def validate(self) -> List[str]:
        errors = []
        if not self.file_name:
            errors.append('file_name is required')
        if not self.file_url:
            errors.append('file_url is required')
        valid_categories = ['environment', 'social', 'governance']
        if self.esg_category and self.esg_category not in valid_categories:
            errors.append(f'esg_category must be one of: {", ".join(valid_categories)}')
        return errors
