"""
Organization service for managing organization data and roles
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from ....models.subscriptions.organizations import Organization, OrganizationInfo, OrganizationSetup
from ....models.subscriptions.subscription_models import OrganizationRole
from ....models.users.user_location import UserLocation
from .organization_role_presets import OrganizationRolePresets


class OrganizationService:
    """
    Service for managing organization operations
    """

    def __init__(self, db: Session):
        self.db = db
        self.role_presets = OrganizationRolePresets(db)

    def get_organization_by_id(self, organization_id: int) -> Optional[Organization]:
        """Get organization by ID with organization info"""
        return self.db.query(Organization).options(
            joinedload(Organization.organization_info)
        ).filter(Organization.id == organization_id).first()

    def get_organization_roles(self, organization_id: int) -> List[Dict[str, Any]]:
        """Get all organization roles for a specific organization"""
        return self.role_presets.get_organization_roles(organization_id)

    def get_user_organization(self, user_id: int) -> Optional[Organization]:
        """Get the organization that a user belongs to"""
        user = self.db.query(UserLocation).filter(
            UserLocation.id == user_id
        ).first()

        if not user or not user.organization_id:
            return None

        return self.get_organization_by_id(user.organization_id)

    def get_organization_members(self, organization_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get members of an organization (excluding organization owners)"""
        # Exclude organization owners from member lists
        from GEPPPlatform.models.subscriptions.organizations import Organization

        members = self.db.query(UserLocation).options(
            joinedload(UserLocation.organization_role)
        ).filter(
            and_(
                UserLocation.organization_id == organization_id,
                UserLocation.is_user == True,
                UserLocation.is_active == True
            )
        ).outerjoin(Organization, Organization.owner_id == UserLocation.id).filter(
            Organization.owner_id.is_(None)
        ).limit(limit).all()

        return [
            {
                'id': member.id,
                'display_name': member.display_name,
                'email': member.email,
                'organization_role': {
                    'id': member.organization_role.id,
                    'key': member.organization_role.key,
                    'name': member.organization_role.name
                } if member.organization_role else None,
                'created_date': member.created_date.isoformat() if member.created_date else None,
                'is_active': member.is_active
            }
            for member in members
        ]

    def create_organization_member(self, organization_id: int, user_data: Dict[str, Any], created_by_user_id: int) -> UserLocation:
        """Create a new member for an organization"""
        from ..users.user_crud import UserCRUD

        # Set organization ID for the new user
        user_data['organization_id'] = organization_id

        # Create user using existing UserCRUD
        user_crud = UserCRUD(self.db)
        return user_crud.create_user(
            user_data=user_data,
            created_by_id=created_by_user_id,
            send_invitation=user_data.get('send_invitation', False)
        )

    def validate_organization_role(self, organization_id: int, role_id: int) -> bool:
        """Validate that a role ID is valid for the organization"""
        return self.role_presets.validate_role_for_organization(organization_id, role_id)

    def get_organization_info(self, organization_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed organization information"""
        org = self.get_organization_by_id(organization_id)

        if not org:
            return None

        return {
            'id': org.id,
            'name': org.name,
            'description': org.description,
            'allow_ai_audit': org.allow_ai_audit if hasattr(org, 'allow_ai_audit') else False,
            'info': {
                'company_name': org.organization_info.company_name,
                'account_type': org.organization_info.account_type,
                'business_type': org.organization_info.business_type,
                'business_industry': org.organization_info.business_industry,
                'tax_id': org.organization_info.tax_id,
            } if org.organization_info else None,
            'created_date': org.created_date.isoformat() if org.created_date else None,
            'is_active': org.is_active
        }

    def create_organization_with_default_roles(self, org_data: Dict[str, Any]) -> Organization:
        """Create a new organization and set up default roles"""
        # Create organization (this would typically be done during registration)
        # For now, this is a placeholder - organization creation happens elsewhere
        # But when it does, it should call create_default_roles_for_organization
        pass

    def ensure_default_roles_exist(self, organization_id: int) -> List:
        """Ensure default roles exist for an organization (create if missing)"""
        return self.role_presets.create_default_roles_for_organization(organization_id)

    # Organization Role CRUD operations
    def create_organization_role(self, organization_id: int, role_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a custom role for an organization"""
        role = self.role_presets.create_custom_role(organization_id, role_data)
        return {
            'id': role.id,
            'key': role.key,
            'name': role.name,
            'description': role.description,
            'is_system': role.is_system,
            'created_date': role.created_date.isoformat() if role.created_date else None
        }

    def update_organization_role(self, organization_id: int, role_id: int, role_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an organization role"""
        role = self.role_presets.update_role(organization_id, role_id, role_data)
        return {
            'id': role.id,
            'key': role.key,
            'name': role.name,
            'description': role.description,
            'is_system': role.is_system,
            'updated_date': role.updated_date.isoformat() if role.updated_date else None
        }

    def delete_organization_role(self, organization_id: int, role_id: int) -> bool:
        """Delete an organization role"""
        return self.role_presets.delete_role(organization_id, role_id)

    # Organization Setup CRUD operations
    def get_organization_setup(self, organization_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the current organization setup structure.
        Returns None if not found, or the latest version if multiple exist.
        """
        # Query for the active (current) setup for this organization
        setup = self.db.query(OrganizationSetup).filter(
            and_(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            )
        ).first()

        # If no active setup found, get the latest version
        if not setup:
            setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id
            ).order_by(OrganizationSetup.created_date.desc()).first()

        if not setup:
            return None

        return {
            'id': setup.id,
            'organization_id': setup.organization_id,
            'version': setup.version,
            'is_active': setup.is_active,
            'root_nodes': setup.root_nodes,
            'hub_node': setup.hub_node,
            'metadata': setup.setup_metadata,
            'created_date': setup.created_date.isoformat() if setup.created_date else None,
            'updated_date': setup.updated_date.isoformat() if setup.updated_date else None
        }

    def create_organization_setup(self, organization_id: int, setup_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new organization setup structure.
        This will process locations first, then deactivate any existing active setup and create a new version.
        """
        # Validate organization exists
        organization = self.get_organization_by_id(organization_id)
        if not organization:
            raise ValueError(f"Organization with ID {organization_id} not found")

        # Process locations if provided (locations can be inside treeStructure or at root level)
        location_id_mapping = {}
        locations_data = None

        # Check if locations are in the new structure (inside treeStructure)
        if 'treeStructure' in setup_data and setup_data['treeStructure'] and 'locations' in setup_data['treeStructure']:
            locations_data = setup_data['treeStructure']['locations']
            print("Found locations inside treeStructure")
        # Fallback to old structure for backward compatibility
        elif 'locations' in setup_data and setup_data['locations']:
            locations_data = setup_data['locations']
            print("Found locations at root level")

        print(f"Debug - setup_data keys: {list(setup_data.keys())}")
        if 'treeStructure' in setup_data:
            print(f"Debug - treeStructure keys: {list(setup_data['treeStructure'].keys())}")

        if locations_data:
            print(f"Processing {len(locations_data)} locations for organization {organization_id}")
            for i, loc in enumerate(locations_data[:3]):  # Show first 3 for debugging
                print(f"  Location {i+1}: nodeId={loc.get('nodeId')}, to_create={loc.get('to_create')}, display_name={loc.get('display_name')}")
            location_id_mapping = self._process_locations(organization_id, locations_data)
            print(f"Location ID mapping created: {len(location_id_mapping)} mappings")
        else:
            print("No locations data found to process")

        # Update node IDs in tree structure with new location IDs
        # Get nodes from treeStructure or fallback to root level for backward compatibility
        tree_structure = setup_data.get('treeStructure', {})
        root_nodes_data = tree_structure.get('rootNodes') or setup_data.get('root_nodes')
        hub_node_data = tree_structure.get('hubNode') or setup_data.get('hub_node')

        updated_root_nodes = self._update_node_ids_in_structure(
            root_nodes_data, location_id_mapping
        )
        updated_hub_node = self._update_node_ids_in_structure(
            hub_node_data, location_id_mapping
        )

        # Determine version number
        latest_setup = self.db.query(OrganizationSetup).filter(
            OrganizationSetup.organization_id == organization_id
        ).order_by(OrganizationSetup.created_date.desc()).first()

        # Calculate new version
        if latest_setup:
            try:
                current_version = float(latest_setup.version)
                new_version = str(current_version + 0.1)
            except (ValueError, TypeError):
                new_version = "1.1"
        else:
            new_version = "1.0"

        # Create new setup with updated node IDs
        new_setup = OrganizationSetup(
            organization_id=organization_id,
            version=setup_data.get('version', new_version),
            is_active=True,  # New setup is always active
            root_nodes=updated_root_nodes,
            hub_node=updated_hub_node,
            setup_metadata=setup_data.get('metadata', {
                'version': new_version,
                'created_at': None,  # Will be set by database
                'total_nodes': 0,
                'max_level': 0
            })
        )

        # Add and commit new setup
        # Note: The database trigger will automatically deactivate other versions
        self.db.add(new_setup)
        self.db.flush()  # Get the ID

        return {
            'id': new_setup.id,
            'organization_id': new_setup.organization_id,
            'version': new_setup.version,
            'is_active': new_setup.is_active,
            'root_nodes': new_setup.root_nodes,
            'hub_node': new_setup.hub_node,
            'metadata': new_setup.setup_metadata,
            'created_date': new_setup.created_date.isoformat() if new_setup.created_date else None,
            'updated_date': new_setup.updated_date.isoformat() if new_setup.updated_date else None,
            'location_mappings': location_id_mapping  # Include mapping info for debugging
        }

    def update_organization_setup(self, organization_id: int, setup_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update organization setup by creating a new version.
        This preserves the old version and creates a new active one.
        """
        return self.create_organization_setup(organization_id, setup_data)

    def update_ai_audit_permission(self, organization_id: int, allow_ai_audit: bool) -> Dict[str, Any]:
        """
        Update organization's AI audit permission.

        Args:
            organization_id: ID of the organization to update
            allow_ai_audit: Boolean flag to enable/disable AI audit

        Returns:
            Dict containing updated organization data

        Raises:
            ValueError: If organization not found
        """
        organization = self.db.query(Organization).filter(
            Organization.id == organization_id
        ).first()

        if not organization:
            raise ValueError(f'Organization with ID {organization_id} not found')

        # Update the allow_ai_audit field
        organization.allow_ai_audit = allow_ai_audit
        self.db.commit()
        self.db.refresh(organization)

        return {
            'organization_id': organization.id,
            'allow_ai_audit': organization.allow_ai_audit,
            'updated_at': organization.updated_date.isoformat() if organization.updated_date else None
        }

    def _process_locations(self, organization_id: int, locations: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Process location data - create new locations and update existing ones.
        Only create locations with string-based nodeIds. Numeric nodeIds represent existing locations.
        Returns a mapping of old nodeId to new database ID.
        """
        location_id_mapping = {}
        print(f"_process_locations called with {len(locations)} locations")

        for location_data in locations:
            node_id = location_data.get('nodeId')
            to_create = location_data.get('to_create', True)
            display_name = location_data.get('display_name')
            users = location_data.get('users', [])

            print(f"Processing location: nodeId={node_id}, to_create={to_create}, display_name={display_name}, users={users}")

            # Check if nodeId is numeric (existing location) or string (new location)
            is_numeric_id = self._is_numeric_id(node_id)

            if is_numeric_id:
                # This is an existing location with numeric database ID - update if any changes provided
                existing_location = self.db.query(UserLocation).filter(UserLocation.id == node_id).first()
                if existing_location:
                    updated = False

                    # Update members if users provided (including empty array for removal)
                    if users is not None:
                        existing_location.members = users
                        updated = True
                        print(f"  Updated existing location {node_id} with members: {users}")

                    # Update display_name and name_en if provided
                    if display_name:
                        # Check for duplicate destination names if this is a hub/destination
                        if existing_location.hub_type and display_name != existing_location.display_name:
                            from sqlalchemy import or_
                            duplicate = self.db.query(UserLocation).filter(
                                UserLocation.organization_id == organization_id,
                                UserLocation.hub_type.isnot(None),
                                UserLocation.deleted_date.is_(None),
                                UserLocation.id != int(node_id),  # Exclude the current location
                                or_(
                                    UserLocation.display_name == display_name,
                                    UserLocation.name_en == display_name
                                )
                            ).first()
                            if duplicate:
                                raise ValueError(f'Destination name "{display_name}" already exists in this organization. Please use a different name.')
                        
                        existing_location.display_name = display_name
                        existing_location.name_en = display_name  # Also update name_en
                        updated = True
                        print(f"  Updated existing location {node_id} with display_name and name_en: {display_name}")

                    if updated:
                        self.db.flush()
                continue

            # Only process string-based IDs (new locations)
            if to_create and not is_numeric_id:
                # Check for duplicate destination names if this is a hub/destination
                hub_type = location_data.get('hub_type')
                if hub_type and display_name:
                    # Check if a destination with the same name already exists in this organization
                    from sqlalchemy import or_
                    existing_destination = self.db.query(UserLocation).filter(
                        UserLocation.organization_id == organization_id,
                        UserLocation.hub_type.isnot(None),
                        UserLocation.deleted_date.is_(None),
                        or_(
                            UserLocation.display_name == display_name,
                            UserLocation.name_en == display_name
                        )
                    ).first()
                    if existing_destination:
                        raise ValueError(f'Destination name "{display_name}" already exists in this organization. Please use a different name.')
                
                # Create new location
                new_location = UserLocation(
                    display_name=location_data.get('display_name'),
                    name_en=location_data.get('name_en'),
                    name_th=location_data.get('name_th'),
                    email=location_data.get('email'),
                    phone=location_data.get('phone'),
                    platform=location_data.get('platform', 'GEPP_BUSINESS_WEB'),
                    organization_id=organization_id,
                    is_active=location_data.get('is_active', True),
                    is_location=location_data.get('is_location', True),
                    is_user=location_data.get('is_user', False),
                    type=location_data.get('type'),  # Location type (branch, building, floor, room, hub, etc.)
                    hub_type=location_data.get('hub_type'),  # Hub type from hubData.type
                    members=location_data.get('users', [])  # Store user assignments in members column
                )

                print(f"  Creating new location: {display_name}")
                self.db.add(new_location)
                self.db.flush()  # Get the auto-generated ID

                # Map the old string nodeId to the new database ID
                location_id_mapping[str(node_id)] = str(new_location.id)
                print(f"  Created location with ID: {new_location.id}, mapped {node_id} -> {new_location.id}")

            elif not to_create and not is_numeric_id:
                # Update existing location (should be rare, but handle gracefully)
                print(f"  Warning: String nodeId {node_id} with to_create=false - treating as new location")
                # Treat as new location since string IDs should not exist in database

        print(f"Final location_id_mapping: {location_id_mapping}")
        return location_id_mapping

    def _is_numeric_id(self, node_id) -> bool:
        """
        Check if a nodeId is numeric (existing location) or string-based (new location).
        """
        try:
            if isinstance(node_id, (int, float)):
                return True
            if isinstance(node_id, str):
                # Try to convert to int - if successful, it's numeric
                int(node_id)
                return True
            return False
        except (ValueError, TypeError):
            return False

    def _update_node_ids_in_structure(self, structure: Any, id_mapping: Dict[str, str]) -> Any:
        """
        Recursively update nodeIds in tree structure with new database IDs.
        Only updates string-based nodeIds that are in the mapping. Leaves numeric nodeIds unchanged.
        """
        if structure is None:
            return structure

        if isinstance(structure, dict):
            updated_structure = {}
            for key, value in structure.items():
                if key == 'nodeId':
                    # Only update if the value is in the mapping (string-based new locations)
                    # Numeric IDs (existing locations) should remain unchanged
                    if str(value) in id_mapping:
                        # Replace string nodeId with new database ID
                        updated_structure[key] = int(id_mapping[str(value)])  # Convert back to int for consistency
                        print(f"  Updated nodeId: {value} -> {updated_structure[key]}")
                    else:
                        # Keep original value (likely numeric ID for existing location)
                        updated_structure[key] = value
                elif key == 'parentNodeId':
                    # Only update if the value is in the mapping
                    if str(value) in id_mapping:
                        # Replace string parentNodeId with new database ID
                        updated_structure[key] = int(id_mapping[str(value)])  # Convert back to int for consistency
                        print(f"  Updated parentNodeId: {value} -> {updated_structure[key]}")
                    else:
                        # Keep original value (likely numeric ID for existing location)
                        updated_structure[key] = value
                else:
                    # Recursively process nested structures
                    updated_structure[key] = self._update_node_ids_in_structure(value, id_mapping)
            return updated_structure

        elif isinstance(structure, list):
            # Process each item in the list
            return [self._update_node_ids_in_structure(item, id_mapping) for item in structure]

        else:
            # Return primitive values as-is
            return structure