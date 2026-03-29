"""
Admin handlers for backoffice administration endpoints
"""

import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session

from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.exceptions import (
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
)
from .admin_service import AdminService


class AdminHandlers:

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.admin_service = AdminService(db_session)
        self.jwt_secret = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-here')

    # ── Authentication ─────────────────────────────────────────────────

    def admin_login(self, data: dict) -> Dict[str, Any]:
        """Authenticate an admin user and return JWT tokens"""
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            raise BadRequestException('Email and password are required')

        # Find user by email
        user = (
            self.db_session.query(UserLocation)
            .filter(
                UserLocation.email == email,
                UserLocation.is_user == True,
                UserLocation.is_active == True,
            )
            .first()
        )

        if not user:
            raise UnauthorizedException('Invalid credentials or not an admin user')

        # Verify password
        if not user.password or not bcrypt.checkpw(
            password.encode('utf-8'), user.password.encode('utf-8')
        ):
            raise UnauthorizedException('Invalid credentials or not an admin user')

        # Check admin role
        if user.platform_role not in ('super-admin', 'gepp-admin'):
            raise UnauthorizedException('Invalid credentials or not an admin user')

        # Generate JWT tokens with admin_role claim
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=1)

        auth_payload = {
            'user_id': user.id,
            'organization_id': user.organization_id,
            'email': user.email,
            'admin_role': user.platform_role,
            'type': 'auth',
            'exp': expiry,
            'iat': now,
        }
        refresh_payload = {
            'user_id': user.id,
            'organization_id': user.organization_id,
            'email': user.email,
            'admin_role': user.platform_role,
            'type': 'refresh',
            'exp': now + timedelta(days=7),
            'iat': now,
        }

        auth_token = jwt.encode(auth_payload, self.jwt_secret, algorithm='HS256')
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm='HS256')

        return {
            'token': auth_token,
            'tokenExpiry': expiry.isoformat(),
            'auth_token': auth_token,
            'refresh_token': refresh_token,
            'role': {'id': 1},
            'username': user.display_name or user.email,
            'email': user.email,
            'adminRole': user.platform_role,
            'id': user.id,
            'organizationId': user.organization_id,
        }

    # ── Resource CRUD Dispatch ─────────────────────────────────────────

    def list_resource(self, resource: str, query_params: dict) -> Dict[str, Any]:
        handler_map = {
            'organizations': self.admin_service.list_organizations,
            'users': self.admin_service.list_all_users,
            'locations': self.admin_service.list_all_locations,
            'subscription-plans': self.admin_service.list_subscription_plans,
            'subscriptions': self.admin_service.list_subscriptions,
            'system-permissions': self.admin_service.list_system_permissions,
            'iot-devices': self.admin_service.list_iot_devices,
            'iot-scales': self.admin_service.list_iot_scales,
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(query_params)

    def get_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        handler_map = {
            'organizations': self.admin_service.get_organization,
            'subscription-plans': self.admin_service.get_subscription_plan,
            'system-permissions': self.admin_service.get_system_permission,
            'iot-devices': self.admin_service.get_iot_device,
            'iot-scales': self.admin_service.get_iot_scale,
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(resource_id)

    def create_resource(self, resource: str, data: dict) -> Dict[str, Any]:
        handler_map = {
            'subscription-plans': self.admin_service.create_subscription_plan,
            'subscriptions': self.admin_service.create_subscription,
            'system-permissions': self.admin_service.create_system_permission,
            'iot-devices': self.admin_service.create_iot_device,
            'iot-scales': self.admin_service.create_iot_scale,
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(data)

    def update_resource(self, resource: str, resource_id: int, data: dict) -> Dict[str, Any]:
        handler_map = {
            'organizations': self.admin_service.update_organization,
            'subscription-plans': self.admin_service.update_subscription_plan,
            'subscriptions': self.admin_service.update_subscription,
            'system-permissions': self.admin_service.update_system_permission,
            'iot-devices': self.admin_service.update_iot_device,
            'iot-scales': self.admin_service.update_iot_scale,
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(resource_id, data)

    def delete_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        handler_map = {
            'subscription-plans': self.admin_service.delete_subscription_plan,
            'subscriptions': self.admin_service.delete_subscription,
            'system-permissions': self.admin_service.delete_system_permission,
            'iot-devices': self.admin_service.delete_iot_device,
            'iot-scales': self.admin_service.delete_iot_scale,
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(resource_id)

    def list_sub_resource(self, resource: str, resource_id: int, sub_resource: str, query_params: dict) -> Dict[str, Any]:
        if resource == 'organizations':
            if sub_resource == 'users':
                return self.admin_service.list_organization_users(resource_id, query_params)
            elif sub_resource == 'locations':
                return self.admin_service.list_organization_locations(resource_id, query_params)
        raise NotFoundException(f'Sub-resource {resource}/{sub_resource} not found')

    def assign_permissions(self, resource: str, resource_id: int, data: dict) -> Dict[str, Any]:
        if resource == 'subscription-plans':
            return self.admin_service.toggle_plan_permission(resource_id, data)
        raise NotFoundException(f'Permission assignment not supported for {resource}')

    def batch_permissions(self, plan_id: int, data: dict) -> Dict[str, Any]:
        return self.admin_service.batch_toggle_permissions(plan_id, data)

    def remove_permission(self, subscription_id: int, perm_id: int) -> Dict[str, Any]:
        return self.admin_service.remove_permission_from_subscription(subscription_id, perm_id)
