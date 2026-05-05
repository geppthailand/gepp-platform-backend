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
from GEPPPlatform.exceptions import (
    NotFoundException,
    BadRequestException,
    ValidationException,
    ConflictException,
)


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

    def get_user(self, user_id: int) -> Dict[str, Any]:
        ul = (
            self.db_session.query(UserLocation)
            .filter(UserLocation.id == user_id, UserLocation.is_user == True)
            .first()
        )
        if not ul:
            raise NotFoundException(f'User {user_id} not found')

        owner_email = None
        org_name = None
        if ul.organization_id:
            org = self.db_session.query(Organization).options(
                joinedload(Organization.owner),
                joinedload(Organization.organization_info),
            ).filter(Organization.id == ul.organization_id).first()
            if org:
                if org.owner:
                    owner_email = org.owner.email
                if org.organization_info:
                    org_name = org.organization_info.company_name

        return {
            'id': ul.id,
            'firstName': ul.first_name,
            'lastName': ul.last_name,
            'email': ul.email,
            'phone': ul.phone,
            'displayName': ul.display_name,
            'username': ul.username,
            'organizationId': ul.organization_id,
            'organizationName': org_name,
            'ownerEmail': owner_email,
            'platform': ul.platform.value if ul.platform else None,
            'platformRole': ul.platform_role,
            'companyName': ul.company_name,
            'companyPhone': ul.company_phone,
            'companyEmail': ul.company_email,
            'taxId': ul.tax_id,
            'address': ul.address,
            'postalCode': ul.postal_code,
            'businessType': ul.business_type,
            'businessIndustry': ul.business_industry,
            'isUser': ul.is_user,
            'isLocation': ul.is_location,
            'isActive': ul.is_active,
            'isEmailActive': ul.is_email_active,
            'note': ul.note,
            'createdDate': ul.created_date.isoformat() if ul.created_date else None,
            'updatedDate': ul.updated_date.isoformat() if ul.updated_date else None,
        }

    def change_user_password(self, user_id: int, data: dict) -> Dict[str, Any]:
        new_password = data.get('password', '').strip()
        if not new_password:
            raise BadRequestException('Password is required')
        if len(new_password) < 6:
            raise BadRequestException('Password must be at least 6 characters')

        user = (
            self.db_session.query(UserLocation)
            .filter(UserLocation.id == user_id, UserLocation.is_user == True)
            .first()
        )
        if not user:
            raise NotFoundException(f'User {user_id} not found')

        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user.password = hashed
        self.db_session.flush()
        return {'id': user.id, 'message': 'Password changed successfully'}

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

        # Resolve paired hardware (if any) so the show page can render the
        # HW#id + MAC badge without a second round-trip.
        hardware_id = getattr(device, 'hardware_id', None)
        hardware_mac = None
        if hardware_id:
            from sqlalchemy import text as _t
            hw_row = self.db_session.execute(_t(
                "SELECT mac_address FROM iot_hardwares "
                "WHERE id = :id AND deleted_date IS NULL"
            ), {'id': int(hardware_id)}).fetchone()
            if hw_row:
                hardware_mac = hw_row[0]

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
            'hardwareId': hardware_id,
            'hardwareMac': hardware_mac,
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

        # Pending command count (FleetOverview "Pending Commands" card).
        # Counts cmds that are still waiting to be picked up by the device
        # OR have been delivered but not yet ACKed. Both states warrant
        # admin attention.
        from sqlalchemy import text as _t
        pending_cmds = int(self.db_session.execute(_t(
            "SELECT COUNT(*) FROM iot_device_commands "
            "WHERE status IN ('pending', 'delivered')"
        )).fetchone()[0] or 0)

        # Active-watcher count (FleetOverview "Active Watchers" card).
        # Devices whose admin_watching_until flag is currently in the
        # future — i.e. an admin is actively watching the detail page or
        # has just clicked Pair / Unpair / issue-cmd within the last
        # 5 min, putting the tablet into long-poll mode.
        active_watchers = int(self.db_session.execute(_t(
            "SELECT COUNT(*) FROM iot_device_health "
            "WHERE raw->>'admin_watching_until' IS NOT NULL "
            "  AND (raw->>'admin_watching_until')::timestamptz > NOW()"
        )).fetchone()[0] or 0)

        return {
            'totalDevices': total,
            'assignedDevices': assigned,
            'unassignedDevices': unassigned,
            'byType': by_type,
            'topOrganizations': top_organizations,
            'pendingCommands': pending_cmds,
            'activeWatchers': active_watchers,
        }

    # ── IoT Devices: realtime / status / commands / events ─────────────

    ALLOWED_DEVICE_COMMAND_TYPES = [
        'force_login', 'force_logout', 'navigate', 'reset_to_home', 'reset_input',
        'overwrite_cache', 'clear_storage', 'restart_app', 'ping',
        # Server-issued during Pair-with-PIN. Tablet hijack_agent writes the
        # 4–8 digit PIN to secure storage. Admin command-issue endpoint
        # accepts this too for ad-hoc PIN resets.
        'set_settings_pin',
        # Kiosk Mode toggle. The tablet calls KioskModeNotifier which opens
        # the system Home-app chooser — an on-site tap is required to
        # complete the launcher swap. The kiosk flag (router gating, wake-
        # lock, allowed-paths whitelist) flips immediately regardless.
        'enable_kiosk', 'disable_kiosk',
    ]

    def _serialize_device_row(self, row) -> Dict[str, Any]:
        """Shared row shape for /realtime + /by-organization."""
        # Row indexes match the SELECT below in list_realtime / list_by_organization.
        # Cols 15-17 are the tags + maintenance metadata added in
        # 20260503_*_049_add_tags_and_maintenance_to_iot_devices.sql.
        tags_raw = row[15]
        # JSONB comes back as a Python list already with most drivers; tolerate
        # bytes/str just in case.
        if isinstance(tags_raw, (bytes, bytearray)):
            try:
                import json as _json
                tags = _json.loads(tags_raw.decode('utf-8'))
            except Exception:
                tags = []
        elif isinstance(tags_raw, str):
            try:
                import json as _json
                tags = _json.loads(tags_raw)
            except Exception:
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []
        return {
            'id': row[0],
            'device_name': row[1],
            'type': row[2],
            'mac_bt': row[3],
            'mac_tablet': row[4],
            'organization': (
                {'id': row[5], 'name': row[6]} if row[5] is not None else None
            ),
            'online': bool(row[7]),
            'last_seen_at': row[8].isoformat() if row[8] else None,
            'current_route': row[9],
            'current_user_id': row[10],
            'battery_level': row[11],
            'battery_charging': row[12],
            'network_type': row[13],
            'network_strength': row[14],
            'tags': tags,
            'maintenance_mode': bool(row[16]) if row[16] is not None else False,
            'maintenance_reason': row[17],
            # Hardware pairing — when a physical tablet is bound to this
            # logical iot_devices account, surface the MAC for the admin
            # list ("MAC Address" column before Device Name) and the
            # hardware_id for the detail-page badge.
            'hardware_id': row[18],
            'hardware_mac': row[19],
        }

    _REALTIME_BASE_SELECT = (
        "SELECT d.id, d.device_name, d.device_type, d.mac_address_bluetooth, "
        "d.mac_address_tablet, d.organization_id, "
        "COALESCE(oi.company_name, o.name) AS org_name, "
        "(h.last_seen_at > NOW() - INTERVAL '30 seconds') AS online, "
        "h.last_seen_at, h.current_route, h.current_user_id, "
        "h.battery_level, h.battery_charging, h.network_type, h.network_strength, "
        "d.tags, d.maintenance_mode, d.maintenance_reason, "
        "d.hardware_id, hw.mac_address AS hardware_mac "
        "FROM iot_devices d "
        "LEFT JOIN iot_device_health h ON h.device_id = d.id "
        "LEFT JOIN organizations o ON o.id = d.organization_id "
        "LEFT JOIN organization_info oi ON oi.id = o.organization_info_id "
        "LEFT JOIN iot_hardwares hw ON hw.id = d.hardware_id "
    )

    def list_realtime(self, query_params: dict, headers: Optional[dict] = None) -> Dict[str, Any]:
        """List of devices with realtime health for the admin dashboard.

        Supports filters: organizationId, status (online|offline), search.
        Provides ETag/304 short-circuit so the dashboard can poll cheaply.
        Always returns a dict; callers use the optional ``__http__`` key when present
        to override status/headers (e.g. 304).
        """
        from sqlalchemy import text as _t
        import hashlib as _hashlib

        org_id = (query_params.get('organizationId') or '').strip() if query_params else ''
        status = (query_params.get('status') or '').strip().lower() if query_params else ''
        search = (query_params.get('search') or '').strip() if query_params else ''
        tag = (query_params.get('tag') or '').strip() if query_params else ''
        maintenance = (query_params.get('maintenance') or '').strip().lower() if query_params else ''

        where_clauses = ['d.deleted_date IS NULL']
        params: Dict[str, Any] = {}
        if org_id:
            where_clauses.append('d.organization_id = :org_id')
            params['org_id'] = int(org_id)
        if search:
            where_clauses.append("(d.device_name ILIKE :search OR d.mac_address_bluetooth ILIKE :search OR d.mac_address_tablet ILIKE :search)")
            params['search'] = f'%{search}%'
        if status == 'online':
            where_clauses.append("(h.last_seen_at > NOW() - INTERVAL '30 seconds')")
        elif status == 'offline':
            where_clauses.append("(h.last_seen_at IS NULL OR h.last_seen_at <= NOW() - INTERVAL '30 seconds')")
        # Tag filter — `tags` is a JSONB array of strings; the @> operator
        # uses the GIN index added in migration 049 for fast lookup.
        if tag:
            where_clauses.append("d.tags @> CAST(:tag_filter AS JSONB)")
            import json as _json
            params['tag_filter'] = _json.dumps([tag])
        # Maintenance filter — accepts 'on' / 'off'.
        if maintenance == 'on':
            where_clauses.append('d.maintenance_mode = TRUE')
        elif maintenance == 'off':
            where_clauses.append('d.maintenance_mode = FALSE')

        where_sql = ' AND '.join(where_clauses)

        # ETag based on global health watermark (cheap to compute)
        etag_row = self.db_session.execute(_t(
            "SELECT MAX(last_seen_at) AS m, COUNT(*) AS c FROM iot_device_health"
        )).fetchone()
        watermark = etag_row[0].isoformat() if (etag_row and etag_row[0]) else 'none'
        count = int(etag_row[1] if etag_row else 0)
        etag = '"' + _hashlib.md5(f'{watermark}|{count}|{where_sql}|{params}'.encode('utf-8')).hexdigest() + '"'

        if_none_match = None
        if headers:
            for k, v in headers.items():
                if k.lower() == 'if-none-match':
                    if_none_match = v
                    break

        if if_none_match and if_none_match == etag:
            return {
                '__http__': {
                    'statusCode': 304,
                    'headers': {'ETag': etag},
                    'body': '',
                }
            }

        sql = self._REALTIME_BASE_SELECT + 'WHERE ' + where_sql + ' ORDER BY d.id ASC'
        rows = self.db_session.execute(_t(sql), params).fetchall()
        items = [self._serialize_device_row(r) for r in rows]

        return {
            'items': items,
            'etag': etag,
            '__http__': {'headers': {'ETag': etag}},
        }

    def list_by_organization(self) -> Dict[str, Any]:
        """Devices grouped by organization, including an unassigned bucket."""
        from sqlalchemy import text as _t

        sql = self._REALTIME_BASE_SELECT + 'WHERE d.deleted_date IS NULL ORDER BY d.organization_id NULLS LAST, d.id ASC'
        rows = self.db_session.execute(_t(sql)).fetchall()

        groups: Dict[Any, Dict[str, Any]] = {}
        for r in rows:
            row = self._serialize_device_row(r)
            org_id = r[5]
            org_name = r[6]
            key = org_id if org_id is not None else '__unassigned__'
            if key not in groups:
                groups[key] = {
                    'organization': (
                        {'id': org_id, 'name': org_name}
                        if org_id is not None else
                        {'id': None, 'name': 'Unassigned'}
                    ),
                    'devices': [],
                    'online_count': 0,
                    'total_count': 0,
                    'last_activity_at': None,
                }
            entry = groups[key]
            entry['devices'].append(row)
            entry['total_count'] += 1
            if row['online']:
                entry['online_count'] += 1
            if row['last_seen_at']:
                if entry['last_activity_at'] is None or row['last_seen_at'] > entry['last_activity_at']:
                    entry['last_activity_at'] = row['last_seen_at']

        # Stable order: orgs first by id ASC, unassigned last.
        ordered: List[Dict[str, Any]] = []
        for key in sorted([k for k in groups.keys() if k != '__unassigned__']):
            ordered.append(groups[key])
        if '__unassigned__' in groups:
            ordered.append(groups['__unassigned__'])

        return {'items': ordered}

    def _ensure_device_exists(self, device_id: int) -> None:
        from GEPPPlatform.models.cores.iot_devices import IoTDevice as _D
        device = self.db_session.query(_D).filter(_D.id == device_id, _D.deleted_date.is_(None)).first()
        if not device:
            raise NotFoundException(f'IoT device {device_id} not found')

    def get_device_status(self, device_id: int) -> Dict[str, Any]:
        """Full health row + last 5 commands + last 50 events.

        Side-effect: extends the per-device ``admin_watching_until`` flag in
        ``iot_device_health.raw`` for 30 minutes so subsequent /sync calls long-poll.
        """
        from sqlalchemy import text as _t
        self._ensure_device_exists(device_id)

        # Refresh (or insert sentinel) admin_watching_until.
        self.db_session.execute(_t(
            "INSERT INTO iot_device_health (device_id, last_seen_at, raw) "
            "VALUES (:device_id, NOW() - INTERVAL '1 hour', "
            "        jsonb_build_object('admin_watching_until', "
            "                           to_char((NOW() + INTERVAL '30 minutes') AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))) "
            "ON CONFLICT (device_id) DO UPDATE "
            "SET raw = COALESCE(iot_device_health.raw, '{}'::jsonb) || "
            "          jsonb_build_object('admin_watching_until', "
            "            to_char((NOW() + INTERVAL '30 minutes') AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))"
        ), {'device_id': device_id})

        health_row = self.db_session.execute(_t(
            "SELECT device_id, last_seen_at, "
            "(last_seen_at > NOW() - INTERVAL '30 seconds') AS online, "
            "battery_level, battery_charging, cpu_temp_c, network_type, network_strength, "
            "ip_address, storage_free_mb, ram_free_mb, os_version, app_version, "
            "current_route, current_user_id, current_org_id, current_location_id, "
            "scale_connected, scale_mac_bt, cache_summary, raw "
            "FROM iot_device_health WHERE device_id = :device_id"
        ), {'device_id': device_id}).fetchone()

        health: Optional[Dict[str, Any]] = None
        if health_row:
            health = {
                'device_id': health_row[0],
                'last_seen_at': health_row[1].isoformat() if health_row[1] else None,
                'online': bool(health_row[2]),
                'battery_level': health_row[3],
                'battery_charging': health_row[4],
                'cpu_temp_c': float(health_row[5]) if health_row[5] is not None else None,
                'network_type': health_row[6],
                'network_strength': health_row[7],
                'ip_address': health_row[8],
                'storage_free_mb': health_row[9],
                'ram_free_mb': health_row[10],
                'os_version': health_row[11],
                'app_version': health_row[12],
                'current_route': health_row[13],
                'current_user_id': health_row[14],
                'current_org_id': health_row[15],
                'current_location_id': health_row[16],
                'scale_connected': health_row[17],
                'scale_mac_bt': health_row[18],
                'cache_summary': health_row[19],
                'raw': health_row[20],
            }

        cmd_rows = self.db_session.execute(_t(
            "SELECT id, command_type, payload, status, issued_by, issued_at, "
            "delivered_at, acked_at, completed_at, result, expires_at "
            "FROM iot_device_commands WHERE device_id = :device_id "
            "ORDER BY issued_at DESC LIMIT 5"
        ), {'device_id': device_id}).fetchall()
        recent_commands = [
            {
                'id': r[0], 'command_type': r[1], 'payload': r[2], 'status': r[3],
                'issued_by': r[4],
                'issued_at': r[5].isoformat() if r[5] else None,
                'delivered_at': r[6].isoformat() if r[6] else None,
                'acked_at': r[7].isoformat() if r[7] else None,
                'completed_at': r[8].isoformat() if r[8] else None,
                'result': r[9],
                'expires_at': r[10].isoformat() if r[10] else None,
            }
            for r in cmd_rows
        ]

        ev_rows = self.db_session.execute(_t(
            "SELECT id, occurred_at, received_at, event_type, route, payload, user_id, session_id "
            "FROM iot_device_events WHERE device_id = :device_id "
            "ORDER BY occurred_at DESC LIMIT 50"
        ), {'device_id': device_id}).fetchall()
        recent_events = [
            {
                'id': r[0],
                'occurred_at': r[1].isoformat() if r[1] else None,
                'received_at': r[2].isoformat() if r[2] else None,
                'event_type': r[3],
                'route': r[4],
                'payload': r[5],
                'user_id': r[6],
                'session_id': r[7],
            }
            for r in ev_rows
        ]

        return {
            'health': health,
            'recent_commands': recent_commands,
            'recent_events': recent_events,
        }

    def list_iot_device_events(self, device_id: int, query_params: dict) -> Dict[str, Any]:
        from sqlalchemy import text as _t
        self._ensure_device_exists(device_id)

        page = max(1, int(query_params.get('page', 1)))
        page_size = int(query_params.get('pageSize', 50))
        if page_size > 200:
            page_size = 200
        if page_size < 1:
            page_size = 50

        date_from = (query_params.get('from') or '').strip()
        date_to = (query_params.get('to') or '').strip()
        type_filter = (query_params.get('type') or '').strip()
        route_filter = (query_params.get('route') or '').strip()

        where = ['device_id = :device_id']
        params: Dict[str, Any] = {'device_id': device_id}
        if date_from:
            where.append('occurred_at >= :date_from')
            params['date_from'] = date_from
        if date_to:
            where.append('occurred_at <= :date_to')
            params['date_to'] = date_to
        if type_filter:
            type_list = [t.strip() for t in type_filter.split(',') if t.strip()]
            if type_list:
                where.append('event_type = ANY(:type_list)')
                params['type_list'] = type_list
        if route_filter:
            where.append('route = :route_filter')
            params['route_filter'] = route_filter
        where_sql = ' AND '.join(where)

        total_row = self.db_session.execute(_t(
            f"SELECT COUNT(*) FROM iot_device_events WHERE {where_sql}"
        ), params).fetchone()
        total = int(total_row[0] if total_row else 0)

        params_paged = dict(params)
        params_paged['_limit'] = page_size
        params_paged['_offset'] = (page - 1) * page_size
        rows = self.db_session.execute(_t(
            f"SELECT id, occurred_at, received_at, event_type, route, payload, user_id, session_id "
            f"FROM iot_device_events WHERE {where_sql} "
            f"ORDER BY occurred_at DESC LIMIT :_limit OFFSET :_offset"
        ), params_paged).fetchall()

        # NB: top-level key is `items` (NOT `data`). The frontend provider's
        # unwrap() helper collapses `{data: ...}` wrappers, so a `data:[…]`
        # payload would arrive at the consumer as a bare array, dropping
        # `total`/`page` and breaking the Action Trail / Commands tabs.
        return {
            'items': [
                {
                    'id': r[0],
                    'occurred_at': r[1].isoformat() if r[1] else None,
                    'received_at': r[2].isoformat() if r[2] else None,
                    'event_type': r[3],
                    'route': r[4],
                    'payload': r[5],
                    'user_id': r[6],
                    'session_id': r[7],
                }
                for r in rows
            ],
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    def list_iot_device_commands(self, device_id: int, query_params: dict) -> Dict[str, Any]:
        from sqlalchemy import text as _t
        self._ensure_device_exists(device_id)

        page = max(1, int(query_params.get('page', 1)))
        page_size = int(query_params.get('pageSize', 50))
        if page_size > 200:
            page_size = 200
        if page_size < 1:
            page_size = 50

        status_filter = (query_params.get('status') or '').strip()
        where = ['c.device_id = :device_id']
        params: Dict[str, Any] = {'device_id': device_id}
        if status_filter:
            status_list = [s.strip() for s in status_filter.split(',') if s.strip()]
            if status_list:
                where.append('c.status = ANY(:status_list)')
                params['status_list'] = status_list
        where_sql = ' AND '.join(where)

        total_row = self.db_session.execute(_t(
            f"SELECT COUNT(*) FROM iot_device_commands c WHERE {where_sql}"
        ), params).fetchone()
        total = int(total_row[0] if total_row else 0)

        params_paged = dict(params)
        params_paged['_limit'] = page_size
        params_paged['_offset'] = (page - 1) * page_size
        rows = self.db_session.execute(_t(
            f"SELECT c.id, c.command_type, c.payload, c.status, c.issued_by, "
            f"COALESCE(NULLIF(TRIM(CONCAT_WS(' ', u.first_name, u.last_name)), ''), u.display_name, u.email) AS issued_by_name, "
            f"c.issued_at, c.delivered_at, c.acked_at, c.completed_at, c.result, c.expires_at "
            f"FROM iot_device_commands c "
            f"LEFT JOIN user_locations u ON u.id = c.issued_by "
            f"WHERE {where_sql} "
            f"ORDER BY c.issued_at DESC LIMIT :_limit OFFSET :_offset"
        ), params_paged).fetchall()

        # See note in list_iot_device_events about `items` vs `data`.
        return {
            'items': [
                {
                    'id': r[0],
                    'command_type': r[1],
                    'payload': r[2],
                    'status': r[3],
                    'issued_by': r[4],
                    'issued_by_name': r[5],
                    'issued_at': r[6].isoformat() if r[6] else None,
                    'delivered_at': r[7].isoformat() if r[7] else None,
                    'acked_at': r[8].isoformat() if r[8] else None,
                    'completed_at': r[9].isoformat() if r[9] else None,
                    'result': r[10],
                    'expires_at': r[11].isoformat() if r[11] else None,
                }
                for r in rows
            ],
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    def issue_device_command(self, device_id: int, data: dict, current_user: dict) -> Dict[str, Any]:
        from sqlalchemy import text as _t
        import json as _json

        self._ensure_device_exists(device_id)

        if not isinstance(data, dict):
            raise BadRequestException('Body must be an object')
        command_type = (data.get('command_type') or '').strip()
        if command_type not in self.ALLOWED_DEVICE_COMMAND_TYPES:
            raise BadRequestException(
                f'command_type must be one of {self.ALLOWED_DEVICE_COMMAND_TYPES}'
            )

        payload = data.get('payload') or {}
        if not isinstance(payload, dict):
            raise BadRequestException('payload must be an object')

        issuer_id = (current_user or {}).get('user_id')
        if not issuer_id:
            raise BadRequestException('Cannot determine issuing admin user')

        row = self.db_session.execute(_t(
            "INSERT INTO iot_device_commands "
            "(device_id, command_type, payload, status, issued_by, issued_at, expires_at) "
            "VALUES (:device_id, :command_type, CAST(:payload AS jsonb), 'pending', "
            ":issued_by, NOW(), NOW() + INTERVAL '5 minutes') "
            "RETURNING id, status, expires_at"
        ), {
            'device_id': device_id,
            'command_type': command_type,
            'payload': _json.dumps(payload),
            'issued_by': issuer_id,
        }).fetchone()

        # Refresh the admin_watching_until flag so the device long-polls eagerly.
        self.db_session.execute(_t(
            "INSERT INTO iot_device_health (device_id, last_seen_at, raw) "
            "VALUES (:device_id, NOW() - INTERVAL '1 hour', "
            "        jsonb_build_object('admin_watching_until', "
            "                           to_char((NOW() + INTERVAL '30 minutes') AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))) "
            "ON CONFLICT (device_id) DO UPDATE "
            "SET raw = COALESCE(iot_device_health.raw, '{}'::jsonb) || "
            "          jsonb_build_object('admin_watching_until', "
            "            to_char((NOW() + INTERVAL '30 minutes') AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))"
        ), {'device_id': device_id})

        return {
            'id': row[0],
            'status': row[1],
            'expires_at': row[2].isoformat() if row[2] else None,
        }

    # ── IoT Devices: tags + maintenance + activity feed ──────────────

    def update_device_tags(self, device_id: int, data: dict) -> Dict[str, Any]:
        """Replace the tags JSONB array on a device.

        Body: ``{tags: ["pilot-group-a", "firmware-v2"]}``. Tags are
        deduped + lowercased + trimmed server-side so the GIN index
        matches consistently.
        """
        from sqlalchemy import text as _t
        import json as _json

        self._ensure_device_exists(device_id)

        raw = data.get('tags')
        if not isinstance(raw, list):
            raise BadRequestException('tags must be an array of strings')
        # Normalise: trim, lowercase, drop empty + dupes, cap length.
        seen: set = set()
        cleaned: list = []
        for t in raw:
            if not isinstance(t, str):
                continue
            v = t.strip().lower()
            if not v or v in seen:
                continue
            if len(v) > 64:
                v = v[:64]
            seen.add(v)
            cleaned.append(v)
        # Hard cap: 20 tags per device — enough for any realistic combination
        # without letting the array grow unbounded.
        cleaned = cleaned[:20]

        self.db_session.execute(_t(
            "UPDATE iot_devices SET tags = CAST(:tags AS JSONB), updated_date = NOW() "
            "WHERE id = :id AND deleted_date IS NULL"
        ), {'id': device_id, 'tags': _json.dumps(cleaned)})
        self.db_session.commit()
        return {'id': device_id, 'tags': cleaned}

    def list_device_tags(self) -> Dict[str, Any]:
        """Return the distinct set of tags currently in use across the fleet,
        with usage counts. Powers the tag-filter dropdown in the admin list.
        """
        from sqlalchemy import text as _t
        rows = self.db_session.execute(_t(
            "SELECT tag, COUNT(*) AS n "
            "FROM iot_devices, jsonb_array_elements_text(tags) AS tag "
            "WHERE deleted_date IS NULL "
            "GROUP BY tag "
            "ORDER BY n DESC, tag ASC"
        )).fetchall()
        return {'items': [{'tag': r[0], 'count': int(r[1])} for r in rows]}

    def update_device_maintenance(self, device_id: int, data: dict) -> Dict[str, Any]:
        """Toggle maintenance mode + reason + auto-clear timestamp.

        Body: ``{maintenance_mode: bool, reason?: str, until?: iso8601}``.
        Devices in maintenance are suppressed from the alerts panel and
        proactive notifications (when the cron lands).
        """
        from sqlalchemy import text as _t
        from datetime import datetime as _dt

        self._ensure_device_exists(device_id)

        mm = data.get('maintenance_mode')
        if not isinstance(mm, bool):
            raise BadRequestException('maintenance_mode must be a boolean')
        reason = data.get('reason')
        if reason is not None and not isinstance(reason, str):
            raise BadRequestException('reason must be a string when provided')

        until_iso = data.get('until')
        until_val = None
        if until_iso:
            try:
                # Accept Z-suffixed and offset-aware ISO strings alike.
                until_val = _dt.fromisoformat(until_iso.replace('Z', '+00:00'))
            except Exception:
                raise BadRequestException('until must be a valid ISO 8601 timestamp')

        self.db_session.execute(_t(
            "UPDATE iot_devices SET "
            "  maintenance_mode = :mm, "
            "  maintenance_reason = :reason, "
            "  maintenance_until = :until, "
            "  updated_date = NOW() "
            "WHERE id = :id AND deleted_date IS NULL"
        ), {
            'id': device_id,
            'mm': mm,
            'reason': reason,
            'until': until_val,
        })
        self.db_session.commit()
        return {
            'id': device_id,
            'maintenance_mode': mm,
            'maintenance_reason': reason,
            'maintenance_until': until_val.isoformat() if until_val else None,
        }

    def list_recent_activity(self, query_params: dict) -> Dict[str, Any]:
        """Fleet-wide activity feed — recent commands joined with device + actor names.

        Query params:
          * limit (default 50, max 200)
          * since (ISO 8601; defaults to NOW() - INTERVAL '24 hours')
          * status (csv of pending/delivered/succeeded/failed/expired)
        """
        from sqlalchemy import text as _t

        try:
            limit = int(query_params.get('limit', 50))
        except Exception:
            limit = 50
        limit = max(1, min(200, limit))

        since = (query_params.get('since') or '').strip()
        status = (query_params.get('status') or '').strip()

        where_clauses = []
        params: Dict[str, Any] = {'lim': limit}
        if since:
            where_clauses.append('c.issued_at >= :since')
            params['since'] = since
        else:
            where_clauses.append("c.issued_at >= NOW() - INTERVAL '24 hours'")
        if status:
            statuses = [s.strip() for s in status.split(',') if s.strip()]
            if statuses:
                where_clauses.append('c.status = ANY(:statuses)')
                params['statuses'] = statuses

        where_sql = ' AND '.join(where_clauses) if where_clauses else 'TRUE'

        rows = self.db_session.execute(_t(
            "SELECT c.id, c.device_id, d.device_name, "
            "       c.command_type, c.status, c.issued_at, c.delivered_at, "
            "       c.acked_at, c.completed_at, c.expires_at, c.payload, c.result, "
            "       c.issued_by, ul.first_name, ul.last_name "
            "FROM iot_device_commands c "
            "LEFT JOIN iot_devices d ON d.id = c.device_id "
            "LEFT JOIN user_locations ul ON ul.id = c.issued_by "
            f"WHERE {where_sql} "
            "ORDER BY c.issued_at DESC "
            "LIMIT :lim"
        ), params).fetchall()

        items = []
        for r in rows:
            actor_name = None
            if r[13] or r[14]:
                actor_name = ' '.join([p for p in (r[13], r[14]) if p]).strip() or None
            items.append({
                'id': r[0],
                'device_id': r[1],
                'device_name': r[2],
                'command_type': r[3],
                'status': r[4],
                'issued_at': r[5].isoformat() if r[5] else None,
                'delivered_at': r[6].isoformat() if r[6] else None,
                'acked_at': r[7].isoformat() if r[7] else None,
                'completed_at': r[8].isoformat() if r[8] else None,
                'expires_at': r[9].isoformat() if r[9] else None,
                'payload': r[10],
                'result': r[11],
                'issued_by': r[12],
                'issued_by_name': actor_name,
            })
        return {'items': items, 'total': len(items)}

    # ── IoT Hardwares: physical-tablet registry + pair/unpair ───────

    def list_iot_hardwares(self, query_params: dict) -> Dict[str, Any]:
        """GET /api/admin/iot-hardwares — list all reporting tablets.

        Filters: paired ('yes'|'no'), search (mac/serial/model).
        """
        from sqlalchemy import text as _t

        try:
            page = max(1, int(query_params.get('page', 1) or 1))
        except Exception:
            page = 1
        try:
            page_size = int(query_params.get('pageSize', 50) or 50)
        except Exception:
            page_size = 50
        page_size = max(1, min(page_size, 200))

        paired = (query_params.get('paired') or '').strip().lower()
        search = (query_params.get('search') or '').strip()

        where = ['h.deleted_date IS NULL']
        params: Dict[str, Any] = {}
        if paired == 'yes':
            where.append('h.paired_iot_device_id IS NOT NULL')
        elif paired == 'no':
            where.append('h.paired_iot_device_id IS NULL')
        if search:
            where.append(
                '('
                'h.mac_address ILIKE :search OR '
                'h.serial_number ILIKE :search OR '
                'h.device_model ILIKE :search OR '
                'h.device_code ILIKE :search'
                ')'
            )
            params['search'] = f'%{search}%'
        where_sql = ' AND '.join(where)

        total = int(self.db_session.execute(_t(
            f"SELECT COUNT(*) FROM iot_hardwares h WHERE {where_sql}"
        ), params).fetchone()[0] or 0)

        params_paged = dict(params)
        params_paged['_lim'] = page_size
        params_paged['_off'] = (page - 1) * page_size

        rows = self.db_session.execute(_t(
            "SELECT h.id, h.mac_address, h.serial_number, h.device_code, "
            "       h.device_model, h.os_version, h.app_version, "
            "       h.last_checkin_at, h.last_ip_address, "
            "       h.paired_iot_device_id, d.device_name, h.paired_at, h.created_date, "
            "       h.last_lat, h.last_lng, h.last_location_accuracy_m, h.last_location_at, "
            "       o.id AS organization_id, "
            "       o.name AS organization_name, "
            "       dh.current_route "
            "FROM iot_hardwares h "
            "LEFT JOIN iot_devices d ON d.id = h.paired_iot_device_id "
            "LEFT JOIN organizations o ON o.id = d.organization_id "
            "LEFT JOIN iot_device_health dh ON dh.device_id = d.id "
            f"WHERE {where_sql} "
            "ORDER BY h.last_checkin_at DESC NULLS LAST, h.id ASC "
            "LIMIT :_lim OFFSET :_off"
        ), params_paged).fetchall()

        items = []
        now = self.db_session.execute(_t("SELECT NOW()")).fetchone()[0]
        for r in rows:
            last_checkin = r[7]
            online = False
            if last_checkin is not None:
                try:
                    delta = (now - last_checkin).total_seconds()
                    online = delta <= 15  # 3 missed beats @ 5 s
                except Exception:
                    online = False
            items.append({
                'id': r[0],
                'mac_address': r[1],
                'serial_number': r[2],
                'device_code': r[3],
                'device_model': r[4],
                'os_version': r[5],
                'app_version': r[6],
                'last_checkin_at': last_checkin.isoformat() if last_checkin else None,
                'online': online,
                'last_ip_address': r[8],
                'paired_iot_device_id': r[9],
                'paired_iot_device_name': r[10],
                'paired_at': r[11].isoformat() if r[11] else None,
                'created_date': r[12].isoformat() if r[12] else None,
                # GPS — drives the Map tab.
                'last_lat': float(r[13]) if r[13] is not None else None,
                'last_lng': float(r[14]) if r[14] is not None else None,
                'last_location_accuracy_m': float(r[15]) if r[15] is not None else None,
                'last_location_at': r[16].isoformat() if r[16] else None,
                # Joined org name + current_route — handy for the Map popup.
                'organization_id': r[17],
                'organization_name': r[18],
                'current_route': r[19],
            })

        return {
            'items': items,
            'total': total,
            'page': page,
            'pageSize': page_size,
        }

    def _ensure_hardware_exists(self, hardware_id: int):
        from sqlalchemy import text as _t
        row = self.db_session.execute(_t(
            "SELECT id FROM iot_hardwares WHERE id = :id AND deleted_date IS NULL"
        ), {'id': hardware_id}).fetchone()
        if not row:
            raise NotFoundException(f'iot_hardware {hardware_id} not found')

    def _bump_admin_watching_until(self, device_id: int, minutes: int = 5) -> None:
        """Mark `iot_device_health.raw.admin_watching_until = NOW() + N min`.

        Causes the device's next `/sync` to:
          1. Receive `next_interval_s = 5` (down from 10/30/120 s adaptive).
          2. Long-poll for up to 25 s waiting for new commands.

        Used after Pair / Unpair so the tablet picks up `force_login` (mints
        live on /checkin) or the queued `force_logout {unpair:true}` within
        ~1 s of admin action — instead of waiting up to 30 s for the next
        idle-cadence sync. 5 min is a generous window: more than enough for
        the next sync to fire, short enough that an admin who navigates
        away doesn't keep the tablet in long-poll mode forever.
        """
        from sqlalchemy import text as _t
        self.db_session.execute(_t(
            "INSERT INTO iot_device_health (device_id, last_seen_at, raw) "
            "VALUES (:device_id, NOW() - INTERVAL '1 hour', "
            "        jsonb_build_object('admin_watching_until', "
            "                           to_char((NOW() + (:mins || ' minutes')::interval) AT TIME ZONE 'UTC', "
            "                                   'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))) "
            "ON CONFLICT (device_id) DO UPDATE "
            "SET raw = COALESCE(iot_device_health.raw, '{}'::jsonb) || "
            "          jsonb_build_object('admin_watching_until', "
            "            to_char((NOW() + (:mins || ' minutes')::interval) AT TIME ZONE 'UTC', "
            "                    'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'))"
        ), {'device_id': device_id, 'mins': str(minutes)})

    def pair_iot_hardware(self, hardware_id: int, data: dict, current_user: dict) -> Dict[str, Any]:
        """POST /api/admin/iot-hardwares/{id}/pair  body: {device_id}.

        Sets the bidirectional pointer:
          iot_hardwares.paired_iot_device_id = D
          iot_devices.hardware_id           = H

        On the hardware's NEXT /checkin (within ~15 s) it will receive a
        `force_login` directive in the response and transition to the
        device-token sync flow automatically.
        """
        from sqlalchemy import text as _t

        self._ensure_hardware_exists(hardware_id)

        # Accept either `iot_device_id` (preferred — matches the bidirectional
        # column name) or `device_id` (legacy) so older callers don't break.
        device_id_raw = data.get('iot_device_id', data.get('device_id'))
        if device_id_raw is None:
            raise BadRequestException('iot_device_id is required')
        try:
            device_id = int(device_id_raw)
        except Exception:
            raise BadRequestException('iot_device_id must be an integer')

        # Optional settings-PIN. Stored transiently on the hardware row;
        # consumed and cleared by the next /checkin response. 4–8 digits.
        pin_raw = data.get('pin')
        pending_pin: str | None = None
        if pin_raw is not None and str(pin_raw).strip() != '':
            pin_str = str(pin_raw).strip()
            if not pin_str.isdigit() or not (4 <= len(pin_str) <= 8):
                raise BadRequestException('pin must be 4–8 digits')
            pending_pin = pin_str

        # Validate target device exists.
        dev = self.db_session.execute(_t(
            "SELECT id, device_name FROM iot_devices "
            "WHERE id = :id AND deleted_date IS NULL"
        ), {'id': device_id}).fetchone()
        if not dev:
            raise NotFoundException(f'iot_device {device_id} not found')

        # Reject if either side is already paired to something else.
        existing = self.db_session.execute(_t(
            "SELECT paired_iot_device_id FROM iot_hardwares WHERE id = :id"
        ), {'id': hardware_id}).fetchone()
        if existing and existing[0] is not None and int(existing[0]) != device_id:
            raise ConflictException(
                f'hardware {hardware_id} is already paired to device {int(existing[0])}; unpair first'
            )

        device_pair = self.db_session.execute(_t(
            "SELECT hardware_id FROM iot_devices WHERE id = :id"
        ), {'id': device_id}).fetchone()
        if device_pair and device_pair[0] is not None and int(device_pair[0]) != hardware_id:
            raise ConflictException(
                f'device {device_id} is already paired to hardware {int(device_pair[0])}; unpair first'
            )

        actor_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

        # Set both sides atomically. Also stash any admin-supplied PIN so
        # the tablet picks it up on its next checkin (and we clear it then).
        self.db_session.execute(_t(
            "UPDATE iot_hardwares SET "
            "  paired_iot_device_id = :dev, paired_at = NOW(), paired_by = :actor, "
            "  pending_pin = :pin, "
            "  updated_date = NOW() "
            "WHERE id = :id"
        ), {'id': hardware_id, 'dev': device_id, 'actor': actor_id, 'pin': pending_pin})
        self.db_session.execute(_t(
            "UPDATE iot_devices SET hardware_id = :hw, updated_date = NOW() "
            "WHERE id = :id"
        ), {'id': device_id, 'hw': hardware_id})
        # Expire STALE unpair-style force_logout commands sitting in the
        # queue from a long-past unpair (e.g. a tablet that was offline at
        # the time and never picked up the cmd). Without this, the tablet's
        # first /sync after a fresh pair would deliver the ghost command
        # and immediately log itself out — see the 2026-05-03 ghost-loop
        # fix. Generic force_logout commands (without `unpair:true`) are
        # left alone — they're operator-only logouts with separate semantics.
        #
        # CRITICAL: only sweep cmds older than 60 s. A force_logout queued
        # in the last minute is almost certainly a legitimate Unpair the
        # admin just clicked — possibly followed by Pair-to-same-device
        # for testing or to push a new PIN — and the tablet must actually
        # execute that logout before re-authenticating. Sweeping it would
        # leave the tablet silently in stale state ("Unpair then Pair
        # doesn't work" UX bug from 2026-05-05).
        self.db_session.execute(_t(
            "UPDATE iot_device_commands SET "
            "  status = 'expired', "
            "  completed_at = NOW() "
            "WHERE device_id = :dev "
            "  AND command_type = 'force_logout' "
            "  AND status IN ('pending', 'delivered') "
            "  AND payload @> '{\"unpair\": true}'::jsonb "
            "  AND issued_at < NOW() - INTERVAL '60 seconds'"
        ), {'dev': device_id})
        # Tell the tablet to enter long-poll mode for the next 5 minutes so
        # the very next /sync fetches the freshly-minted force_login (if it
        # somehow missed the /checkin response) within ≤1 s instead of
        # waiting up to 30 s for the idle-cadence sync.
        self._bump_admin_watching_until(device_id, minutes=5)

        # If admin set a PIN, ALSO queue a `set_settings_pin` device command.
        # This covers the re-pair-with-PIN case where the tablet is already
        # paired and on /sync (so the /checkin pending_pin column never gets
        # consumed because HwCheckin is no-op'ing in steady state). The
        # command rides /sync's long-poll flow, so the PIN reaches the
        # tablet within ~1 s. Idempotent with the /checkin path: if both
        # arrive, the second write of the same value is harmless.
        if pending_pin:
            import json as _json
            self.db_session.execute(_t(
                "INSERT INTO iot_device_commands "
                "(device_id, command_type, payload, status, issued_by) "
                "VALUES (:dev, 'set_settings_pin', CAST(:pl AS JSONB), 'pending', :actor)"
            ), {
                'dev': device_id,
                'actor': actor_id,
                'pl': _json.dumps({'pin': pending_pin}),
            })
        self.db_session.commit()

        return {
            'hardware_id': hardware_id,
            'iot_device_id': device_id,
            'iot_device_name': dev[1],
            'paired': True,
        }

    def unpair_iot_hardware(self, hardware_id: int, current_user: dict) -> Dict[str, Any]:
        """POST /api/admin/iot-hardwares/{id}/unpair.

        Clears both sides AND queues a force_logout command on the
        previously-paired device so the tablet drops back to the pre-login
        checkin loop on its next /sync.
        """
        from sqlalchemy import text as _t

        self._ensure_hardware_exists(hardware_id)

        existing = self.db_session.execute(_t(
            "SELECT paired_iot_device_id FROM iot_hardwares WHERE id = :id"
        ), {'id': hardware_id}).fetchone()
        prev_device_id = (
            int(existing[0]) if (existing and existing[0] is not None) else None
        )

        # Clear hardware → device.
        self.db_session.execute(_t(
            "UPDATE iot_hardwares SET "
            "  paired_iot_device_id = NULL, paired_at = NULL, paired_by = NULL, "
            "  updated_date = NOW() "
            "WHERE id = :id"
        ), {'id': hardware_id})
        # Clear device → hardware (only if it points back at us).
        if prev_device_id:
            self.db_session.execute(_t(
                "UPDATE iot_devices SET hardware_id = NULL, updated_date = NOW() "
                "WHERE id = :id AND hardware_id = :hw"
            ), {'id': prev_device_id, 'hw': hardware_id})

            # Queue a force_logout command so the tablet drops back into the
            # pre-login state on its next /sync. The `unpair: true` payload
            # flag tells the tablet to also clear *device* credentials (not
            # just the operator session) and restart the hardware checkin loop.
            actor_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')
            self.db_session.execute(_t(
                "INSERT INTO iot_device_commands "
                "(device_id, command_type, payload, status, issued_by) "
                "VALUES (:dev, 'force_logout', CAST(:pl AS JSONB), 'pending', :actor)"
            ), {
                'dev': prev_device_id,
                'actor': actor_id,
                'pl': '{"unpair": true}',
            })
            # Drop the tablet into long-poll mode so it fetches the queued
            # force_logout within ~1 s (vs up to 30 s on the idle-cadence
            # sync). Without this an idle paired tablet can take 30 s to
            # actually log out, which made the Unpair button feel slow.
            self._bump_admin_watching_until(prev_device_id, minutes=5)
        self.db_session.commit()

        return {
            'hardware_id': hardware_id,
            'unpaired_from_iot_device_id': prev_device_id,
            'paired': False,
        }

    # ── IoT Devices: aggregated history (5-min buckets) ─────────────

    # 5-min aggregation cadence — matches the bucket size in the SQL.
    _HISTORY_BUCKET_MIN = 5
    _HISTORY_RETENTION_DAYS = 7

    def aggregate_health_snapshot(self) -> Dict[str, Any]:
        """Write a single 5-min bucket row per active device.

        Idempotent — the table's PK (device_id, bucket_start) means calling
        this twice in the same bucket is a no-op. Designed to be called by:
          * a CloudWatch / cron job every 5 minutes (preferred), OR
          * manually via this endpoint for testing / backfill.

        Also opportunistically drops rows older than 7 days from the same
        bucket so retention stays bounded without a separate sweeper.
        """
        from sqlalchemy import text as _t

        # Bucket alignment: floor NOW() to the nearest 5-min boundary.
        # Postgres expression keeps the math server-side so we don't drift
        # on clock skew between app server + db.
        result = self.db_session.execute(_t(
            "INSERT INTO iot_device_health_history "
            "  (device_id, bucket_start, online, battery_level, "
            "   battery_charging, network_type, network_strength, last_seen_at) "
            "SELECT "
            "  d.id, "
            "  date_trunc('hour', NOW()) "
            "    + (FLOOR(EXTRACT(MINUTE FROM NOW())::int / :bucket_min) "
            "       * :bucket_min) * INTERVAL '1 minute' AS bucket_start, "
            "  COALESCE(h.last_seen_at > NOW() - INTERVAL '30 seconds', FALSE) AS online, "
            "  h.battery_level, h.battery_charging, h.network_type, h.network_strength, "
            "  h.last_seen_at "
            "FROM iot_devices d "
            "LEFT JOIN iot_device_health h ON h.device_id = d.id "
            "WHERE d.deleted_date IS NULL "
            "ON CONFLICT (device_id, bucket_start) DO NOTHING"
        ), {'bucket_min': self._HISTORY_BUCKET_MIN})

        # Drop rows older than the retention window. Keeps the table small.
        purged = self.db_session.execute(_t(
            "DELETE FROM iot_device_health_history "
            "WHERE bucket_start < NOW() - INTERVAL ':d days'".replace(
                ':d', str(self._HISTORY_RETENTION_DAYS)
            )
        ))

        self.db_session.commit()

        return {
            'inserted': getattr(result, 'rowcount', 0) or 0,
            'purged': getattr(purged, 'rowcount', 0) or 0,
            'bucket_minutes': self._HISTORY_BUCKET_MIN,
            'retention_days': self._HISTORY_RETENTION_DAYS,
        }

    def list_online_history(self, query_params: dict) -> Dict[str, Any]:
        """Fleet-wide online% over a time range.

        Params:
          * range  — ``24h`` (default) | ``7d`` | ``1h``
          * organizationId — restrict to one org
        Returns ``[{bucket_start, total, online, online_pct}, …]`` ordered
        chronologically; empty buckets are skipped (frontend renders gaps).
        """
        from sqlalchemy import text as _t

        rng = (query_params.get('range') or '24h').strip()
        if rng not in ('1h', '24h', '7d'):
            rng = '24h'
        interval_sql = {
            '1h': "INTERVAL '1 hour'",
            '24h': "INTERVAL '24 hours'",
            '7d': "INTERVAL '7 days'",
        }[rng]

        org_id = (query_params.get('organizationId') or '').strip()
        params: Dict[str, Any] = {}
        org_filter = ''
        if org_id:
            org_filter = ' AND d.organization_id = :org_id'
            params['org_id'] = int(org_id)

        rows = self.db_session.execute(_t(
            "SELECT h.bucket_start, "
            "       COUNT(*) AS total, "
            "       COUNT(*) FILTER (WHERE h.online) AS online "
            "FROM iot_device_health_history h "
            "JOIN iot_devices d ON d.id = h.device_id "
            "WHERE h.bucket_start >= NOW() - " + interval_sql + " "
            "  AND d.deleted_date IS NULL"
            + org_filter +
            " GROUP BY h.bucket_start "
            "ORDER BY h.bucket_start ASC"
        ), params).fetchall()

        items = []
        for r in rows:
            total = int(r[1] or 0)
            online = int(r[2] or 0)
            items.append({
                'bucket_start': r[0].isoformat() if r[0] else None,
                'total': total,
                'online': online,
                'online_pct': round(100.0 * online / total, 1) if total else 0.0,
            })
        return {'items': items, 'range': rng}

    def list_iot_device_health_history(
        self, device_id: int, query_params: dict
    ) -> Dict[str, Any]:
        """Per-device history for sparklines on the show.tsx Status tab.

        Params:
          * range  — ``24h`` (default) | ``7d`` | ``1h``
        Returns ``[{bucket_start, online, battery_level, network_strength,
                    network_type}, …]`` ordered chronologically.
        """
        from sqlalchemy import text as _t

        self._ensure_device_exists(device_id)

        rng = (query_params.get('range') or '24h').strip()
        if rng not in ('1h', '24h', '7d'):
            rng = '24h'
        interval_sql = {
            '1h': "INTERVAL '1 hour'",
            '24h': "INTERVAL '24 hours'",
            '7d': "INTERVAL '7 days'",
        }[rng]

        rows = self.db_session.execute(_t(
            "SELECT bucket_start, online, battery_level, battery_charging, "
            "       network_type, network_strength, last_seen_at "
            "FROM iot_device_health_history "
            "WHERE device_id = :id "
            "  AND bucket_start >= NOW() - " + interval_sql + " "
            "ORDER BY bucket_start ASC"
        ), {'id': device_id}).fetchall()

        return {
            'items': [
                {
                    'bucket_start': r[0].isoformat() if r[0] else None,
                    'online': bool(r[1]),
                    'battery_level': r[2],
                    'battery_charging': r[3],
                    'network_type': r[4],
                    'network_strength': r[5],
                    'last_seen_at': r[6].isoformat() if r[6] else None,
                }
                for r in rows
            ],
            'range': rng,
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
