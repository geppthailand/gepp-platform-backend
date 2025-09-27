"""
User permission management service
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ....models.users.user_location import UserLocation
from ....models.cores.roles import SystemRole
from ....models.subscriptions.subscription_models import OrganizationRole
from ....models.cores.permissions import Permission, PermissionType


class UserPermissionService:
    """
    Service for managing user permissions at both platform and subscription levels
    """

    def __init__(self, db: Session):
        self.db = db

    def get_user_permissions(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive user permissions including platform and subscription levels
        """
        user = self.db.query(UserLocation).filter(UserLocation.id == user_id).first()
        if not user:
            return {}

        # Get platform-level permissions
        platform_permissions = self._get_platform_permissions(user)

        # Get subscription-level permissions
        subscription_permissions = self._get_subscription_permissions(user)

        # Get role-based permissions
        role_permissions = self._get_role_permissions(user)

        # Combine all permissions
        return {
            'user_id': user_id,
            'platform_permissions': platform_permissions,
            'subscription_permissions': subscription_permissions,
            'role_permissions': role_permissions,
            'effective_permissions': self._merge_permissions(
                platform_permissions,
                subscription_permissions,
                role_permissions
            )
        }

    def check_user_permission(
        self,
        user_id: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if user has specific permission
        """
        permissions = self.get_user_permissions(user_id)
        effective_permissions = permissions.get('effective_permissions', {})

        # Check direct permission
        permission_key = f"{resource}:{action}"
        if permission_key in effective_permissions:
            permission = effective_permissions[permission_key]

            # Check conditions if any
            if permission.get('conditions') and context:
                return self._evaluate_conditions(permission['conditions'], context)

            return permission.get('granted', False)

        # Check wildcard permissions
        wildcard_key = f"{resource}:*"
        if wildcard_key in effective_permissions:
            return effective_permissions[wildcard_key].get('granted', False)

        # Check global permissions
        if '*:*' in effective_permissions:
            return effective_permissions['*:*'].get('granted', False)

        return False

    def get_user_subscription_limits(self, user_id: str) -> Dict[str, Any]:
        """
        Get user's subscription limits and usage
        """
        user = self.db.query(UserLocation).filter(UserLocation.id == user_id).first()
        if not user or not user.organization_id:
            return {}

        # Get organization's subscription
        # This would typically join with organization and subscription tables
        # For now, return mock data
        return {
            'max_users': 100,
            'max_locations': 50,
            'max_transactions_per_month': 1000,
            'current_usage': {
                'users': 25,
                'locations': 10,
                'transactions_this_month': 150
            },
            'features': [
                'user_management',
                'basic_analytics',
                'waste_tracking',
                'report_generation'
            ]
        }

    def validate_subscription_action(
        self,
        user_id: str,
        action: str,
        resource: str,
        count: int = 1
    ) -> Dict[str, Any]:
        """
        Validate if action is allowed under subscription limits
        """
        limits = self.get_user_subscription_limits(user_id)

        if action == 'create_user':
            current = limits.get('current_usage', {}).get('users', 0)
            max_allowed = limits.get('max_users', 0)

            if current + count > max_allowed:
                return {
                    'allowed': False,
                    'reason': f'User limit exceeded. Max: {max_allowed}, Current: {current}',
                    'limit_type': 'user_count'
                }

        elif action == 'create_location':
            current = limits.get('current_usage', {}).get('locations', 0)
            max_allowed = limits.get('max_locations', 0)

            if current + count > max_allowed:
                return {
                    'allowed': False,
                    'reason': f'Location limit exceeded. Max: {max_allowed}, Current: {current}',
                    'limit_type': 'location_count'
                }

        return {'allowed': True}

    def get_role_permissions_matrix(self, organization_id: str) -> Dict[str, Any]:
        """
        Get permission matrix for all roles in organization
        """
        # Get all roles in organization
        platform_roles = self.db.query(SystemRole).filter(
            SystemRole.organization_id == organization_id
        ).all()

        organization_roles = self.db.query(OrganizationRole).filter(
            OrganizationRole.organization_id == organization_id
        ).all()

        matrix = {
            'platform_roles': [],
            'organization_roles': []
        }

        # Build platform roles matrix
        for role in platform_roles:
            role_permissions = self._get_role_platform_permissions(role)
            matrix['platform_roles'].append({
                'id': role.id,
                'name': role.name,
                'description': role.description,
                'permissions': role_permissions
            })

        # Build organization roles matrix
        for role in organization_roles:
            role_permissions = self._get_role_organization_permissions(role)
            matrix['organization_roles'].append({
                'id': role.id,
                'name': role.name,
                'description': role.description,
                'permissions': role_permissions
            })

        return matrix

    def assign_permission_to_role(
        self,
        role_id: str,
        role_type: str,  # 'platform' or 'business'
        permission_id: str,
        assigned_by_id: str
    ) -> bool:
        """
        Assign permission to role
        """
        try:
            if role_type == 'platform':
                # This would typically involve a role_permissions table
                # For now, just return success
                pass
            elif role_type == 'business':
                # Update organization role permissions
                role = self.db.query(OrganizationRole).filter(
                    OrganizationRole.id == role_id
                ).first()

                if role:
                    # Parse existing permissions and add new one
                    # This assumes permissions are stored as JSON or comma-separated
                    pass

            return True

        except Exception:
            return False

    # ========== PRIVATE METHODS ==========

    def _get_platform_permissions(self, user: UserLocation) -> Dict[str, Any]:
        """
        Get platform-level permissions - now returns empty as we use organization roles only
        """
        # Platform roles have been removed, all permissions are now organization-based
        return {}

        # This would typically join with role_permissions table
        # For now, return based on role name patterns
        platform_perms = {}

        role_name = role.name.lower()

        if 'super-admin' in role_name:
            platform_perms = {
                '*:*': {'granted': True, 'source': 'platform_role'}
            }
        elif 'gepp-admin' in role_name:
            platform_perms = {
                'organization:*': {'granted': True, 'source': 'platform_role'},
                'user:*': {'granted': True, 'source': 'platform_role'},
                'subscription:view': {'granted': True, 'source': 'platform_role'},
            }
        elif 'business' in role_name:
            platform_perms = {
                'user:view': {'granted': True, 'source': 'platform_role'},
                'user:create': {'granted': True, 'source': 'platform_role'},
                'user:edit': {'granted': True, 'source': 'platform_role'},
                'waste_transaction:*': {'granted': True, 'source': 'platform_role'},
                'location:*': {'granted': True, 'source': 'platform_role'},
            }

        return platform_perms

    def _get_subscription_permissions(self, user: UserLocation) -> Dict[str, Any]:
        """
        Get subscription-level permissions based on user's subscription package
        """
        if not user.organization_id:
            return {}

        # Get organization's active subscription
        # This would typically query the organization_subscriptions table
        # For now, return mock permissions based on a "Business" package

        subscription_perms = {
            'user:create': {
                'granted': True,
                'source': 'subscription',
                'conditions': {'max_count': 100}
            },
            'location:create': {
                'granted': True,
                'source': 'subscription',
                'conditions': {'max_count': 50}
            },
            'analytics:view': {'granted': True, 'source': 'subscription'},
            'analytics:export': {'granted': True, 'source': 'subscription'},
            'waste_transaction:create': {
                'granted': True,
                'source': 'subscription',
                'conditions': {'max_per_month': 1000}
            },
            'report:generate': {'granted': True, 'source': 'subscription'},
            'api:access': {'granted': True, 'source': 'subscription'},
        }

        return subscription_perms

    def _get_role_permissions(self, user: UserLocation) -> Dict[str, Any]:
        """
        Get role-based permissions (business role within organization)
        """
        if not user.organization_role_id:
            return {}

        organization_role = self.db.query(OrganizationRole).filter(
            OrganizationRole.id == user.organization_role_id
        ).first()

        if not organization_role:
            return {}

        # Parse organization role permissions
        role_perms = {}

        role_name = organization_role.name.lower()

        if 'admin' in role_name:
            role_perms = {
                'organization:manage': {'granted': True, 'source': 'organization_role'},
                'user:invite': {'granted': True, 'source': 'organization_role'},
                'user:suspend': {'granted': True, 'source': 'organization_role'},
                'role:assign': {'granted': True, 'source': 'organization_role'},
                'settings:manage': {'granted': True, 'source': 'organization_role'},
            }
        elif 'data_input' in role_name:
            role_perms = {
                'waste_transaction:create': {'granted': True, 'source': 'organization_role'},
                'waste_transaction:edit': {'granted': True, 'source': 'organization_role'},
                'location:create': {'granted': True, 'source': 'organization_role'},
            }
        elif 'auditor' in role_name:
            role_perms = {
                'waste_transaction:view': {'granted': True, 'source': 'organization_role'},
                'audit:perform': {'granted': True, 'source': 'organization_role'},
                'report:generate': {'granted': True, 'source': 'organization_role'},
            }
        elif 'viewer' in role_name:
            role_perms = {
                'waste_transaction:view': {'granted': True, 'source': 'organization_role'},
                'location:view': {'granted': True, 'source': 'organization_role'},
                'report:view': {'granted': True, 'source': 'organization_role'},
            }

        return role_perms

    def _merge_permissions(self, *permission_sets) -> Dict[str, Any]:
        """
        Merge multiple permission sets, with later sets taking precedence
        """
        merged = {}

        for permission_set in permission_sets:
            for key, permission in permission_set.items():
                if key not in merged:
                    merged[key] = permission
                else:
                    # Later permissions override earlier ones
                    # But we preserve the most restrictive conditions
                    existing = merged[key]
                    new_perm = permission.copy()

                    # Merge conditions
                    if existing.get('conditions') and new_perm.get('conditions'):
                        # Take the most restrictive limits
                        merged_conditions = existing['conditions'].copy()
                        for cond_key, cond_value in new_perm['conditions'].items():
                            if cond_key.startswith('max_'):
                                # Take the smaller limit
                                if cond_key in merged_conditions:
                                    merged_conditions[cond_key] = min(
                                        merged_conditions[cond_key],
                                        cond_value
                                    )
                                else:
                                    merged_conditions[cond_key] = cond_value
                            else:
                                merged_conditions[cond_key] = cond_value

                        new_perm['conditions'] = merged_conditions

                    merged[key] = new_perm

        return merged

    def _evaluate_conditions(self, conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate permission conditions against context
        """
        for condition_key, condition_value in conditions.items():
            if condition_key == 'max_count':
                current_count = context.get('current_count', 0)
                if current_count >= condition_value:
                    return False

            elif condition_key == 'max_per_month':
                current_month_count = context.get('current_month_count', 0)
                if current_month_count >= condition_value:
                    return False

            elif condition_key == 'organization_only':
                if condition_value and context.get('organization_id') != context.get('user_organization_id'):
                    return False

        return True

    def _get_role_platform_permissions(self, role: SystemRole) -> List[Dict[str, Any]]:
        """Get platform permissions for a role"""
        # This would typically query role_permissions table
        return []

    def _get_role_organization_permissions(self, role: OrganizationRole) -> List[Dict[str, Any]]:
        """Get business permissions for a role"""
        # Parse permissions from role.permissions field
        if not role.permissions:
            return []

        # Assuming permissions are stored as JSON or comma-separated
        try:
            import json
            return json.loads(role.permissions) if role.permissions else []
        except:
            return role.permissions.split(',') if role.permissions else []