"""
G360 Service DTOs
Data Transfer Objects for G360 platform operations and integrations
"""

from .g360_requests import (
    G360SyncRequest,
    G360DataRequest,
    G360IntegrationRequest,
    G360WebhookRequest
)

from .g360_responses import (
    G360SyncResponse,
    G360DataResponse,
    G360IntegrationResponse,
    G360WebhookResponse,
    G360StatusResponse
)

__all__ = [
    # Request DTOs
    'G360SyncRequest',
    'G360DataRequest',
    'G360IntegrationRequest',
    'G360WebhookRequest',

    # Response DTOs
    'G360SyncResponse',
    'G360DataResponse',
    'G360IntegrationResponse',
    'G360WebhookResponse',
    'G360StatusResponse'
]