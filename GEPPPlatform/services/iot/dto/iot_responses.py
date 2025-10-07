"""
IoT Response DTOs for API output formatting
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List


@dataclass
class IoTLoginResponse:
    """
    DTO for IoT Scale login response
    """
    success: bool
    auth_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600  # 1 hour for IoT devices
    scale: 'IoTScaleInfo'
    message: Optional[str] = "Login successful"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'auth_token': self.auth_token,
            'refresh_token': self.refresh_token,
            'token_type': self.token_type,
            'expires_in': self.expires_in,
            'scale': self.scale.to_dict(),
            'message': self.message
        }


@dataclass
class IoTScaleInfo:
    """
    DTO for IoT Scale basic information
    """
    id: int
    scale_name: str
    status: str
    location_id: int
    owner_id: int
    added_date: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'scale_name': self.scale_name,
            'status': self.status,
            'location_id': self.location_id,
            'owner_id': self.owner_id,
            'added_date': self.added_date
        }


@dataclass
class IoTUserInfoResponse:
    """
    DTO for IoT Scale user info response
    """
    success: bool
    owner: 'IoTUserInfo'
    permissions: 'IoTPermissions'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'owner': self.owner.to_dict(),
            'permissions': self.permissions.to_dict()
        }


@dataclass
class IoTUserInfo:
    """
    DTO for IoT Scale owner information
    """
    id: int
    display_name: str
    email: str
    phone: str
    organization_id: int
    organization_name: str
    business_type: str
    business_industry: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'display_name': self.display_name,
            'email': self.email,
            'phone': self.phone,
            'organization_id': self.organization_id,
            'organization_name': self.organization_name,
            'business_type': self.business_type,
            'business_industry': self.business_industry
        }


@dataclass
class IoTPermissions:
    """
    DTO for IoT Scale permissions
    """
    can_create_transactions: bool
    max_daily_transactions: int
    allowed_material_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'can_create_transactions': self.can_create_transactions,
            'max_daily_transactions': self.max_daily_transactions,
            'allowed_material_types': self.allowed_material_types
        }


@dataclass
class IoTLocationInfoResponse:
    """
    DTO for IoT Scale location info response
    """
    success: bool
    location: 'IoTLocationInfo'
    location_settings: 'IoTLocationSettings'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'location': self.location.to_dict(),
            'location_settings': self.location_settings.to_dict()
        }


@dataclass
class IoTLocationInfo:
    """
    DTO for IoT Scale location information
    """
    id: int
    display_name: str
    name_th: str
    name_en: str
    coordinate: str
    address: str
    postal_code: str
    country: str
    province: str
    district: str
    subdistrict: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'display_name': self.display_name,
            'name_th': self.name_th,
            'name_en': self.name_en,
            'coordinate': self.coordinate,
            'address': self.address,
            'postal_code': self.postal_code,
            'country': self.country,
            'province': self.province,
            'district': self.district,
            'subdistrict': self.subdistrict
        }


@dataclass
class IoTLocationSettings:
    """
    DTO for IoT Scale location settings
    """
    timezone: str
    currency: str
    locale: str
    business_hours: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timezone': self.timezone,
            'currency': self.currency,
            'locale': self.locale,
            'business_hours': self.business_hours
        }


@dataclass
class IoTScaleResponse:
    """
    DTO for IoT Scale management responses
    """
    success: bool
    scale: 'IoTScaleDetail'
    message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'scale': self.scale.to_dict(),
            'message': self.message
        }


@dataclass
class IoTScaleDetail:
    """
    DTO for detailed IoT Scale information
    """
    id: int
    scale_name: str
    status: str
    scale_type: str
    owner_user_location_id: int
    location_point_id: int
    added_date: str
    end_date: Optional[str]
    mac_tablet: Optional[str]
    mac_scale: Optional[str]
    notes: Optional[str]
    owner_info: 'IoTUserInfo'
    location_info: 'IoTLocationInfo'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'scale_name': self.scale_name,
            'status': self.status,
            'scale_type': self.scale_type,
            'owner_user_location_id': self.owner_user_location_id,
            'location_point_id': self.location_point_id,
            'added_date': self.added_date,
            'end_date': self.end_date,
            'mac_tablet': self.mac_tablet,
            'mac_scale': self.mac_scale,
            'notes': self.notes,
            'owner_info': self.owner_info.to_dict(),
            'location_info': self.location_info.to_dict()
        }


@dataclass
class IoTTransactionResponse:
    """
    DTO for IoT Scale transaction response
    """
    success: bool
    transaction: 'IoTTransactionInfo'
    message: Optional[str] = "Transaction created successfully"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'success': self.success,
            'transaction': self.transaction.to_dict(),
            'message': self.message
        }


@dataclass
class IoTTransactionInfo:
    """
    DTO for IoT Scale transaction information
    """
    id: int
    weight: float
    material_type: str
    status: str
    created_date: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'weight': self.weight,
            'material_type': self.material_type,
            'status': self.status,
            'created_date': self.created_date
        }
