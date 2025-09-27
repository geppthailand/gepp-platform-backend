"""
Organization role presets and management
"""

from typing import List, Dict, Any
from sqlalchemy.orm import Session

from ....models.subscriptions.subscription_models import OrganizationRole, OrganizationPermission


class OrganizationRolePresets:
    """
    Manages organization role presets and creation
    """

    # Default role presets for new organizations
    DEFAULT_ROLES = [
        {
            'key': 'admin',
            'name': 'Administrator',
            'description': 'Full administrative access to organization',
            'is_system': True,
            'permissions': ['*']  # All permissions
        },
        {
            'key': 'data_input',
            'name': 'Data Input Specialist',
            'description': 'Can input and manage transaction data',
            'is_system': True,
            'permissions': ['transactions.create', 'transactions.edit', 'locations.view']
        },
        {
            'key': 'auditor',
            'name': 'Auditor',
            'description': 'Can review and audit data, read-only access to reports',
            'is_system': True,
            'permissions': ['transactions.view', 'reports.view', 'audit.access']
        },
        {
            'key': 'viewer',
            'name': 'Viewer',
            'description': 'Read-only access to organizational data',
            'is_system': True,
            'permissions': ['transactions.view', 'locations.view']
        }
    ]

    def __init__(self, db: Session):
        self.db = db

    def create_default_roles_for_organization(self, organization_id: int) -> List[OrganizationRole]:
        """
        Create default roles for a new organization
        """
        created_roles = []

        for role_preset in self.DEFAULT_ROLES:
            # Check if role already exists
            existing_role = self.db.query(OrganizationRole).filter(
                OrganizationRole.organization_id == organization_id,
                OrganizationRole.key == role_preset['key']
            ).first()

            if existing_role:
                continue  # Skip if already exists

            # Create the role
            role = OrganizationRole(
                organization_id=organization_id,
                key=role_preset['key'],
                name=role_preset['name'],
                description=role_preset['description'],
                is_system=role_preset['is_system']
            )

            self.db.add(role)
            self.db.flush()  # Get the ID

            # TODO: Add permissions when OrganizationPermission system is implemented
            # For now, we'll store permissions as metadata or implement later

            created_roles.append(role)

        return created_roles

    def get_organization_roles(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        Get all roles for a specific organization
        """
        roles = self.db.query(OrganizationRole).filter(
            OrganizationRole.organization_id == organization_id,
            OrganizationRole.is_active == True
        ).all()

        return [
            {
                'id': role.id,
                'key': role.key,
                'name': role.name,
                'description': role.description,
                'is_system': role.is_system,
                'created_date': role.created_date.isoformat() if role.created_date else None,
                'permissions': self._get_role_permissions(role.id)
            }
            for role in roles
        ]

    def create_custom_role(self, organization_id: int, role_data: Dict[str, Any]) -> OrganizationRole:
        """
        Create a custom role for an organization
        """
        # Validate required fields
        required_fields = ['key', 'name']
        for field in required_fields:
            if field not in role_data:
                raise ValueError(f"Missing required field: {field}")

        # Check if role key already exists in organization
        existing_role = self.db.query(OrganizationRole).filter(
            OrganizationRole.organization_id == organization_id,
            OrganizationRole.key == role_data['key']
        ).first()

        if existing_role:
            raise ValueError(f"Role with key '{role_data['key']}' already exists in organization")

        # Create the role
        role = OrganizationRole(
            organization_id=organization_id,
            key=role_data['key'],
            name=role_data['name'],
            description=role_data.get('description', ''),
            is_system=False  # Custom roles are never system roles
        )

        self.db.add(role)
        self.db.commit()

        return role

    def update_role(self, organization_id: int, role_id: int, role_data: Dict[str, Any]) -> OrganizationRole:
        """
        Update an existing role (only custom roles can be fully updated)
        """
        role = self.db.query(OrganizationRole).filter(
            OrganizationRole.id == role_id,
            OrganizationRole.organization_id == organization_id
        ).first()

        if not role:
            raise ValueError("Role not found")

        # System roles can only have description updated
        if role.is_system:
            if 'description' in role_data:
                role.description = role_data['description']
        else:
            # Custom roles can be fully updated
            if 'key' in role_data:
                # Check for key conflicts
                existing_role = self.db.query(OrganizationRole).filter(
                    OrganizationRole.organization_id == organization_id,
                    OrganizationRole.key == role_data['key'],
                    OrganizationRole.id != role_id
                ).first()

                if existing_role:
                    raise ValueError(f"Role with key '{role_data['key']}' already exists")

                role.key = role_data['key']

            if 'name' in role_data:
                role.name = role_data['name']

            if 'description' in role_data:
                role.description = role_data['description']

        self.db.commit()
        return role

    def delete_role(self, organization_id: int, role_id: int) -> bool:
        """
        Delete a role (only custom roles can be deleted)
        """
        role = self.db.query(OrganizationRole).filter(
            OrganizationRole.id == role_id,
            OrganizationRole.organization_id == organization_id
        ).first()

        if not role:
            raise ValueError("Role not found")

        if role.is_system:
            raise ValueError("System roles cannot be deleted")

        # Check if role is in use
        from ....models.users.user_location import UserLocation
        users_with_role = self.db.query(UserLocation).filter(
            UserLocation.organization_role_id == role_id
        ).count()

        if users_with_role > 0:
            raise ValueError(f"Cannot delete role: {users_with_role} users are assigned to this role")

        # Soft delete
        role.is_active = False
        self.db.commit()

        return True

    def _get_role_permissions(self, role_id: int) -> List[Dict[str, Any]]:
        """
        Get permissions for a role (placeholder for future implementation)
        """
        # TODO: Implement when permission system is fully defined
        return []

    def validate_role_for_organization(self, organization_id: int, role_id: int) -> bool:
        """
        Validate that a role belongs to the specified organization
        """
        role = self.db.query(OrganizationRole).filter(
            OrganizationRole.id == role_id,
            OrganizationRole.organization_id == organization_id,
            OrganizationRole.is_active == True
        ).first()

        return role is not None