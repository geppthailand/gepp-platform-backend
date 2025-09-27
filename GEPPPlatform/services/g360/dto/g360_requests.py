"""
G360 Service Request DTOs
Data Transfer Objects for G360 platform operations and integrations
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class SyncType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    SELECTIVE = "selective"


class IntegrationType(str, Enum):
    API = "api"
    WEBHOOK = "webhook"
    FILE_TRANSFER = "file_transfer"


@dataclass
class G360SyncRequest:
    """
    DTO for G360 data synchronization operations
    """
    sync_type: SyncType
    data_types: List[str]
    organization_id: str
    last_sync_timestamp: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for sync operations"""
        result = {
            'sync_type': self.sync_type.value,
            'data_types': self.data_types,
            'organization_id': self.organization_id
        }

        if self.last_sync_timestamp:
            result['last_sync_timestamp'] = self.last_sync_timestamp
        if self.filters:
            result['filters'] = self.filters

        return result


@dataclass
class G360DataRequest:
    """
    DTO for G360 data exchange operations
    """
    operation: str  # get, post, put, delete
    endpoint: str
    data: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for data operations"""
        result = {
            'operation': self.operation,
            'endpoint': self.endpoint
        }

        if self.data:
            result['data'] = self.data
        if self.parameters:
            result['parameters'] = self.parameters
        if self.headers:
            result['headers'] = self.headers

        return result


@dataclass
class G360IntegrationRequest:
    """
    DTO for G360 integration setup and configuration
    """
    integration_type: IntegrationType
    organization_id: str
    configuration: Dict[str, Any]
    enabled: bool = True
    webhook_url: Optional[str] = None
    api_credentials: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for integration operations"""
        result = {
            'integration_type': self.integration_type.value,
            'organization_id': self.organization_id,
            'configuration': self.configuration,
            'enabled': self.enabled
        }

        if self.webhook_url:
            result['webhook_url'] = self.webhook_url
        if self.api_credentials:
            result['api_credentials'] = self.api_credentials

        return result


@dataclass
class G360WebhookRequest:
    """
    DTO for G360 webhook operations
    """
    event_type: str
    payload: Dict[str, Any]
    source: str = "g360"
    timestamp: Optional[str] = None
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for webhook operations"""
        result = {
            'event_type': self.event_type,
            'payload': self.payload,
            'source': self.source
        }

        if self.timestamp:
            result['timestamp'] = self.timestamp
        if self.signature:
            result['signature'] = self.signature

        return result