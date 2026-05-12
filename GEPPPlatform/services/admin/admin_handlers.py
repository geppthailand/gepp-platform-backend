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
from . import crm as _crm  # noqa: F401  (sub-route dispatcher)
from .crm import crm_handlers as crm
from .crm import brand_assets as crm_brand
from .crm import lead_handlers as crm_leads
from .crm import drip_handlers as crm_drip
from .crm import inbox_handlers as crm_inbox


def _list_crm_brand_assets(db_session, query_params, current_user):
    """
    GET /admin/crm-brand-assets — returns the resolved (platform default + per-org override)
    brand context as a list of {key, platformDefault, orgOverride, resolvedValue, isOverridden}.

    Scope: super-admin/gepp-admin can specify ?organizationId=X; otherwise the caller's own org.
    """
    admin_role = (current_user or {}).get('admin_role') or ''
    org_id = None
    if admin_role in ('super-admin', 'gepp-admin'):
        raw = query_params.get('organizationId')
        if raw:
            try:
                org_id = int(raw)
            except (TypeError, ValueError):
                org_id = None
    else:
        org_id = (current_user or {}).get('organization_id')

    items = crm_brand.list_brand_assets(db_session, org_id)
    return {"items": items, "total": len(items), "page": 1, "pageSize": len(items)}


class AdminHandlers:

    def __init__(self, db_session: Session, current_user: dict = None):
        self.db_session = db_session
        self.current_user = current_user or {}
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
            # CRM / Marketing module
            'crm-segments': lambda qp: crm.list_crm_segments(self.db_session, qp),
            'crm-templates': lambda qp: crm.list_crm_templates(self.db_session, qp),
            'crm-campaigns': lambda qp: crm.list_crm_campaigns(self.db_session, qp),
            'crm-email-lists': lambda qp: crm.list_crm_email_lists(self.db_session, qp, current_user=self.current_user),
            'crm-user-profiles': lambda qp: crm.list_crm_user_profiles(self.db_session, qp),
            'crm-org-profiles': lambda qp: crm.list_crm_org_profiles(self.db_session, qp),
            'crm-deliveries': lambda qp: crm.list_crm_deliveries(self.db_session, qp),
            'crm-unsubscribes': lambda qp: crm.list_crm_unsubscribes(self.db_session, qp),
            'crm-analytics': lambda qp: crm.list_crm_analytics(self.db_session, qp),
            'crm-brand-assets': lambda qp: _list_crm_brand_assets(self.db_session, qp, self.current_user),
            'crm-leads': lambda qp: crm_leads.list_crm_leads(self.db_session, qp),
            'crm-drip-sequences': lambda qp: crm_drip.list_crm_drip_sequences(self.db_session, qp, current_user=self.current_user),
            'crm-conversations': lambda qp: crm_inbox.list_crm_conversations(self.db_session, qp, current_user=self.current_user),
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(query_params)

    def get_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        handler_map = {
            'organizations': self.admin_service.get_organization,
            'users': self.admin_service.get_user,
            'subscription-plans': self.admin_service.get_subscription_plan,
            'system-permissions': self.admin_service.get_system_permission,
            'iot-devices': self.admin_service.get_iot_device,
            'iot-scales': self.admin_service.get_iot_scale,
            # CRM / Marketing
            'crm-segments': lambda rid: crm.get_crm_segment(self.db_session, rid),
            'crm-templates': lambda rid: crm.get_crm_template(self.db_session, rid),
            'crm-campaigns': lambda rid: crm.get_crm_campaign(self.db_session, rid),
            'crm-email-lists': lambda rid: crm.get_crm_email_list(self.db_session, rid, current_user=self.current_user),
            'crm-leads': lambda rid: crm_leads.get_crm_lead(self.db_session, rid, current_user=self.current_user),
            'crm-drip-sequences': lambda rid: crm_drip.get_crm_drip_sequence(self.db_session, rid, current_user=self.current_user),
            'crm-conversations': lambda rid: crm_inbox.get_crm_conversation(self.db_session, rid, current_user=self.current_user),
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
            # CRM / Marketing
            'crm-segments': lambda d: crm.create_crm_segment(self.db_session, d),
            'crm-templates': lambda d: crm.create_crm_template(self.db_session, d),
            'crm-campaigns': lambda d: crm.create_crm_campaign(self.db_session, d),
            'crm-email-lists': lambda d: crm.create_crm_email_list(self.db_session, d, current_user=self.current_user),
            'crm-leads': lambda d: crm_leads.create_crm_lead(self.db_session, d, current_user=self.current_user),
            'crm-drip-sequences': lambda d: crm_drip.create_crm_drip_sequence(self.db_session, d, current_user=self.current_user),
        }
        handler = handler_map.get(resource)
        if not handler:
            raise NotFoundException(f'Resource {resource} not found')
        return handler(data)

    def update_resource(self, resource: str, resource_id: int, data: dict) -> Dict[str, Any]:
        handler_map = {
            'organizations': self.admin_service.update_organization,
            'users': self.admin_service.change_user_password,
            'subscription-plans': self.admin_service.update_subscription_plan,
            'subscriptions': self.admin_service.update_subscription,
            'system-permissions': self.admin_service.update_system_permission,
            'iot-devices': self.admin_service.update_iot_device,
            'iot-scales': self.admin_service.update_iot_scale,
            # CRM / Marketing
            'crm-segments': lambda rid, d: crm.update_crm_segment(self.db_session, rid, d),
            'crm-templates': lambda rid, d: crm.update_crm_template(self.db_session, rid, d),
            'crm-campaigns': lambda rid, d: crm.update_crm_campaign(self.db_session, rid, d),
            'crm-email-lists': lambda rid, d: crm.update_crm_email_list(self.db_session, rid, d, current_user=self.current_user),
            'crm-leads': lambda rid, d: crm_leads.update_crm_lead(self.db_session, rid, d, current_user=self.current_user),
            'crm-drip-sequences': lambda rid, d: crm_drip.update_crm_drip_sequence(self.db_session, rid, d, current_user=self.current_user),
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
            # CRM / Marketing
            'crm-segments': lambda rid: crm.delete_crm_segment(self.db_session, rid),
            'crm-templates': lambda rid: crm.delete_crm_template(self.db_session, rid),
            'crm-campaigns': lambda rid: crm.delete_crm_campaign(self.db_session, rid),
            'crm-email-lists': lambda rid: crm.delete_crm_email_list(self.db_session, rid, current_user=self.current_user),
            'crm-leads': lambda rid: crm_leads.delete_crm_lead(self.db_session, rid, current_user=self.current_user),
            'crm-drip-sequences': lambda rid: crm_drip.delete_crm_drip_sequence(self.db_session, rid, current_user=self.current_user),
            'crm-conversations': lambda rid: crm_inbox.delete_crm_conversation(self.db_session, rid, current_user=self.current_user),
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
