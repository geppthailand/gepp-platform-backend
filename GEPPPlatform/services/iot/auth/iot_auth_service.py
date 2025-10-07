"""
IoT Scale Authentication Service
Handles authentication logic for IoT Scale devices
"""

import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

# Import models
from GEPPPlatform.models.iot.iot_scale import IoTScale
from GEPPPlatform.models.users.user_location import UserLocation

# Import exceptions
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    ValidationException
)


class IoTScaleAuthService:
    """
    Service for IoT Scale authentication operations
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.jwt_secret = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-here')
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def generate_iot_tokens(self, scale_id: int, owner_id: int, location_id: int) -> Dict[str, str]:
        """Generate JWT tokens for IoT Scale device"""
        now = datetime.now(timezone.utc)
        
        # IoT Auth token (short-lived: 1 hour)
        auth_payload = {
            'scale_id': scale_id,
            'owner_id': owner_id,
            'location_id': location_id,
            'type': 'iot_auth',
            'exp': now + timedelta(hours=1),
            'iat': now
        }
        
        # IoT Refresh token (long-lived: 24 hours)
        refresh_payload = {
            'scale_id': scale_id,
            'owner_id': owner_id,
            'location_id': location_id,
            'type': 'iot_refresh',
            'exp': now + timedelta(hours=24),
            'iat': now
        }
        
        auth_token = jwt.encode(auth_payload, self.jwt_secret, algorithm='HS256')
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm='HS256')
        
        return {
            'auth_token': auth_token,
            'refresh_token': refresh_token
        }

    def verify_iot_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode an IoT JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            
            # Verify it's an IoT token
            if payload.get('type') not in ['iot_auth', 'iot_refresh']:
                return None
                
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def login_scale(self, scale_name: str, password: str) -> Dict[str, Any]:
        """Authenticate IoT Scale device"""
        try:
            # Find scale by name
            scale = self.db_session.query(IoTScale).filter_by(
                scale_name=scale_name,
                is_active=True
            ).first()

            if not scale:
                raise UnauthorizedException('Invalid scale name or password')

            # Check if scale can authenticate
            if not scale.can_authenticate():
                raise UnauthorizedException('Scale is inactive or expired')

            # Verify password
            if not self.verify_password(password, scale.password):
                raise UnauthorizedException('Invalid scale name or password')

            # Generate tokens
            tokens = self.generate_iot_tokens(
                scale.id, 
                scale.owner_user_location_id,
                scale.location_point_id
            )

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 1 hour
                'scale': {
                    'id': scale.id,
                    'scale_name': scale.scale_name,
                    'status': scale.status,
                    'location_id': scale.location_point_id,
                    'owner_id': scale.owner_user_location_id,
                    'added_date': scale.added_date.isoformat() if scale.added_date else None
                }
            }

        except Exception as e:
            if isinstance(e, (UnauthorizedException, ValidationException)):
                raise e
            raise APIException(f"Login failed: {str(e)}")

    def refresh_iot_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh IoT authentication token"""
        try:
            # Verify refresh token
            payload = self.verify_iot_token(refresh_token)
            
            if not payload:
                raise UnauthorizedException('Invalid or expired refresh token')
            
            # Check if it's a refresh token
            if payload.get('type') != 'iot_refresh':
                raise UnauthorizedException('Invalid token type')
            
            # Verify scale still exists and is active
            scale_id = payload.get('scale_id')
            scale = self.db_session.query(IoTScale).filter_by(
                id=scale_id,
                is_active=True
            ).first()

            if not scale:
                raise NotFoundException('IoT Scale not found')

            if not scale.can_authenticate():
                raise UnauthorizedException('Scale is inactive or expired')

            # Generate new tokens
            tokens = self.generate_iot_tokens(
                scale.id,
                scale.owner_user_location_id,
                scale.location_point_id
            )

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600  # 1 hour
            }

        except Exception as e:
            if isinstance(e, (UnauthorizedException, NotFoundException, ValidationException)):
                raise e
            raise APIException(f"Token refresh failed: {str(e)}")

    def validate_iot_token(self, token: str) -> Dict[str, Any]:
        """Validate IoT token and return scale information"""
        try:
            # Verify token
            payload = self.verify_iot_token(token)
            
            if not payload:
                raise UnauthorizedException('Invalid or expired token')
            
            # Check if it's an auth token
            if payload.get('type') != 'iot_auth':
                raise UnauthorizedException('Invalid token type')
            
            # Get scale information
            scale_id = payload.get('scale_id')
            scale = self.db_session.query(IoTScale).filter_by(
                id=scale_id,
                is_active=True
            ).first()

            if not scale:
                raise NotFoundException('IoT Scale not found')

            if not scale.can_authenticate():
                raise UnauthorizedException('Scale is inactive or expired')

            return {
                'success': True,
                'scale': {
                    'id': scale.id,
                    'scale_name': scale.scale_name,
                    'status': scale.status,
                    'location_id': scale.location_point_id,
                    'owner_id': scale.owner_user_location_id
                }
            }

        except Exception as e:
            if isinstance(e, (UnauthorizedException, NotFoundException, ValidationException)):
                raise e
            raise APIException(f"Token validation failed: {str(e)}")

    def get_scale_from_token(self, token: str) -> Optional[IoTScale]:
        """Get IoT Scale object from token"""
        try:
            payload = self.verify_iot_token(token)
            if not payload or payload.get('type') != 'iot_auth':
                return None
            
            scale_id = payload.get('scale_id')
            return self.db_session.query(IoTScale).filter_by(
                id=scale_id,
                is_active=True
            ).first()
            
        except Exception:
            return None
