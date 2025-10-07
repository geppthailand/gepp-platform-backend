"""
IoT Request DTOs for API input validation
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime


@dataclass
class IoTLoginRequest:
    """
    DTO for IoT Scale login request
    """
    scale_name: str
    password: str
    device_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for authentication operations"""
        result = {
            'scale_name': self.scale_name,
            'password': self.password
        }
        
        if self.device_info:
            result['device_info'] = self.device_info
            
        return result


@dataclass
class IoTTransactionRequest:
    """
    DTO for IoT Scale transaction data submission
    """
    weight: float
    material_type: str
    timestamp: str
    additional_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transaction creation"""
        result = {
            'weight': self.weight,
            'material_type': self.material_type,
            'timestamp': self.timestamp
        }
        
        if self.additional_data:
            result['additional_data'] = self.additional_data
            
        return result


@dataclass
class IoTCreateScaleRequest:
    """
    DTO for creating new IoT Scale
    """
    scale_name: str
    password: str
    owner_user_location_id: int
    location_point_id: int
    end_date: Optional[str] = None
    mac_tablet: Optional[str] = None
    mac_scale: Optional[str] = None
    scale_type: str = 'digital'
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for scale creation"""
        return {
            'scale_name': self.scale_name,
            'password': self.password,
            'owner_user_location_id': self.owner_user_location_id,
            'location_point_id': self.location_point_id,
            'end_date': self.end_date,
            'mac_tablet': self.mac_tablet,
            'mac_scale': self.mac_scale,
            'scale_type': self.scale_type,
            'notes': self.notes
        }


@dataclass
class IoTUpdateScaleRequest:
    """
    DTO for updating IoT Scale information
    """
    scale_name: Optional[str] = None
    password: Optional[str] = None
    location_point_id: Optional[int] = None
    end_date: Optional[str] = None
    mac_tablet: Optional[str] = None
    mac_scale: Optional[str] = None
    status: Optional[str] = None
    scale_type: Optional[str] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for scale update"""
        result = {}
        
        if self.scale_name is not None:
            result['scale_name'] = self.scale_name
        if self.password is not None:
            result['password'] = self.password
        if self.location_point_id is not None:
            result['location_point_id'] = self.location_point_id
        if self.end_date is not None:
            result['end_date'] = self.end_date
        if self.mac_tablet is not None:
            result['mac_tablet'] = self.mac_tablet
        if self.mac_scale is not None:
            result['mac_scale'] = self.mac_scale
        if self.status is not None:
            result['status'] = self.status
        if self.scale_type is not None:
            result['scale_type'] = self.scale_type
        if self.notes is not None:
            result['notes'] = self.notes
            
        return result
