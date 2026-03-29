"""
Admin service for backoffice business logic
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
import bcrypt

from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.subscriptions.organizations import Organization, OrganizationInfo
from GEPPPlatform.models.subscriptions.subscription_models import (
    SubscriptionPlan,
    Subscription,
    OrganizationRole,
    OrganizationPermission,
)
from GEPPPlatform.models.cores.roles import SystemPermission, subscription_permissions
from GEPPPlatform.models.cores.iot_devices import IoTDevice
from GEPPPlatform.models.cores.iot_scales import IoTScale
from GEPPPlatform.exceptions import NotFoundException, BadRequestException, ValidationException


class AdminService:

    def __init__(self, db_session: Session):
        self.db_session = db_session

    # ── Organizations ──────────────────────────────────────────────────

    def list_organizations(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        search = query_params.get('search', '').strip()
        filter_name = query_params.get('name', '').strip()
        filter_owner_email = query_params.get('ownerEmail', '').strip()

        query = (
            self.db_session.query(Organization)
            .options(
                joinedload(Organization.organization_info),
                joinedload(Organization.owner),
            )
            .filter(Organization.is_active == True)
        )

        if search:
            query = query.join(Organization.organization_info).filter(
                or_(
                    OrganizationInfo.company_name.ilike(f'%{search}%'),
                    OrganizationInfo.company_email.ilike(f'%{search}%'),
                )
            )

        if filter_name:
            query = query.outerjoin(Organization.organization_info).filter(
                or_(
                    OrganizationInfo.company_name.ilike(f'%{filter_name}%'),
                    Organization.name.ilike(f'%{filter_name}%'),
                )
            )

        if filter_owner_email:
            query = query.join(Organization.owner).filter(
                UserLocation.email.ilike(f'%{filter_owner_email}%')
            )

        total = query.count()
        orgs = query.offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for org in orgs:
            users_count = (
                self.db_session.query(func.count(UserLocation.id))
                .filter(
                    UserLocation.organization_id == org.id,
                    UserLocation.is_user == True,
                    UserLocation.is_active == True,
                )
                .scalar()
            )
            locations_count = (
                self.db_session.query(func.count(UserLocation.id))
                .filter(
                    UserLocation.organization_id == org.id,
                    UserLocation.is_location == True,
                    UserLocation.is_active == True,
                )
                .scalar()
            )
            info = org.organization_info
            results.append({
                'id': org.id,
                'name': info.company_name if info else org.name,
                'displayName': info.display_name if info else None,
                'ownerEmail': org.owner.email if org.owner else None,
                'ownerName': org.owner.display_name if org.owner else None,
                'subscriptionId': org.subscription_id,
                'usersCount': users_count,
                'locationsCount': locations_count,
                'isActive': org.is_active,
                'createdDate': org.created_date.isoformat() if org.created_date else None,
            })

        return {
            'items': results,
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    def get_organization(self, org_id: int) -> Dict[str, Any]:
        org = (
            self.db_session.query(Organization)
            .options(
                joinedload(Organization.organization_info),
                joinedload(Organization.owner),
                joinedload(Organization.subscriptions).joinedload(Subscription.plan),
            )
            .filter(Organization.id == org_id, Organization.is_active == True)
            .first()
        )
        if not org:
            raise NotFoundException(f'Organization {org_id} not found')

        info = org.organization_info
        return {
            'id': org.id,
            'name': info.company_name if info else org.name,
            'displayName': info.display_name if info else None,
            'description': org.description,
            'ownerEmail': org.owner.email if org.owner else None,
            'ownerName': org.owner.display_name if org.owner else None,
            'organizationInfo': {
                'companyName': info.company_name,
                'companyNameTh': info.company_name_th,
                'companyNameEn': info.company_name_en,
                'businessType': info.business_type,
                'businessIndustry': info.business_industry,
                'taxId': info.tax_id,
                'companyEmail': info.company_email,
                'phoneNumber': info.phone_number,
                'address': info.address,
            } if info else None,
            'subscriptions': [
                {
                    'id': sub.id,
                    'planName': sub.plan.display_name if sub.plan else sub.plan_id,
                    'status': sub.status,
                    'currentPeriodEndsAt': sub.current_period_ends_at,
                }
                for sub in (org.subscriptions or [])
            ],
            'allowAiAudit': org.allow_ai_audit,
            'maxOrgStructureNodes': org.max_org_structure_nodes if hasattr(org, 'max_org_structure_nodes') else 50,
            'isActive': org.is_active,
            'createdDate': org.created_date.isoformat() if org.created_date else None,
        }

    def update_organization(self, org_id: int, data: dict) -> Dict[str, Any]:
        org = self.db_session.query(Organization).filter(
            Organization.id == org_id, Organization.is_active == True
        ).first()
        if not org:
            raise NotFoundException(f'Organization {org_id} not found')

        if 'name' in data:
            org.name = data['name']
        if 'description' in data:
            org.description = data['description']
        if 'allowAiAudit' in data:
            org.allow_ai_audit = data['allowAiAudit']
        if 'maxOrgStructureNodes' in data:
            org.max_org_structure_nodes = int(data['maxOrgStructureNodes'])

        self.db_session.flush()
        return {'id': org.id, 'message': 'Organization updated'}

    def list_organization_users(self, org_id: int, query_params: dict) -> Dict[str, Any]:
        return self._list_user_locations(org_id, is_user=True, query_params=query_params)

    def list_organization_locations(self, org_id: int, query_params: dict) -> Dict[str, Any]:
        return self._list_user_locations(org_id, is_location=True, query_params=query_params)

    def _list_user_locations(self, org_id: int, is_user: bool = False, is_location: bool = False, query_params: dict = None) -> Dict[str, Any]:
        query_params = query_params or {}
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        search = query_params.get('search', '').strip()

        query = (
            self.db_session.query(UserLocation)
            .filter(
                UserLocation.organization_id == org_id,
                UserLocation.is_active == True,
            )
        )
        if is_user:
            query = query.filter(UserLocation.is_user == True)
        if is_location:
            query = query.filter(UserLocation.is_location == True)

        if search:
            query = query.filter(
                or_(
                    UserLocation.email.ilike(f'%{search}%'),
                    UserLocation.display_name.ilike(f'%{search}%'),
                    UserLocation.name_en.ilike(f'%{search}%'),
                )
            )

        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for ul in items:
            results.append({
                'id': ul.id,
                'email': ul.email,
                'displayName': ul.display_name,
                'nameEn': ul.name_en,
                'nameTh': ul.name_th,
                'phone': ul.phone,
                'isUser': ul.is_user,
                'isLocation': ul.is_location,
                'platform': ul.platform.value if ul.platform else None,
                'platformRole': ul.platform_role,
                'organizationRoleId': ul.organization_role_id,
                'isActive': ul.is_active,
                'createdDate': ul.created_date.isoformat() if ul.created_date else None,
            })

        return {
            'items': results,
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    # ── Users (all organizations) ─────────────────────────────────────

    def list_all_users(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        filter_first_name = query_params.get('firstName', '').strip()
        filter_last_name = query_params.get('lastName', '').strip()
        filter_email = query_params.get('email', '').strip()
        search = query_params.get('search', '').strip()

        query = (
            self.db_session.query(UserLocation)
            .filter(
                UserLocation.is_user == True,
                UserLocation.is_active == True,
            )
        )

        if search:
            query = query.filter(
                or_(
                    UserLocation.email.ilike(f'%{search}%'),
                    UserLocation.first_name.ilike(f'%{search}%'),
                    UserLocation.last_name.ilike(f'%{search}%'),
                    UserLocation.display_name.ilike(f'%{search}%'),
                )
            )

        if filter_first_name:
            query = query.filter(UserLocation.first_name.ilike(f'%{filter_first_name}%'))
        if filter_last_name:
            query = query.filter(UserLocation.last_name.ilike(f'%{filter_last_name}%'))
        if filter_email:
            query = query.filter(UserLocation.email.ilike(f'%{filter_email}%'))

        total = query.count()
        items = query.order_by(UserLocation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for ul in items:
            # Get owner email from organization
            owner_email = None
            if ul.organization_id:
                org = self.db_session.query(Organization).options(
                    joinedload(Organization.owner)
                ).filter(Organization.id == ul.organization_id).first()
                if org and org.owner:
                    owner_email = org.owner.email

            results.append({
                'id': ul.id,
                'firstName': ul.first_name,
                'lastName': ul.last_name,
                'email': ul.email,
                'phone': ul.phone,
                'displayName': ul.display_name,
                'organizationId': ul.organization_id,
                'ownerEmail': owner_email,
                'platform': ul.platform.value if ul.platform else None,
                'platformRole': ul.platform_role,
                'isActive': ul.is_active,
                'createdDate': ul.created_date.isoformat() if ul.created_date else None,
            })

        return {
            'items': results,
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    # ── Locations (all organizations) ──────────────────────────────────

    def list_all_locations(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        filter_name = query_params.get('name', '').strip()
        filter_email = query_params.get('email', '').strip()
        search = query_params.get('search', '').strip()

        query = (
            self.db_session.query(UserLocation)
            .filter(
                UserLocation.is_location == True,
                UserLocation.is_active == True,
            )
        )

        if search:
            query = query.filter(
                or_(
                    UserLocation.name_en.ilike(f'%{search}%'),
                    UserLocation.name_th.ilike(f'%{search}%'),
                    UserLocation.display_name.ilike(f'%{search}%'),
                    UserLocation.email.ilike(f'%{search}%'),
                )
            )

        if filter_name:
            query = query.filter(
                or_(
                    UserLocation.name_en.ilike(f'%{filter_name}%'),
                    UserLocation.name_th.ilike(f'%{filter_name}%'),
                    UserLocation.display_name.ilike(f'%{filter_name}%'),
                )
            )
        if filter_email:
            query = query.filter(UserLocation.email.ilike(f'%{filter_email}%'))

        total = query.count()
        items = query.order_by(UserLocation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for ul in items:
            results.append({
                'id': ul.id,
                'nameEn': ul.name_en,
                'nameTh': ul.name_th,
                'displayName': ul.display_name,
                'email': ul.email,
                'phone': ul.phone,
                'type': ul.type,
                'hubType': ul.hub_type,
                'functions': ul.functions,
                'organizationId': ul.organization_id,
                'address': ul.address,
                'isActive': ul.is_active,
                'createdDate': ul.created_date.isoformat() if ul.created_date else None,
            })

        return {
            'items': results,
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    # ── Subscription Plans ─────────────────────────────────────────────

    def list_subscription_plans(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))

        query = self.db_session.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True)
        total = query.count()
        plans = query.offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for plan in plans:
            results.append({
                'id': plan.id,
                'name': plan.name,
                'displayName': plan.display_name,
                'description': plan.description,
                'priceMonthly': plan.price_monthly,
                'priceYearly': plan.price_yearly,
                'maxUsers': plan.max_users,
                'maxTransactionsMonthly': plan.max_transactions_monthly,
                'maxStorageGb': plan.max_storage_gb,
                'maxApiCallsDaily': plan.max_api_calls_daily,
                'features': plan.features,
                'createdDate': plan.created_date.isoformat() if plan.created_date else None,
            })

        return {'items': results, 'total': total, 'page': page, 'pageSize': page_size}

    def get_subscription_plan(self, plan_id: int) -> Dict[str, Any]:
        plan = (
            self.db_session.query(SubscriptionPlan)
            .filter(SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True)
            .first()
        )
        if not plan:
            raise NotFoundException(f'Subscription plan {plan_id} not found')

        # Get ALL active system permissions
        all_permissions = (
            self.db_session.query(SystemPermission)
            .filter(SystemPermission.is_active == True)
            .order_by(SystemPermission.category, SystemPermission.code)
            .all()
        )

        assigned_ids = set(plan.permission_ids or [])

        return {
            'id': plan.id,
            'name': plan.name,
            'displayName': plan.display_name,
            'description': plan.description,
            'priceMonthly': plan.price_monthly,
            'priceYearly': plan.price_yearly,
            'maxUsers': plan.max_users,
            'maxTransactionsMonthly': plan.max_transactions_monthly,
            'maxStorageGb': plan.max_storage_gb,
            'maxApiCallsDaily': plan.max_api_calls_daily,
            'features': plan.features,
            'permissions': [
                {'id': p.id, 'code': p.code, 'name': p.name, 'category': p.category}
                for p in all_permissions if p.id in assigned_ids
            ],
            'allPermissions': [
                {
                    'id': p.id,
                    'code': p.code,
                    'name': p.name,
                    'description': p.description,
                    'category': p.category,
                    'enabled': p.id in assigned_ids,
                }
                for p in all_permissions
            ],
        }

    def create_subscription_plan(self, data: dict) -> Dict[str, Any]:
        plan = SubscriptionPlan(
            name=data.get('name'),
            display_name=data.get('displayName'),
            description=data.get('description'),
            price_monthly=data.get('priceMonthly', 0),
            price_yearly=data.get('priceYearly', 0),
            max_users=data.get('maxUsers', 1),
            max_transactions_monthly=data.get('maxTransactionsMonthly', 100),
            max_storage_gb=data.get('maxStorageGb', 1),
            max_api_calls_daily=data.get('maxApiCallsDaily', 1000),
            features=data.get('features'),
        )
        self.db_session.add(plan)
        self.db_session.flush()
        return {'id': plan.id, 'message': 'Subscription plan created'}

    def update_subscription_plan(self, plan_id: int, data: dict) -> Dict[str, Any]:
        plan = self.db_session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True
        ).first()
        if not plan:
            raise NotFoundException(f'Subscription plan {plan_id} not found')

        # name is immutable — only display_name and other fields can be changed
        for field in ['display_name', 'description', 'price_monthly', 'price_yearly',
                      'max_users', 'max_transactions_monthly', 'max_storage_gb', 'max_api_calls_daily', 'features']:
            camel = self._to_camel(field)
            if camel in data:
                setattr(plan, field, data[camel])

        self.db_session.flush()
        return {'id': plan.id, 'message': 'Subscription plan updated'}

    def _create_plan_version(self, old_plan: 'SubscriptionPlan', new_permission_ids: list) -> 'SubscriptionPlan':
        """Create a new plan version with updated permissions, deactivate the old one, and migrate subscriptions."""
        new_plan = SubscriptionPlan(
            name=old_plan.name,
            display_name=old_plan.display_name,
            description=old_plan.description,
            price_monthly=old_plan.price_monthly,
            price_yearly=old_plan.price_yearly,
            max_users=old_plan.max_users,
            max_transactions_monthly=old_plan.max_transactions_monthly,
            max_storage_gb=old_plan.max_storage_gb,
            max_api_calls_daily=old_plan.max_api_calls_daily,
            features=old_plan.features,
            permission_ids=new_permission_ids,
        )
        self.db_session.add(new_plan)

        # Deactivate old plan
        old_plan.is_active = False
        self.db_session.flush()

        # Migrate active subscriptions to the new plan version
        self.db_session.query(Subscription).filter(
            Subscription.plan_id == old_plan.id,
            Subscription.status == 'active',
            Subscription.is_active == True
        ).update({Subscription.plan_id: new_plan.id}, synchronize_session='fetch')
        self.db_session.flush()

        return new_plan

    def toggle_plan_permission(self, plan_id: int, data: dict) -> Dict[str, Any]:
        """Toggle a system permission — creates a new plan version for historical tracking"""
        plan = self.db_session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True
        ).first()
        if not plan:
            raise NotFoundException(f'Subscription plan {plan_id} not found')

        permission_id = data.get('permissionId')
        enabled = data.get('enabled', True)

        if not permission_id:
            raise BadRequestException('permissionId is required')

        # Verify permission exists
        perm = self.db_session.query(SystemPermission).filter(
            SystemPermission.id == permission_id, SystemPermission.is_active == True
        ).first()
        if not perm:
            raise NotFoundException(f'System permission {permission_id} not found')

        current_ids = list(plan.permission_ids or [])

        if enabled and permission_id not in current_ids:
            current_ids.append(permission_id)
        elif not enabled and permission_id in current_ids:
            current_ids.remove(permission_id)

        new_plan = self._create_plan_version(plan, current_ids)

        return {
            'message': f'Permission {perm.code} {"enabled" if enabled else "disabled"} for plan {new_plan.name}',
            'permissionId': permission_id,
            'enabled': enabled,
            'newPlanId': new_plan.id,
        }

    def batch_toggle_permissions(self, plan_id: int, data: dict) -> Dict[str, Any]:
        """Enable or disable all permissions (optionally filtered by category/subGroup) — creates a new plan version"""
        plan = self.db_session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True
        ).first()
        if not plan:
            raise NotFoundException(f'Subscription plan {plan_id} not found')

        action = data.get('action')  # 'enable_all' or 'disable_all'
        category = data.get('category')  # optional: filter by category
        sub_group = data.get('subGroup')  # optional: filter by sub-group (e.g. 'rewards')

        if action not in ('enable_all', 'disable_all'):
            raise BadRequestException('action must be "enable_all" or "disable_all"')

        # Get target permissions
        query = self.db_session.query(SystemPermission).filter(SystemPermission.is_active == True)
        if category:
            query = query.filter(SystemPermission.category == category)

        target_perms = query.all()

        # Further filter by sub-group code prefix if specified
        if sub_group:
            target_perms = [p for p in target_perms if p.code.split('.')[1] == sub_group if len(p.code.split('.')) >= 3]

        target_ids = {p.id for p in target_perms}
        current_ids = set(plan.permission_ids or [])

        if action == 'enable_all':
            new_ids = list(current_ids | target_ids)
        else:
            new_ids = list(current_ids - target_ids)

        new_plan = self._create_plan_version(plan, new_ids)

        return {
            'message': f'{action} completed for plan {new_plan.name}',
            'newPlanId': new_plan.id,
            'action': action,
        }

    def delete_subscription_plan(self, plan_id: int) -> Dict[str, Any]:
        plan = self.db_session.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id
        ).first()
        if not plan:
            raise NotFoundException(f'Subscription plan {plan_id} not found')
        plan.is_active = False
        self.db_session.flush()
        return {'id': plan.id, 'message': 'Subscription plan deleted'}

    # ── Subscriptions ──────────────────────────────────────────────────

    def list_subscriptions(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))

        query = (
            self.db_session.query(Subscription)
            .options(joinedload(Subscription.plan), joinedload(Subscription.organization))
            .filter(Subscription.is_active == True)
        )
        total = query.count()
        subs = query.offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for sub in subs:
            results.append({
                'id': sub.id,
                'organizationId': sub.organization_id,
                'organizationName': sub.organization.name if sub.organization else None,
                'planId': sub.plan_id,
                'planName': sub.plan.display_name if sub.plan else None,
                'status': sub.status,
                'usersCount': sub.users_count,
                'transactionsCountThisMonth': sub.transactions_count_this_month,
                'currentPeriodEndsAt': sub.current_period_ends_at,
                'createdDate': sub.created_date.isoformat() if sub.created_date else None,
            })

        return {'items': results, 'total': total, 'page': page, 'pageSize': page_size}

    def create_subscription(self, data: dict) -> Dict[str, Any]:
        sub = Subscription(
            organization_id=data.get('organizationId'),
            plan_id=data.get('planId'),
            status=data.get('status', 'active'),
            create_transaction_limit=data.get('createTransactionLimit', 100),
            ai_audit_limit=data.get('aiAuditLimit', 10),
        )
        self.db_session.add(sub)
        self.db_session.flush()
        return {'id': sub.id, 'message': 'Subscription created'}

    def update_subscription(self, sub_id: int, data: dict) -> Dict[str, Any]:
        sub = self.db_session.query(Subscription).filter(
            Subscription.id == sub_id, Subscription.is_active == True
        ).first()
        if not sub:
            raise NotFoundException(f'Subscription {sub_id} not found')

        for field in ['plan_id', 'status', 'create_transaction_limit', 'ai_audit_limit',
                      'allow_ai_audit_exceed_quota', 'duration_type']:
            camel = self._to_camel(field)
            if camel in data:
                setattr(sub, field, data[camel])

        self.db_session.flush()
        return {'id': sub.id, 'message': 'Subscription updated'}

    def delete_subscription(self, sub_id: int) -> Dict[str, Any]:
        sub = self.db_session.query(Subscription).filter(Subscription.id == sub_id).first()
        if not sub:
            raise NotFoundException(f'Subscription {sub_id} not found')
        sub.is_active = False
        self.db_session.flush()
        return {'id': sub.id, 'message': 'Subscription deleted'}

    # ── System Permissions ─────────────────────────────────────────────

    def list_system_permissions(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        category = query_params.get('category', '').strip()

        query = self.db_session.query(SystemPermission).filter(SystemPermission.is_active == True)
        if category:
            query = query.filter(SystemPermission.category == category)

        total = query.count()
        perms = query.order_by(SystemPermission.category, SystemPermission.code).offset((page - 1) * page_size).limit(page_size).all()

        results = []
        for p in perms:
            results.append({
                'id': p.id,
                'code': p.code,
                'name': p.name,
                'description': p.description,
                'category': p.category,
                'createdDate': p.created_date.isoformat() if p.created_date else None,
            })

        return {'items': results, 'total': total, 'page': page, 'pageSize': page_size}

    def get_system_permission(self, perm_id: int) -> Dict[str, Any]:
        perm = self.db_session.query(SystemPermission).filter(
            SystemPermission.id == perm_id, SystemPermission.is_active == True
        ).first()
        if not perm:
            raise NotFoundException(f'System permission {perm_id} not found')
        return {
            'id': perm.id,
            'code': perm.code,
            'name': perm.name,
            'description': perm.description,
            'category': perm.category,
            'createdDate': perm.created_date.isoformat() if perm.created_date else None,
        }

    def create_system_permission(self, data: dict) -> Dict[str, Any]:
        perm = SystemPermission(
            code=data.get('code'),
            name=data.get('name'),
            description=data.get('description'),
            category=data.get('category'),
        )
        self.db_session.add(perm)
        self.db_session.flush()
        return {'id': perm.id, 'message': 'System permission created'}

    def update_system_permission(self, perm_id: int, data: dict) -> Dict[str, Any]:
        perm = self.db_session.query(SystemPermission).filter(
            SystemPermission.id == perm_id, SystemPermission.is_active == True
        ).first()
        if not perm:
            raise NotFoundException(f'System permission {perm_id} not found')

        for field in ['code', 'name', 'description', 'category']:
            if field in data:
                setattr(perm, field, data[field])

        self.db_session.flush()
        return {'id': perm.id, 'message': 'System permission updated'}

    def delete_system_permission(self, perm_id: int) -> Dict[str, Any]:
        perm = self.db_session.query(SystemPermission).filter(SystemPermission.id == perm_id).first()
        if not perm:
            raise NotFoundException(f'System permission {perm_id} not found')
        perm.is_active = False
        self.db_session.flush()
        return {'id': perm.id, 'message': 'System permission deleted'}

    # ── Permission Assignment ──────────────────────────────────────────

    def assign_permissions_to_subscription(self, subscription_id: int, data: dict) -> Dict[str, Any]:
        """Assign system permissions to a subscription (via junction table)"""
        sub = self.db_session.query(Subscription).filter(
            Subscription.id == subscription_id, Subscription.is_active == True
        ).first()
        if not sub:
            raise NotFoundException(f'Subscription {subscription_id} not found')

        permission_ids = data.get('permissionIds', [])
        for pid in permission_ids:
            perm = self.db_session.query(SystemPermission).filter(SystemPermission.id == pid).first()
            if perm and perm not in sub.permissions:
                sub.permissions.append(perm)

        self.db_session.flush()
        return {'message': f'Assigned {len(permission_ids)} permissions to subscription {subscription_id}'}

    def remove_permission_from_subscription(self, subscription_id: int, perm_id: int) -> Dict[str, Any]:
        sub = self.db_session.query(Subscription).filter(
            Subscription.id == subscription_id, Subscription.is_active == True
        ).first()
        if not sub:
            raise NotFoundException(f'Subscription {subscription_id} not found')

        perm = self.db_session.query(SystemPermission).filter(SystemPermission.id == perm_id).first()
        if perm and perm in sub.permissions:
            sub.permissions.remove(perm)

        self.db_session.flush()
        return {'message': f'Removed permission {perm_id} from subscription {subscription_id}'}

    # ── IoT Devices ─────────────────────────────────────────────────

    ALLOWED_DEVICE_TYPES = ['scale', 'sensor', 'terminal', 'printer']

    def list_iot_devices(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        filter_name = query_params.get('deviceName', '').strip()
        filter_type = query_params.get('deviceType', '').strip()
        filter_org_id = query_params.get('organizationId', '').strip()
        filter_assigned = query_params.get('assigned', '').strip()

        query = self.db_session.query(IoTDevice).filter(IoTDevice.deleted_date.is_(None))

        if filter_name:
            query = query.filter(IoTDevice.device_name.ilike(f'%{filter_name}%'))
        if filter_type:
            query = query.filter(IoTDevice.device_type == filter_type)
        if filter_org_id:
            query = query.filter(IoTDevice.organization_id == int(filter_org_id))
        if filter_assigned == 'true':
            query = query.filter(IoTDevice.organization_id.isnot(None))
        elif filter_assigned == 'false':
            query = query.filter(IoTDevice.organization_id.is_(None))

        total = query.count()
        devices = query.order_by(IoTDevice.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # Batch-fetch org names
        org_ids = {d.organization_id for d in devices if d.organization_id}
        org_map = {}
        if org_ids:
            orgs = self.db_session.query(Organization).filter(Organization.id.in_(org_ids)).all()
            for o in orgs:
                org_map[o.id] = o.name

        results = []
        for d in devices:
            results.append({
                'id': d.id,
                'deviceName': d.device_name,
                'deviceType': d.device_type,
                'macAddressBluetooth': d.mac_address_bluetooth,
                'macAddressTablet': d.mac_address_tablet,
                'organizationId': d.organization_id,
                'organizationName': org_map.get(d.organization_id),
                'isActive': d.is_active,
                'createdDate': d.created_date.isoformat() if d.created_date else None,
                'updatedDate': d.updated_date.isoformat() if d.updated_date else None,
            })

        return {'items': results, 'total': total, 'page': page, 'pageSize': page_size}

    def get_iot_device(self, device_id: int) -> Dict[str, Any]:
        device = self.db_session.query(IoTDevice).filter(
            IoTDevice.id == device_id, IoTDevice.deleted_date.is_(None)
        ).first()
        if not device:
            raise NotFoundException(f'IoT device {device_id} not found')

        org_name = None
        if device.organization_id:
            org = self.db_session.query(Organization).filter(Organization.id == device.organization_id).first()
            if org:
                org_name = org.name

        return {
            'id': device.id,
            'deviceName': device.device_name,
            'deviceType': device.device_type,
            'macAddressBluetooth': device.mac_address_bluetooth,
            'macAddressTablet': device.mac_address_tablet,
            'organizationId': device.organization_id,
            'organizationName': org_name,
            'hasPassword': bool(device.password),
            'isActive': device.is_active,
            'createdDate': device.created_date.isoformat() if device.created_date else None,
            'updatedDate': device.updated_date.isoformat() if device.updated_date else None,
        }

    def create_iot_device(self, data: dict) -> Dict[str, Any]:
        device_name = (data.get('deviceName') or '').strip()
        device_type = (data.get('deviceType') or 'scale').strip()
        if not device_name:
            raise BadRequestException('deviceName is required')
        if device_type not in self.ALLOWED_DEVICE_TYPES:
            raise BadRequestException(f'deviceType must be one of {self.ALLOWED_DEVICE_TYPES}')

        org_id = data.get('organizationId')
        if org_id:
            org = self.db_session.query(Organization).filter(Organization.id == int(org_id)).first()
            if not org:
                raise NotFoundException(f'Organization {org_id} not found')

        raw_password = (data.get('password') or '').strip()
        generated = False
        if not raw_password:
            raw_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            generated = True

        hashed = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        device = IoTDevice()
        device.device_name = device_name
        device.device_type = device_type
        device.mac_address_bluetooth = (data.get('macAddressBluetooth') or '').strip() or None
        device.mac_address_tablet = (data.get('macAddressTablet') or '').strip() or None
        device.password = hashed
        device.organization_id = int(org_id) if org_id else None

        self.db_session.add(device)
        self.db_session.flush()

        result = {'id': device.id, 'message': 'IoT device created'}
        if generated:
            result['generatedPassword'] = raw_password
        return result

    def update_iot_device(self, device_id: int, data: dict) -> Dict[str, Any]:
        device = self.db_session.query(IoTDevice).filter(
            IoTDevice.id == device_id, IoTDevice.deleted_date.is_(None)
        ).first()
        if not device:
            raise NotFoundException(f'IoT device {device_id} not found')

        if 'deviceName' in data:
            device.device_name = data['deviceName']
        if 'deviceType' in data:
            if data['deviceType'] not in self.ALLOWED_DEVICE_TYPES:
                raise BadRequestException(f'deviceType must be one of {self.ALLOWED_DEVICE_TYPES}')
            device.device_type = data['deviceType']
        if 'macAddressBluetooth' in data:
            device.mac_address_bluetooth = data['macAddressBluetooth'] or None
        if 'macAddressTablet' in data:
            device.mac_address_tablet = data['macAddressTablet'] or None
        if 'organizationId' in data:
            device.organization_id = int(data['organizationId']) if data['organizationId'] else None
        if 'isActive' in data:
            device.is_active = bool(data['isActive'])
        if data.get('password'):
            hashed = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            device.password = hashed

        self.db_session.flush()
        return {'id': device.id, 'message': 'IoT device updated'}

    def delete_iot_device(self, device_id: int) -> Dict[str, Any]:
        device = self.db_session.query(IoTDevice).filter(
            IoTDevice.id == device_id, IoTDevice.deleted_date.is_(None)
        ).first()
        if not device:
            raise NotFoundException(f'IoT device {device_id} not found')
        device.deleted_date = datetime.now(timezone.utc)
        device.is_active = False
        self.db_session.flush()
        return {'id': device.id, 'message': 'IoT device deleted'}

    def get_iot_device_stats(self, query_params: dict) -> Dict[str, Any]:
        base = self.db_session.query(IoTDevice).filter(IoTDevice.deleted_date.is_(None))
        total = base.count()
        assigned = base.filter(IoTDevice.organization_id.isnot(None)).count()
        unassigned = total - assigned

        type_rows = (
            self.db_session.query(IoTDevice.device_type, func.count(IoTDevice.id))
            .filter(IoTDevice.deleted_date.is_(None))
            .group_by(IoTDevice.device_type)
            .all()
        )
        by_type = {row[0]: row[1] for row in type_rows}

        top_orgs_rows = (
            self.db_session.query(IoTDevice.organization_id, func.count(IoTDevice.id).label('cnt'))
            .filter(IoTDevice.deleted_date.is_(None), IoTDevice.organization_id.isnot(None))
            .group_by(IoTDevice.organization_id)
            .order_by(func.count(IoTDevice.id).desc())
            .limit(10)
            .all()
        )
        org_ids = [row[0] for row in top_orgs_rows]
        org_name_map = {}
        if org_ids:
            orgs = self.db_session.query(Organization).filter(Organization.id.in_(org_ids)).all()
            org_name_map = {o.id: o.name for o in orgs}

        top_organizations = [
            {'id': row[0], 'name': org_name_map.get(row[0]), 'count': row[1]}
            for row in top_orgs_rows
        ]

        return {
            'totalDevices': total,
            'assignedDevices': assigned,
            'unassignedDevices': unassigned,
            'byType': by_type,
            'topOrganizations': top_organizations,
        }

    # ── IoT Scales ──────────────────────────────────────────────────

    ALLOWED_SCALE_TYPES = ['digital', 'analog', 'hybrid']
    ALLOWED_SCALE_STATUSES = ['active', 'maintenance', 'offline', 'inactive']

    def list_iot_scales(self, query_params: dict) -> Dict[str, Any]:
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 10))
        filter_name = query_params.get('scaleName', '').strip()
        filter_type = query_params.get('scaleType', '').strip()
        filter_status = query_params.get('status', '').strip()
        filter_owner = query_params.get('ownerUserLocationId', '').strip()

        query = self.db_session.query(IoTScale).filter(IoTScale.deleted_date.is_(None))

        if filter_name:
            query = query.filter(IoTScale.scale_name.ilike(f'%{filter_name}%'))
        if filter_type:
            query = query.filter(IoTScale.scale_type == filter_type)
        if filter_status:
            query = query.filter(IoTScale.status == filter_status)
        if filter_owner:
            query = query.filter(IoTScale.owner_user_location_id == int(filter_owner))

        total = query.count()
        scales = query.order_by(IoTScale.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # Batch-fetch owner and location names
        ul_ids = set()
        for s in scales:
            ul_ids.add(s.owner_user_location_id)
            ul_ids.add(s.location_point_id)
        ul_map = {}
        if ul_ids:
            uls = self.db_session.query(UserLocation).filter(UserLocation.id.in_(ul_ids)).all()
            ul_map = {u.id: u for u in uls}

        results = []
        for s in scales:
            owner = ul_map.get(s.owner_user_location_id)
            location = ul_map.get(s.location_point_id)
            results.append({
                'id': s.id,
                'scaleName': s.scale_name,
                'scaleType': s.scale_type,
                'status': s.status,
                'ownerUserLocationId': s.owner_user_location_id,
                'ownerName': owner.display_name if owner else None,
                'ownerEmail': owner.email if owner else None,
                'locationPointId': s.location_point_id,
                'locationName': location.display_name or location.name_en if location else None,
                'macTablet': s.mac_tablet,
                'macScale': s.mac_scale,
                'addedDate': s.added_date.isoformat() if s.added_date else None,
                'endDate': s.end_date.isoformat() if s.end_date else None,
                'isActive': s.is_active,
                'createdDate': s.created_date.isoformat() if s.created_date else None,
            })

        return {'items': results, 'total': total, 'page': page, 'pageSize': page_size}

    def get_iot_scale(self, scale_id: int) -> Dict[str, Any]:
        scale = self.db_session.query(IoTScale).filter(
            IoTScale.id == scale_id, IoTScale.deleted_date.is_(None)
        ).first()
        if not scale:
            raise NotFoundException(f'IoT scale {scale_id} not found')

        owner = self.db_session.query(UserLocation).filter(UserLocation.id == scale.owner_user_location_id).first()
        location = self.db_session.query(UserLocation).filter(UserLocation.id == scale.location_point_id).first()

        return {
            'id': scale.id,
            'scaleName': scale.scale_name,
            'scaleType': scale.scale_type,
            'status': scale.status,
            'ownerUserLocationId': scale.owner_user_location_id,
            'ownerName': owner.display_name if owner else None,
            'ownerEmail': owner.email if owner else None,
            'locationPointId': scale.location_point_id,
            'locationName': location.display_name or location.name_en if location else None,
            'macTablet': scale.mac_tablet,
            'macScale': scale.mac_scale,
            'calibrationData': scale.calibration_data,
            'notes': scale.notes,
            'hasPassword': bool(scale.password),
            'addedDate': scale.added_date.isoformat() if scale.added_date else None,
            'endDate': scale.end_date.isoformat() if scale.end_date else None,
            'isActive': scale.is_active,
            'createdDate': scale.created_date.isoformat() if scale.created_date else None,
            'updatedDate': scale.updated_date.isoformat() if scale.updated_date else None,
        }

    def create_iot_scale(self, data: dict) -> Dict[str, Any]:
        scale_name = (data.get('scaleName') or '').strip()
        password = (data.get('password') or '').strip()
        scale_type = (data.get('scaleType') or 'digital').strip()
        owner_id = data.get('ownerUserLocationId')
        location_id = data.get('locationPointId')

        if not scale_name:
            raise BadRequestException('scaleName is required')
        if not password:
            raise BadRequestException('password is required')
        if not owner_id:
            raise BadRequestException('ownerUserLocationId is required')
        if not location_id:
            raise BadRequestException('locationPointId is required')
        if scale_type not in self.ALLOWED_SCALE_TYPES:
            raise BadRequestException(f'scaleType must be one of {self.ALLOWED_SCALE_TYPES}')

        # Validate owner and location exist
        owner = self.db_session.query(UserLocation).filter(UserLocation.id == int(owner_id)).first()
        if not owner:
            raise NotFoundException(f'Owner user location {owner_id} not found')
        location = self.db_session.query(UserLocation).filter(UserLocation.id == int(location_id)).first()
        if not location:
            raise NotFoundException(f'Location point {location_id} not found')

        # Check unique scale_name
        existing = self.db_session.query(IoTScale).filter(
            IoTScale.scale_name == scale_name, IoTScale.deleted_date.is_(None)
        ).first()
        if existing:
            raise BadRequestException(f'Scale name "{scale_name}" already exists')

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        scale = IoTScale()
        scale.scale_name = scale_name
        scale.password = hashed
        scale.owner_user_location_id = int(owner_id)
        scale.location_point_id = int(location_id)
        scale.scale_type = scale_type
        scale.status = data.get('status', 'active')
        scale.mac_tablet = (data.get('macTablet') or '').strip() or None
        scale.mac_scale = (data.get('macScale') or '').strip() or None
        scale.calibration_data = data.get('calibrationData')
        scale.notes = data.get('notes')

        self.db_session.add(scale)
        self.db_session.flush()
        return {'id': scale.id, 'message': 'IoT scale created'}

    def update_iot_scale(self, scale_id: int, data: dict) -> Dict[str, Any]:
        scale = self.db_session.query(IoTScale).filter(
            IoTScale.id == scale_id, IoTScale.deleted_date.is_(None)
        ).first()
        if not scale:
            raise NotFoundException(f'IoT scale {scale_id} not found')

        if 'scaleName' in data:
            new_name = (data['scaleName'] or '').strip()
            if new_name and new_name != scale.scale_name:
                existing = self.db_session.query(IoTScale).filter(
                    IoTScale.scale_name == new_name, IoTScale.deleted_date.is_(None), IoTScale.id != scale_id
                ).first()
                if existing:
                    raise BadRequestException(f'Scale name "{new_name}" already exists')
                scale.scale_name = new_name
        if 'scaleType' in data:
            if data['scaleType'] not in self.ALLOWED_SCALE_TYPES:
                raise BadRequestException(f'scaleType must be one of {self.ALLOWED_SCALE_TYPES}')
            scale.scale_type = data['scaleType']
        if 'status' in data:
            if data['status'] not in self.ALLOWED_SCALE_STATUSES:
                raise BadRequestException(f'status must be one of {self.ALLOWED_SCALE_STATUSES}')
            scale.status = data['status']
        if 'ownerUserLocationId' in data:
            scale.owner_user_location_id = int(data['ownerUserLocationId'])
        if 'locationPointId' in data:
            scale.location_point_id = int(data['locationPointId'])
        if 'macTablet' in data:
            scale.mac_tablet = data['macTablet'] or None
        if 'macScale' in data:
            scale.mac_scale = data['macScale'] or None
        if 'calibrationData' in data:
            scale.calibration_data = data['calibrationData']
        if 'notes' in data:
            scale.notes = data['notes']
        if 'endDate' in data:
            scale.end_date = data['endDate']
        if 'isActive' in data:
            scale.is_active = bool(data['isActive'])
        if data.get('password'):
            hashed = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            scale.password = hashed

        self.db_session.flush()
        return {'id': scale.id, 'message': 'IoT scale updated'}

    def delete_iot_scale(self, scale_id: int) -> Dict[str, Any]:
        scale = self.db_session.query(IoTScale).filter(
            IoTScale.id == scale_id, IoTScale.deleted_date.is_(None)
        ).first()
        if not scale:
            raise NotFoundException(f'IoT scale {scale_id} not found')
        scale.deleted_date = datetime.now(timezone.utc)
        scale.is_active = False
        self.db_session.flush()
        return {'id': scale.id, 'message': 'IoT scale deleted'}

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _to_camel(snake_str: str) -> str:
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
