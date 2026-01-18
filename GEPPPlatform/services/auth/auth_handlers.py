"""
Authentication handlers for the auth module
"""

import os
import jwt
import bcrypt
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# SQLAlchemy imports
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Database imports
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.integration_tokens import IntegrationToken
from GEPPPlatform.models.subscriptions.organizations import Organization, OrganizationInfo
from GEPPPlatform.models.subscriptions.subscription_models import SubscriptionPlan, Subscription
from GEPPPlatform.models.cores.iot_devices import IoTDevice
from ..cores.organizations.organization_role_presets import OrganizationRolePresets
from ...exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)

class AuthHandlers:

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

    def generate_secret_key(self) -> str:
        """Generate a random secret key for integration authentication (64 characters)"""
        return secrets.token_urlsafe(48)  # Generates ~64 characters

    def generate_jwt_tokens(self, user_id: int, organization_id: int, email: str) -> Dict[str, str]:
        """Generate JWT auth_token and refresh_token"""
        now = datetime.now(timezone.utc)
        
        # Auth token (short-lived: 15 minutes)
        auth_payload = {
            'user_id': user_id,
            'organization_id': organization_id,
            'email': email,
            'type': 'auth',
            'exp': now + timedelta(minutes=15),
            'iat': now
        }
        
        # Refresh token (long-lived: 7 days)
        refresh_payload = {
            'user_id': user_id,
            'organization_id': organization_id,
            'email': email,
            'type': 'refresh',
            'exp': now + timedelta(days=7),
            'iat': now
        }
        
        auth_token = jwt.encode(auth_payload, self.jwt_secret, algorithm='HS256')
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm='HS256')
        
        return {
            'auth_token': auth_token,
            'refresh_token': refresh_token
        }

    def generate_device_tokens(self, device_id: int, device_name: str) -> Dict[str, str]:
        """Generate JWT auth_token and refresh_token for IoT devices"""
        now = datetime.now(timezone.utc)

        auth_payload = {
            'device_id': device_id,
            'device_name': device_name,
            'type': 'device',
            'exp': now + timedelta(minutes=15),
            'iat': now
        }

        refresh_payload = {
            'device_id': device_id,
            'device_name': device_name,
            'type': 'device_refresh',
            'exp': now + timedelta(days=7),
            'iat': now
        }

        auth_token = jwt.encode(auth_payload, self.jwt_secret, algorithm='HS256')
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm='HS256')

        return {
            'auth_token': auth_token,
            'refresh_token': refresh_token
        }

    def generate_jwt_token(self, user_id: int, organization_id: int, email: str) -> str:
        """Generate a single JWT token for backwards compatibility"""
        now = datetime.now(timezone.utc)
        payload = {
            'user_id': user_id,
            'organization_id': organization_id,
            'email': email,
            'exp': now + timedelta(days=30),
            'iat': now
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        return token

    def verify_jwt_token(self, token: str, path: str = None) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token. For integration tokens, verifies with user-specific secret."""
        try:
            # First decode without verification to check token type
            unverified_payload = jwt.decode(token, options={"verify_signature": False})

            # Check if this is an integration token
            if unverified_payload.get('type') == 'integration':
                # Integration tokens must be used on /api/integration/* routes only
                if path and not path.startswith('/api/integration'):
                    print(f"Integration token used on non-integration route: {path}")
                    return None

                # Get user's secret key from database
                user_id = unverified_payload.get('user_id')
                if not user_id:
                    return None

                session = self.db_session
                user = session.query(UserLocation).filter_by(id=user_id, is_active=True).first()

                if not user or not user.secret:
                    print(f"User not found or no secret key for user_id: {user_id}")
                    return None

                # Verify token with user's secret key
                payload = jwt.decode(token, user.secret, algorithms=['HS256'])
                return payload
            else:
                # Regular tokens - verify with global secret
                payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])

                # Regular tokens cannot access /api/integration/* routes
                if path and path.startswith('/api/integration'):
                    print(f"Regular token used on integration route: {path}")
                    return None

                return payload

        except jwt.ExpiredSignatureError:
            print("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            print(f"Invalid token: {e}")
            return None

    def register(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Register a new user with organization and free subscription using SQLAlchemy"""
        try:
            # Extract registration data
            email = data.get('email')
            password = data.get('password')
            first_name = data.get('firstName')
            last_name = data.get('lastName')
            phone = data.get('phoneNumber')
            display_name = data.get('displayName')
            account_type = data.get('accountType')
            industry = data.get('industry', '')
            sub_industry = data.get('subIndustry', '')
            use_purpose = data.get('usePurpose', '')
            
            session = self.db_session
            # Check if email already exists
            existing_user = session.query(UserLocation).filter_by(email=email).first()
            if existing_user:
                raise ValidationException('Email already registered')

            # Hash the password
            hashed_password = self.hash_password(password)

            try:
                # 1. Create organization info
                org_info = OrganizationInfo(
                    company_name=display_name,
                    display_name=display_name,
                    business_industry=industry,
                    business_sub_industry=sub_industry,
                    account_type=account_type,
                    use_purpose=use_purpose,
                    company_email=email,
                    phone_number=phone
                )
                session.add(org_info)
                session.flush()  # Get the ID

                # 2. Create organization
                organization = Organization(
                    name=display_name,
                    description=f"Organization for {display_name}",
                    organization_info_id=org_info.id
                )
                session.add(organization)
                session.flush()  # Get the ID

                # 3. Create user location (owner)
                user = UserLocation(
                    is_user=True,
                    is_location=False,
                    name_en=f"{first_name} {last_name}",
                    display_name=display_name,
                    email=email,
                    phone=phone,
                    username=email,
                    password=hashed_password,
                    platform='GEPP_BUSINESS_WEB',  # Set platform correctly
                    organization_id=organization.id,
                    business_industry=industry,
                    business_sub_industry=sub_industry,
                    company_name=display_name,
                    company_email=email,
                    company_phone=phone,
                    organization_level=0
                )
                session.add(user)
                session.flush()  # Get the ID

                # 4. Update organization with owner
                organization.owner_id = user.id

                # 5. Get or create free subscription plan
                free_plan = session.query(SubscriptionPlan).filter_by(name='free').first()

                if not free_plan:
                    # Create free plan if it doesn't exist
                    free_plan = SubscriptionPlan(
                        name='free',
                        display_name='Free Plan',
                        description='Basic features for getting started',
                        price_monthly=0,
                        price_yearly=0,
                        max_users=5,
                        max_transactions_monthly=100,
                        max_storage_gb=1,
                        max_api_calls_daily=1000,
                        features=json.dumps([
                            'Basic waste tracking',
                            'Up to 5 users',
                            '100 transactions/month',
                            '1GB storage',
                            'Basic reporting'
                        ])
                    )
                    session.add(free_plan)
                    session.flush()  # Get the ID
                    
                # 6. Create subscription for organization
                now = datetime.now(timezone.utc)
                subscription = Subscription(
                    organization_id=organization.id,
                    plan_id=free_plan.id,
                    status='active',
                    trial_ends_at=(now + timedelta(days=14)).isoformat(),
                    current_period_starts_at=now.isoformat(),
                    current_period_ends_at=(now + timedelta(days=30)).isoformat(),
                    users_count=1
                )
                session.add(subscription)
                session.flush()  # Get the ID
                    
                # 7. Update organization with subscription
                organization.subscription_id = subscription.id

                # 8. Create default organization roles
                role_presets = OrganizationRolePresets(session)
                default_roles = role_presets.create_default_roles_for_organization(organization.id)

                # Commit the transaction
                session.commit()

                return {
                    'success': True,
                    'message': 'Registration successful! Please login with your credentials.',
                    'user': {
                        'id': user.id,
                        'email': email,
                        'displayName': display_name
                    }
                }

            except IntegrityError as e:
                session.rollback()
                raise ValidationException('Email already registered or data integrity error')
            except Exception as e:
                session.rollback()
                raise e

        except Exception as e:
            raise APIException(str(e))

    def login(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Login user with email and password using SQLAlchemy"""
        try:
            email = data.get('email')
            password = data.get('password')
            
            session = self.db_session
            # Get user by email
            user = session.query(UserLocation).filter_by(
                email=email,
                is_active=True
            ).first()

            if not user:
                raise UnauthorizedException('Invalid email or password')

            # Verify password
            if not self.verify_password(password, user.password):
                raise UnauthorizedException('Invalid email or password')

            # Generate JWT auth and refresh tokens
            tokens = self.generate_jwt_tokens(user.id, user.organization_id, email)

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 60 minutes in seconds
                'user': {
                    'id': user.id,
                    'email': email,
                    'displayName': user.display_name,
                    'organizationId': user.organization_id
                }
            }

        except UnauthorizedException:
            # Re-raise authentication errors directly
            raise
        except Exception as e:
            raise APIException(str(e))

    def integration_login(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Login for integration with long-lived token (7 days) using email and password. Uses user.secret as JWT secret."""
        try:
            email = data.get('email')
            password = data.get('password')

            if not email or not password:
                raise ValidationException('Email and password are required')

            session = self.db_session
            # Get user by email
            user = session.query(UserLocation).filter_by(
                email=email,
                is_active=True
            ).first()

            if not user:
                raise UnauthorizedException('Invalid email or password')

            # Verify password
            if not user.password or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
                raise UnauthorizedException('Invalid email or password')

            # Check if user has a secret key set, generate one if not
            if not user.secret:
                # Auto-generate secret key on first integration login
                user.secret = self.generate_secret_key()
                session.commit()

            # Generate integration token (7 days expiry with 'integration' tag)
            # Use user.secret as the JWT secret instead of global jwt_secret
            now = datetime.now(timezone.utc)
            integration_payload = {
                'user_id': user.id,
                'organization_id': user.organization_id,
                'email': email,
                'type': 'integration',  # Tag as integration
                'exp': now + timedelta(days=7),
                'iat': now
            }

            integration_token = jwt.encode(integration_payload, user.secret, algorithm='HS256')

            # Save token to integration_tokens table
            token_record = IntegrationToken(
                user_id=user.id,
                jwt=integration_token,
                description=f"Integration token for {email}",
                valid=True
            )
            session.add(token_record)
            session.commit()

            return {
                'success': True,
                'token': integration_token,
                'token_type': 'Bearer',
                'expires_in': 604800,  # 7 days in seconds
                'user': {
                    'id': user.id,
                    'email': email,
                    'displayName': user.display_name,
                    'organizationId': user.organization_id
                }
            }

        except Exception as e:
            raise APIException(str(e))

    def generate_integration_secret(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Generate or regenerate integration secret key for authenticated user"""
        try:
            # Get user from token
            headers = kwargs.get('headers', {})
            auth_header = headers.get('Authorization') or headers.get('authorization')

            if not auth_header or not auth_header.startswith("Bearer "):
                raise UnauthorizedException('Authorization header with Bearer token is required')

            token = auth_header.split(" ")[1]
            payload = self.verify_jwt_token(token)

            if not payload:
                raise UnauthorizedException('Invalid or expired token')

            session = self.db_session
            user = session.query(UserLocation).filter_by(
                id=payload['user_id'],
                is_active=True
            ).first()

            if not user:
                raise NotFoundException('User not found')

            # Generate new secret key
            new_secret = self.generate_secret_key()
            user.secret = new_secret
            session.commit()

            return {
                'success': True,
                'message': 'Integration secret key generated successfully',
                'secret': new_secret,
                'user': {
                    'id': user.id,
                    'email': user.email
                }
            }

        except Exception as e:
            raise APIException(str(e))

    def validate_token(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Validate JWT token from request body"""
        try:
            token = data.get('token')

            if not token:
                raise ValidationException('Token is required')

            return self._validate_token_internal(token)

        except Exception as e:
            raise APIException(str(e))

    def validate_token_header(self, **kwargs) -> Dict[str, Any]:
        """Validate JWT token from Authorization header"""
        try:
            # Extract token from Authorization header passed in kwargs
            headers = kwargs.get('headers', {})
            auth_header = headers.get('Authorization') or headers.get('authorization')
            
            if not auth_header or not auth_header.startswith("Bearer "):
                raise UnauthorizedException('Authorization header with Bearer token is required')
            
            token = auth_header.split(" ")[1]
            return self._validate_token_internal(token)

        except Exception as e:
            raise APIException(str(e))

    def _validate_token_internal(self, token: str) -> Dict[str, Any]:
        """Internal method to validate token using SQLAlchemy"""
        # Verify token
        payload = self.verify_jwt_token(token)
        
        if not payload:
            raise UnauthorizedException('Invalid or expired token')
        
        try:
            session = self.db_session
            # Get user details
            user = session.query(UserLocation).filter_by(
                id=payload['user_id'],
                is_active=True
            ).first()

            if not user:
                raise NotFoundException('User not found')

            return {
                'success': True,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'displayName': user.display_name,
                    'organizationId': user.organization_id
                }
            }

        except Exception as e:
            raise APIException(str(e))

    def refresh_token(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Refresh JWT access token using refresh token"""
        try:
            refresh_token = data.get('refresh_token')
            
            if not refresh_token:
                raise ValidationException('Refresh token is required')
            
            # Verify refresh token
            payload = self.verify_jwt_token(refresh_token)
            
            if not payload:
                raise UnauthorizedException('Invalid or expired refresh token')
            
            # Check if it's a refresh token
            if payload.get('type') != 'refresh':
                raise UnauthorizedException('Invalid token type')
            
            # Verify user still exists and is active
            session = self.db_session
            user = session.query(UserLocation).filter_by(
                id=payload['user_id'],
                is_active=True
            ).first()

            if not user:
                raise NotFoundException('User not found')

            # Generate new auth and refresh tokens
            tokens = self.generate_jwt_tokens(user.id, user.organization_id, user.email)

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 900  # 15 minutes in seconds
            }

        except Exception as e:
            raise APIException(str(e))

    def get_profile(self, **kwargs) -> Dict[str, Any]:
        """Get user profile"""
        # TODO: Implement get profile logic
        raise APIException('Get profile endpoint not implemented')

    def update_profile(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Update user profile"""
        # TODO: Implement update profile logic
        raise APIException('Update profile endpoint not implemented')

    def change_password(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Change user password"""
        # TODO: Implement change password logic
        raise APIException('Change password endpoint not implemented')

    def logout(self, **kwargs) -> Dict[str, Any]:
        """Logout user"""
        # TODO: Implement logout logic (invalidate token)
        raise APIException('Logout endpoint not implemented')

    def check_email_exists(self, email: str) -> Dict[str, Any]:
        """Check if an email already exists in user_locations table"""
        try:
            if not email:
                return {
                    'success': True,
                    'exists': False,
                    'valid': False,
                    'message': 'Email is required'
                }
            
            # Basic email format validation
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                return {
                    'success': True,
                    'exists': False,
                    'valid': False,
                    'message': 'Invalid email format'
                }
            
            session = self.db_session
            # Check if email already exists
            existing_user = session.query(UserLocation).filter_by(email=email).first()
            
            if existing_user:
                return {
                    'success': True,
                    'exists': True,
                    'valid': False,
                    'message': 'Email already registered'
                }
            
            return {
                'success': True,
                'exists': False,
                'valid': True,
                'message': 'Email is available'
            }
            
        except Exception as e:
            return {
                'success': False,
                'exists': False,
                'valid': False,
                'message': str(e)
            }

    def login_iot_user(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Login user with QRCode d obj of username and password using SQLAlchemy"""
        try:
            payload = jwt.decode(data["login_token"], self.jwt_secret, algorithms=['HS256'])
            if payload is None:
                raise BadRequestException("Invalid login token")
            email = payload.get('email')
            password = payload.get('password')
            expired_date_value = payload.get("expired_date")
            expired_date_value = datetime.fromisoformat(expired_date_value.replace("Z", "+00:00"))
            if expired_date_value is None:
                raise BadRequestException("Invalid login token")
            if datetime.now(timezone.utc) > expired_date_value:
                raise UnauthorizedException("Expired login token")

            session = self.db_session
            # Get user by email
            user = session.query(UserLocation).filter_by(
                email=email,
                is_active=True
            ).first()

            if not user:
                raise NotFoundException('User not found')

            # Verify password
            if not self.verify_password(password, user.password):
                raise UnauthorizedException('Invalid email or password')

            # Generate JWT auth and refresh tokens
            tokens = self.generate_jwt_tokens(user.id, user.organization_id, email)

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 900,  # 15 minutes in seconds
                'user': {
                    'id': user.id,
                    'email': email,
                    'displayName': user.display_name,
                    'organizationId': user.organization_id
                }
            }

        except Exception as e:
            raise APIException(str(e))

    def login_iot_device(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Login an IoT device using device_name or MAC addresses and password"""
        try:
            device_name = data.get('device_name')
            mac_bt = data.get('mac_address_bluetooth')
            mac_tablet = data.get('mac_address_tablet')
            password = data.get('password')

            if not password or not (device_name or mac_bt or mac_tablet):
                raise ValidationException('Provide password and one of device_name, mac_address_bluetooth, mac_address_tablet')

            session = self.db_session

            # Build base query
            query = session.query(IoTDevice).filter(IoTDevice.is_active == True)

            # Apply identifier filters (priority: device_name, mac bt, mac tablet)
            if device_name:
                query = query.filter(IoTDevice.device_name == device_name)
            elif mac_bt:
                query = query.filter(IoTDevice.mac_address_bluetooth == mac_bt)
            else:
                query = query.filter(IoTDevice.mac_address_tablet == mac_tablet)

            device = query.first()

            if not device:
                raise UnauthorizedException('Invalid device credentials')

            try:
                if not device.password or not self.verify_password(password, device.password):
                    raise UnauthorizedException('Invalid device credentials')
            except Exception:
                raise UnauthorizedException('Invalid device credentials')

            tokens = self.generate_device_tokens(device.id, device.device_name)

            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 900,
                'device': {
                    'id': device.id,
                    'device_name': device.device_name,
                    'device_type': device.device_type,
                    'organization_id': device.organization_id
                }
            }

        except Exception as e:
            raise APIException(str(e))
                