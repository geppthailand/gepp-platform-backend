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
class CreateWasteRecordRequest:
    """DTO for creating a waste record"""
    record_date: str
    waste_type: str
    treatment_method: str
    weight_kg: float

    # Optional
    waste_category: Optional[str] = None
    data_quality: str = 'estimated'
    source: str = 'manual'
    origin_location_id: Optional[int] = None
    vendor_name: Optional[str] = None
    cost: Optional[float] = None
    currency: str = 'THB'
    notes: Optional[str] = None
    document_id: Optional[int] = None

    def validate(self) -> List[str]:
        errors = []
        if not self.record_date:
            errors.append('record_date is required')
        if not self.waste_type:
            errors.append('waste_type is required')
        if not self.treatment_method:
            errors.append('treatment_method is required')
        if self.weight_kg is None or self.weight_kg <= 0:
            errors.append('weight_kg must be greater than 0')
        valid_waste_types = ['general', 'organic', 'plastic', 'paper', 'glass', 'metal', 'electronic', 'hazardous']
        if self.waste_type and self.waste_type not in valid_waste_types:
            errors.append(f'waste_type must be one of: {", ".join(valid_waste_types)}')
        valid_treatments = ['landfill', 'incineration', 'recycling', 'composting', 'anaerobic_digestion']
        if self.treatment_method and self.treatment_method not in valid_treatments:
            errors.append(f'treatment_method must be one of: {", ".join(valid_treatments)}')
        return errors


@dataclass
class BulkCreateWasteRecordsRequest:
    """DTO for bulk creating waste records from AI extraction"""
    document_id: int
    records: List[Dict[str, Any]] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors = []
        if not self.document_id:
            errors.append('document_id is required')
        if not self.records:
            errors.append('records list is required and must not be empty')
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
