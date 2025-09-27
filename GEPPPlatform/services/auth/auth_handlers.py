"""
Authentication handlers for the auth module
"""

import os
import jwt
import bcrypt
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# SQLAlchemy imports
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Database imports
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.subscriptions.organizations import Organization, OrganizationInfo
from GEPPPlatform.models.subscriptions.subscription_models import SubscriptionPlan, Subscription
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

    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
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