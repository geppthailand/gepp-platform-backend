"""
IoT Scale Service
Business logic for IoT Scale management and operations
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Import models
from GEPPPlatform.models.iot.iot_scale import IoTScale
from GEPPPlatform.models.users.user_location import UserLocation

# Import DTOs
from .dto.iot_requests import IoTCreateScaleRequest, IoTUpdateScaleRequest
from .dto.iot_responses import (
    IoTUserInfo, IoTPermissions, IoTLocationInfo, IoTLocationSettings,
    IoTUserInfoResponse, IoTLocationInfoResponse
)

# Import exceptions
from ...exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException,
    ConflictException
)

logger = logging.getLogger(__name__)


class IoTScaleService:
    """
    Service for IoT Scale business operations
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
    def create_scale(self, data: Dict[str, Any], owner_id: int) -> IoTScale:
        """Create a new IoT Scale"""
        try:
            # Validate required fields
            required_fields = ['scale_name', 'password', 'owner_user_location_id', 'location_point_id']
            for field in required_fields:
                if field not in data or not data[field]:
                    raise ValidationException(f'{field} is required')
            
            # Check if scale name already exists
            existing_scale = self.get_scale_by_name(data['scale_name'])
            if existing_scale:
                raise ConflictException('Scale name already exists')
            
            # Verify owner exists
            owner = self.db_session.query(UserLocation).filter_by(
                id=data['owner_user_location_id'],
                is_active=True
            ).first()
            if not owner:
                raise NotFoundException('Owner user not found')
            
            # Verify location exists
            location = self.db_session.query(UserLocation).filter_by(
                id=data['location_point_id'],
                is_active=True
            ).first()
            if not location:
                raise NotFoundException('Location not found')
            
            # Hash password
            from .auth.iot_auth_service import IoTScaleAuthService
            auth_service = IoTScaleAuthService(self.db_session)
            hashed_password = auth_service.hash_password(data['password'])
            
            # Create scale
            scale = IoTScale(
                scale_name=data['scale_name'],
                password=hashed_password,
                owner_user_location_id=data['owner_user_location_id'],
                location_point_id=data['location_point_id'],
                end_date=datetime.fromisoformat(data['end_date']) if data.get('end_date') else None,
                mac_tablet=data.get('mac_tablet'),
                mac_scale=data.get('mac_scale'),
                scale_type=data.get('scale_type', 'digital'),
                notes=data.get('notes')
            )
            
            self.db_session.add(scale)
            self.db_session.commit()
            
            return scale
            
        except IntegrityError as e:
            self.db_session.rollback()
            if 'scale_name' in str(e):
                raise ConflictException('Scale name already exists')
            raise ValidationException('Data integrity error')
        except Exception as e:
            self.db_session.rollback()
            if isinstance(e, (ValidationException, NotFoundException, ConflictException)):
                raise e
            logger.error(f"Error creating IoT Scale: {str(e)}")
            raise APIException(f"Failed to create IoT Scale: {str(e)}")

    def get_scale_by_id(self, scale_id: int) -> Optional[IoTScale]:
        """Get IoT Scale by ID"""
        return self.db_session.query(IoTScale).filter_by(
            id=scale_id,
            is_active=True
        ).first()

    def get_scale_by_name(self, scale_name: str) -> Optional[IoTScale]:
        """Get IoT Scale by name"""
        return self.db_session.query(IoTScale).filter_by(
            scale_name=scale_name,
            is_active=True
        ).first()

    def get_scales_by_owner(self, owner_id: int) -> List[IoTScale]:
        """Get all scales owned by a user"""
        return self.db_session.query(IoTScale).filter_by(
            owner_user_location_id=owner_id,
            is_active=True
        ).all()

    def get_scales_by_location(self, location_id: int) -> List[IoTScale]:
        """Get all scales at a location"""
        return self.db_session.query(IoTScale).filter_by(
            location_point_id=location_id,
            is_active=True
        ).all()

    def update_scale(self, scale_id: int, data: Dict[str, Any]) -> IoTScale:
        """Update IoT Scale information"""
        try:
            scale = self.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            # Update fields
            if 'scale_name' in data and data['scale_name']:
                # Check if new name conflicts
                existing = self.get_scale_by_name(data['scale_name'])
                if existing and existing.id != scale_id:
                    raise ConflictException('Scale name already exists')
                scale.scale_name = data['scale_name']
            
            if 'password' in data and data['password']:
                from .auth.iot_auth_service import IoTScaleAuthService
                auth_service = IoTScaleAuthService(self.db_session)
                scale.password = auth_service.hash_password(data['password'])
            
            if 'location_point_id' in data and data['location_point_id']:
                # Verify location exists
                location = self.db_session.query(UserLocation).filter_by(
                    id=data['location_point_id'],
                    is_active=True
                ).first()
                if not location:
                    raise NotFoundException('Location not found')
                scale.location_point_id = data['location_point_id']
            
            if 'end_date' in data:
                scale.end_date = datetime.fromisoformat(data['end_date']) if data['end_date'] else None
            
            if 'mac_tablet' in data:
                scale.mac_tablet = data['mac_tablet']
            
            if 'mac_scale' in data:
                scale.mac_scale = data['mac_scale']
            
            if 'status' in data and data['status']:
                scale.status = data['status']
            
            if 'scale_type' in data and data['scale_type']:
                scale.scale_type = data['scale_type']
            
            if 'notes' in data:
                scale.notes = data['notes']
            
            self.db_session.commit()
            return scale
            
        except Exception as e:
            self.db_session.rollback()
            if isinstance(e, (ValidationException, NotFoundException, ConflictException)):
                raise e
            logger.error(f"Error updating IoT Scale: {str(e)}")
            raise APIException(f"Failed to update IoT Scale: {str(e)}")

    def delete_scale(self, scale_id: int, soft_delete: bool = True) -> bool:
        """Delete IoT Scale (soft delete by default)"""
        try:
            scale = self.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            if soft_delete:
                scale.is_active = False
                scale.deleted_date = datetime.now(timezone.utc)
            else:
                self.db_session.delete(scale)
            
            self.db_session.commit()
            return True
            
        except Exception as e:
            self.db_session.rollback()
            if isinstance(e, NotFoundException):
                raise e
            logger.error(f"Error deleting IoT Scale: {str(e)}")
            raise APIException(f"Failed to delete IoT Scale: {str(e)}")

    def get_owner_info(self, scale_id: int) -> IoTUserInfoResponse:
        """Get owner information for IoT Scale"""
        try:
            scale = self.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            owner = scale.owner
            if not owner:
                raise NotFoundException('Owner information not found')
            
            # Create user info
            user_info = IoTUserInfo(
                id=owner.id,
                display_name=owner.display_name or '',
                email=owner.email or '',
                phone=owner.phone or '',
                organization_id=owner.organization_id or 0,
                organization_name=owner.company_name or '',
                business_type=owner.business_type or '',
                business_industry=owner.business_industry or ''
            )
            
            # Create permissions (basic for now)
            permissions = IoTPermissions(
                can_create_transactions=True,
                max_daily_transactions=100,  # Default limit
                allowed_material_types=['plastic', 'paper', 'metal', 'glass', 'organic']  # Default materials
            )
            
            return IoTUserInfoResponse(
                success=True,
                owner=user_info,
                permissions=permissions
            )
            
        except Exception as e:
            if isinstance(e, NotFoundException):
                raise e
            logger.error(f"Error getting owner info: {str(e)}")
            raise APIException(f"Failed to get owner information: {str(e)}")

    def get_location_info(self, scale_id: int) -> IoTLocationInfoResponse:
        """Get location information for IoT Scale"""
        try:
            scale = self.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            location = scale.location
            if not location:
                raise NotFoundException('Location information not found')
            
            # Create location info
            location_info = IoTLocationInfo(
                id=location.id,
                display_name=location.display_name or '',
                name_th=location.name_th or '',
                name_en=location.name_en or '',
                coordinate=location.coordinate or '',
                address=location.address or '',
                postal_code=location.postal_code or '',
                country='Thailand',  # Default
                province='Bangkok',  # Default
                district='',  # Would need to join with location tables
                subdistrict=''  # Would need to join with location tables
            )
            
            # Create location settings
            location_settings = IoTLocationSettings(
                timezone='Asia/Bangkok',
                currency='THB',
                locale='TH',
                business_hours='08:00-17:00'  # Default
            )
            
            return IoTLocationInfoResponse(
                success=True,
                location=location_info,
                location_settings=location_settings
            )
            
        except Exception as e:
            if isinstance(e, NotFoundException):
                raise e
            logger.error(f"Error getting location info: {str(e)}")
            raise APIException(f"Failed to get location information: {str(e)}")
