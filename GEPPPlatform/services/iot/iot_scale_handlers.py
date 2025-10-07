"""
IoT Scale Handlers
HTTP request handlers for IoT Scale management and operations
"""

from typing import Dict, Any
import logging

from .iot_scale_service import IoTScaleService
from .auth.iot_auth_service import IoTScaleAuthService
from .dto.iot_responses import IoTScaleResponse, IoTScaleDetail, IoTUserInfo, IoTLocationInfo

logger = logging.getLogger(__name__)

from ...exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException,
    ConflictException
)


class IoTScaleHandlers:
    """
    Handlers for IoT Scale management endpoints
    """
    
    def __init__(self, db_session):
        self.db_session = db_session
        self.scale_service = IoTScaleService(db_session)
        self.auth_service = IoTScaleAuthService(db_session)
    
    def handle_create_scale(self, data: Dict[str, Any], current_user_id: int) -> Dict[str, Any]:
        """Handle create IoT Scale request"""
        try:
            # Create scale (current_user_id is the owner)
            data['owner_user_location_id'] = current_user_id
            scale = self.scale_service.create_scale(data, current_user_id)
            
            # Create response
            scale_detail = self._create_scale_detail_response(scale)
            
            response = IoTScaleResponse(
                success=True,
                scale=scale_detail,
                message="IoT Scale created successfully"
            )
            
            return response.to_dict()
            
        except Exception as e:
            if isinstance(e, (ValidationException, NotFoundException, ConflictException)):
                raise e
            logger.error(f"Error creating IoT Scale: {str(e)}")
            raise APIException(f"Failed to create IoT Scale: {str(e)}")

    def handle_get_scale(self, scale_id: int, current_user_id: int) -> Dict[str, Any]:
        """Handle get IoT Scale request"""
        try:
            scale = self.scale_service.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            # Check if user has access to this scale
            if scale.owner_user_location_id != current_user_id:
                raise UnauthorizedException('Access denied to this IoT Scale')
            
            # Create response
            scale_detail = self._create_scale_detail_response(scale)
            
            response = IoTScaleResponse(
                success=True,
                scale=scale_detail,
                message="IoT Scale retrieved successfully"
            )
            
            return response.to_dict()
            
        except Exception as e:
            if isinstance(e, (NotFoundException, UnauthorizedException)):
                raise e
            logger.error(f"Error getting IoT Scale: {str(e)}")
            raise APIException(f"Failed to get IoT Scale: {str(e)}")

    def handle_list_scales(self, current_user_id: int, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list IoT Scales request"""
        try:
            # Get scales owned by current user
            scales = self.scale_service.get_scales_by_owner(current_user_id)
            
            # Create response list
            scale_list = []
            for scale in scales:
                scale_detail = self._create_scale_detail_response(scale)
                scale_list.append(scale_detail.to_dict())
            
            return {
                'success': True,
                'scales': scale_list,
                'total_count': len(scale_list),
                'message': f"Found {len(scale_list)} IoT Scales"
            }
            
        except Exception as e:
            logger.error(f"Error listing IoT Scales: {str(e)}")
            raise APIException(f"Failed to list IoT Scales: {str(e)}")

    def handle_update_scale(self, scale_id: int, data: Dict[str, Any], current_user_id: int) -> Dict[str, Any]:
        """Handle update IoT Scale request"""
        try:
            # Check if user has access to this scale
            scale = self.scale_service.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            if scale.owner_user_location_id != current_user_id:
                raise UnauthorizedException('Access denied to this IoT Scale')
            
            # Update scale
            updated_scale = self.scale_service.update_scale(scale_id, data)
            
            # Create response
            scale_detail = self._create_scale_detail_response(updated_scale)
            
            response = IoTScaleResponse(
                success=True,
                scale=scale_detail,
                message="IoT Scale updated successfully"
            )
            
            return response.to_dict()
            
        except Exception as e:
            if isinstance(e, (NotFoundException, UnauthorizedException, ValidationException, ConflictException)):
                raise e
            logger.error(f"Error updating IoT Scale: {str(e)}")
            raise APIException(f"Failed to update IoT Scale: {str(e)}")

    def handle_delete_scale(self, scale_id: int, current_user_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """Handle delete IoT Scale request"""
        try:
            # Check if user has access to this scale
            scale = self.scale_service.get_scale_by_id(scale_id)
            if not scale:
                raise NotFoundException('IoT Scale not found')
            
            if scale.owner_user_location_id != current_user_id:
                raise UnauthorizedException('Access denied to this IoT Scale')
            
            # Delete scale
            success = self.scale_service.delete_scale(scale_id, soft_delete)
            
            return {
                'success': success,
                'message': f"IoT Scale {'deactivated' if soft_delete else 'deleted'} successfully"
            }
            
        except Exception as e:
            if isinstance(e, (NotFoundException, UnauthorizedException)):
                raise e
            logger.error(f"Error deleting IoT Scale: {str(e)}")
            raise APIException(f"Failed to delete IoT Scale: {str(e)}")

    def handle_get_user_info(self, token: str) -> Dict[str, Any]:
        """Handle get user info request for IoT Scale"""
        try:
            # Get scale from token
            scale = self.auth_service.get_scale_from_token(token)
            if not scale:
                raise UnauthorizedException('Invalid or expired token')
            
            # Get owner info
            owner_response = self.scale_service.get_owner_info(scale.id)
            
            return owner_response.to_dict()
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, NotFoundException)):
                raise e
            logger.error(f"Error getting user info: {str(e)}")
            raise APIException(f"Failed to get user information: {str(e)}")

    def handle_get_location_info(self, token: str) -> Dict[str, Any]:
        """Handle get location info request for IoT Scale"""
        try:
            # Get scale from token
            scale = self.auth_service.get_scale_from_token(token)
            if not scale:
                raise UnauthorizedException('Invalid or expired token')
            
            # Get location info
            location_response = self.scale_service.get_location_info(scale.id)
            
            return location_response.to_dict()
            
        except Exception as e:
            if isinstance(e, (UnauthorizedException, NotFoundException)):
                raise e
            logger.error(f"Error getting location info: {str(e)}")
            raise APIException(f"Failed to get location information: {str(e)}")

    def _create_scale_detail_response(self, scale) -> IoTScaleDetail:
        """Create detailed scale response"""
        # Get owner info
        owner = scale.owner
        owner_info = IoTUserInfo(
            id=owner.id if owner else 0,
            display_name=owner.display_name if owner else '',
            email=owner.email if owner else '',
            phone=owner.phone if owner else '',
            organization_id=owner.organization_id if owner else 0,
            organization_name=owner.company_name if owner else '',
            business_type=owner.business_type if owner else '',
            business_industry=owner.business_industry if owner else ''
        )
        
        # Get location info
        location = scale.location
        location_info = IoTLocationInfo(
            id=location.id if location else 0,
            display_name=location.display_name if location else '',
            name_th=location.name_th if location else '',
            name_en=location.name_en if location else '',
            coordinate=location.coordinate if location else '',
            address=location.address if location else '',
            postal_code=location.postal_code if location else '',
            country='Thailand',
            province='Bangkok',
            district='',
            subdistrict=''
        )
        
        return IoTScaleDetail(
            id=scale.id,
            scale_name=scale.scale_name,
            status=scale.status,
            scale_type=scale.scale_type,
            owner_user_location_id=scale.owner_user_location_id,
            location_point_id=scale.location_point_id,
            added_date=scale.added_date.isoformat() if scale.added_date else '',
            end_date=scale.end_date.isoformat() if scale.end_date else None,
            mac_tablet=scale.mac_tablet,
            mac_scale=scale.mac_scale,
            notes=scale.notes,
            owner_info=owner_info,
            location_info=location_info
        )
