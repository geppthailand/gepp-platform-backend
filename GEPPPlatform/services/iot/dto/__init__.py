"""
IoT DTO package - Data Transfer Objects for IoT Scale operations
"""

from .iot_requests import (
    IoTLoginRequest,
    IoTTransactionRequest,
    IoTCreateScaleRequest,
    IoTUpdateScaleRequest
)

from .iot_responses import (
    IoTLoginResponse,
    IoTUserInfoResponse,
    IoTLocationInfoResponse,
    IoTScaleResponse,
    IoTTransactionResponse
)

__all__ = [
    # Request DTOs
    'IoTLoginRequest',
    'IoTTransactionRequest', 
    'IoTCreateScaleRequest',
    'IoTUpdateScaleRequest',
    
    # Response DTOs
    'IoTLoginResponse',
    'IoTUserInfoResponse',
    'IoTLocationInfoResponse',
    'IoTScaleResponse',
    'IoTTransactionResponse'
]
