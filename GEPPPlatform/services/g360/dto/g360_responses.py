"""
G360 Service Response DTOs
Data Transfer Objects for G360 platform operations and integrations
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class G360SyncResponse:
    """
    DTO for G360 synchronization results
    """
    sync_id: str
    sync_type: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    records_processed: int = 0
    records_successful: int = 0
    records_failed: int = 0
    errors: Optional[List[str]] = None
    next_sync_recommended: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class G360DataResponse:
    """
    DTO for G360 data exchange results
    """
    operation: str
    endpoint: str
    status: str
    response_data: Optional[Dict[str, Any]] = None
    response_code: Optional[int] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class G360IntegrationResponse:
    """
    DTO for G360 integration configuration results
    """
    integration_id: str
    integration_type: str
    organization_id: str
    status: str
    created_at: str
    last_tested_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    configuration: Dict[str, Any] = None
    health_status: Optional[str] = None

    def __post_init__(self):
        if self.configuration is None:
            self.configuration = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class G360WebhookResponse:
    """
    DTO for G360 webhook processing results
    """
    webhook_id: str
    event_type: str
    processed_at: str
    status: str
    response_sent: bool = False
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class G360StatusResponse:
    """
    DTO for G360 platform status and health check
    """
    platform_status: str
    organization_id: str
    integrations_active: int
    last_sync_status: Optional[str] = None
    last_sync_at: Optional[str] = None
    pending_webhooks: int = 0
    api_rate_limit_remaining: Optional[int] = None
    system_alerts: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {k: v for k, v in self.__dict__.items() if v is not None}