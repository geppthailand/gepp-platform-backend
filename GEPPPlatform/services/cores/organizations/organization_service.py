"""
Organization service for managing organization data and roles
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, text

from ....models.subscriptions.organizations import Organization, OrganizationInfo, OrganizationSetup
from ....models.subscriptions.subscription_models import OrganizationRole
from ....models.users.user_location import UserLocation
from ....exceptions import ValidationException
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
            'ai_audit_rule_set_id': org.ai_audit_rule_set_id if hasattr(org, 'ai_audit_rule_set_id') else None,
            'enable_ai_audit_response_setting': org.enable_ai_audit_response_setting if hasattr(org, 'enable_ai_audit_response_setting') else False,
            'enable_ai_audit_api': org.enable_ai_audit_api if hasattr(org, 'enable_ai_audit_api') else False,
            'info': {
                'company_name': org.organization_info.company_name,
                'account_type': org.organization_info.account_type,
                'business_type': org.organization_info.business_type,
                'business_industry': org.organization_info.business_industry,
                'tax_id': org.organization_info.tax_id,
            } if org.organization_info else None,
            'created_date': org.created_date.isoformat() if org.created_date else None,
            'is_active': org.is_active,
            'max_org_structure_nodes': org.max_org_structure_nodes if hasattr(org, 'max_org_structure_nodes') else 50,
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
            'branch_level_name': setup.branch_level_name,
            'building_level_name': setup.building_level_name,
            'floor_level_name': setup.floor_level_name,
            'room_level_name': setup.room_level_name,
            'input_destination': bool(setup.input_destination),
            'show_all_location_options': bool(setup.show_all_location_options) if setup.show_all_location_options is not None else True,
            'created_date': setup.created_date.isoformat() if setup.created_date else None,
            'updated_date': setup.updated_date.isoformat() if setup.updated_date else None
        }

    def get_organization_setup_filtered(self, organization_id: int, current_user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get organization setup with 3-tier tree pruning.
        - Assigned nodes: kept as-is
        - Ancestor nodes: kept with is_ancestor=True annotation
        - Unseen nodes: pruned entirely

        For sub-users in large orgs, this avoids sending the full org tree —
        only the nodes the user is allowed to see are returned. Tier resolution
        runs against a lightweight ``(id, members)`` projection so we don't
        full-load every UserLocation row just to compute visibility.
        """
        setup = self.get_organization_setup(organization_id)
        if not setup:
            return setup

        # Get tiers from user_service
        from ..users.user_service import UserService
        from types import SimpleNamespace

        user_service = UserService(self.db)

        # _resolve_location_tiers reads only `id` and `members` per location,
        # so a 2-column projection is enough. This is the same pattern used by
        # user_service.get_locations() to keep large orgs responsive.
        light_rows = self.db.query(UserLocation.id, UserLocation.members).filter(
            UserLocation.is_location == True,
            UserLocation.is_active == True,
            UserLocation.deleted_date.is_(None),  # skip soft-deleted rows
            UserLocation.organization_id == organization_id,
        ).all()
        light_locs = [SimpleNamespace(id=r.id, members=r.members) for r in light_rows]

        tiers = user_service._resolve_location_tiers(light_locs, organization_id, current_user_id)

        if tiers['is_owner']:
            return setup

        visible_ids = tiers['assigned_ids'] | tiers['ancestor_ids']
        ancestor_ids = tiers['ancestor_ids']

        def prune_tree(nodes):
            if not nodes:
                return []
            result = []
            for node in nodes:
                nid = int(node.get('nodeId', 0))
                if nid not in visible_ids:
                    continue
                pruned = dict(node)
                if 'children' in pruned:
                    pruned['children'] = prune_tree(pruned['children'])
                if nid in ancestor_ids:
                    pruned['is_ancestor'] = True
                result.append(pruned)
            return result

        setup['root_nodes'] = prune_tree(setup.get('root_nodes') or [])

        # Also prune hub_node children
        hub_node = setup.get('hub_node')
        if hub_node and isinstance(hub_node, dict):
            hub_children = hub_node.get('children', [])
            if hub_children:
                pruned_hub = dict(hub_node)
                pruned_hub['children'] = prune_tree(hub_children)
                setup['hub_node'] = pruned_hub

        return setup

    def _merge_tree_nodes(self, full_nodes: list, partial_nodes: list,
                          allow_new_siblings: bool = True) -> list:
        """
        Merge a partial tree (from a non-owner user) into the full existing tree.
        Nodes present in partial_nodes update the corresponding node in full_nodes.
        Nodes only in full_nodes (unseen by user) are preserved as-is.
        Nodes only in partial_nodes (newly created by user) are appended.

        Args:
            allow_new_siblings: when ``False``, partial-only nodes at THIS level
                are rejected. Used at the outermost root_nodes merge for
                non-owners — sub-users can add children under nodes they can
                see, but they cannot create brand-new top-level branches.
                Recursive calls always pass ``True`` because deeper levels are
                where legitimate new-child additions live.
        """
        if not full_nodes:
            # When the user has no full tree at this level, only allow the
            # partial nodes through if they're permitted as siblings at this
            # depth. For non-owners at the root this would normally be a
            # corruption indicator (see merge call below) so we drop them.
            if not allow_new_siblings:
                return []
            return partial_nodes or []
        if not partial_nodes:
            return full_nodes

        # Index partial nodes by nodeId for fast lookup
        partial_map = {}
        for node in partial_nodes:
            nid = str(node.get('nodeId', ''))
            if nid:
                partial_map[nid] = node

        merged = []
        seen_ids = set()

        for full_node in full_nodes:
            nid = str(full_node.get('nodeId', ''))
            if nid in partial_map:
                # User can see this node — use user's version but recurse into children
                user_node = partial_map[nid]
                merged_node = dict(user_node)
                # Recursively merge children — deeper levels always allow new
                # additions (that's how a sub-user adds a child under their
                # assigned node).
                full_children = full_node.get('children') or []
                user_children = user_node.get('children') or []
                merged_node['children'] = self._merge_tree_nodes(
                    full_children, user_children, allow_new_siblings=True
                )
                merged.append(merged_node)
                seen_ids.add(nid)
            else:
                # User cannot see this node — preserve it entirely from full tree
                merged.append(full_node)
                seen_ids.add(nid)

        # Append any new nodes from partial that don't exist in full (newly created)
        if allow_new_siblings:
            for node in partial_nodes:
                nid = str(node.get('nodeId', ''))
                if nid and nid not in seen_ids:
                    merged.append(node)
        else:
            # Drop any orphan top-level nodes the partial tree tried to inject.
            # This is what was producing "Node-undefined" boxes at the root for
            # sub-user submissions — the frontend was sending the new node at
            # the wrong nesting depth, and the merge dutifully appended it
            # next to the real branches.
            for node in partial_nodes:
                nid = str(node.get('nodeId', ''))
                if nid and nid not in seen_ids:
                    print(
                        f"  Drop orphan partial root node nodeId={nid} "
                        f"(non-owner cannot create root-level branches)"
                    )

        return merged

    def _splice_new_nodes_by_parent_ref(
        self,
        root_nodes: list,
        locations_data: list,
        id_mapping: Dict[str, str],
    ) -> list:
        """
        For each newly-created location, ensure it sits under its declared
        ``parentNodeId`` in the tree. Idempotent: nodes that are already
        nested correctly are left alone. Newly-created locations whose
        parent isn't anywhere in the tree are skipped (we don't invent
        new top-level branches).
        """
        if not locations_data or not id_mapping:
            return root_nodes

        # Index the (possibly empty) tree by stringified nodeId.
        nodes_by_id: Dict[str, Dict[str, Any]] = {}

        def index_tree(nodes: Any):
            if not isinstance(nodes, list):
                return
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                nid = node.get('nodeId')
                if nid is not None:
                    nodes_by_id[str(nid)] = node
                children = node.get('children')
                if children:
                    index_tree(children)

        index_tree(root_nodes)

        for loc in locations_data:
            if not isinstance(loc, dict):
                continue

            # Only splice nodes we just created (their original nodeId is in
            # the temp→real mapping). Existing locations are already at
            # whatever position the user dragged them to.
            original_node_id = loc.get('nodeId')
            mapped = id_mapping.get(str(original_node_id))
            if mapped is None:
                continue
            try:
                new_real_id = int(mapped)
            except (ValueError, TypeError):
                continue

            # If the node is already in the tree somewhere, leave it.
            if str(new_real_id) in nodes_by_id:
                continue

            parent_raw = loc.get('parentNodeId')
            if parent_raw is None:
                continue

            # parentNodeId might be a real numeric ID or a temp string that
            # was just mapped to a new ID in this same request.
            mapped_parent = id_mapping.get(str(parent_raw))
            try:
                parent_real_id = int(mapped_parent) if mapped_parent is not None else int(parent_raw)
            except (ValueError, TypeError):
                continue

            parent_node = nodes_by_id.get(str(parent_real_id))
            if parent_node is None:
                continue  # parent isn't in the visible/persisted tree

            new_node_obj: Dict[str, Any] = {'nodeId': new_real_id}
            children_from_loc = loc.get('children')
            if isinstance(children_from_loc, list) and children_from_loc:
                new_node_obj['children'] = children_from_loc

            parent_node.setdefault('children', []).append(new_node_obj)
            nodes_by_id[str(new_real_id)] = new_node_obj
            print(
                f"  Splice new node {new_real_id} under parent {parent_real_id} "
                f"(reconciled from locations[].parentNodeId)"
            )

        return root_nodes

    def _count_tree_nodes(self, nodes: Any) -> int:
        """Count total nodes in a tree structure for sanity checking."""
        if not nodes:
            return 0
        if isinstance(nodes, dict):
            count = 1
            for child in (nodes.get('children') or []):
                count += self._count_tree_nodes(child)
            return count
        if isinstance(nodes, list):
            return sum(self._count_tree_nodes(n) for n in nodes)
        return 0

    def create_organization_setup(self, organization_id: int, setup_data: Dict[str, Any], current_user_id: int = None) -> Dict[str, Any]:
        """
        Create a new organization setup structure.
        This will process locations first, then deactivate any existing active setup and create a new version.

        If current_user_id is provided and the user is NOT the org owner, the incoming
        (possibly pruned) tree is merged into the existing full tree so that unseen nodes
        are preserved.
        """
        # Validate organization exists
        organization = self.get_organization_by_id(organization_id)
        if not organization:
            raise ValueError(f"Organization with ID {organization_id} not found")

        # Determine if user is org owner
        is_owner = True
        if current_user_id is not None:
            is_owner = (organization.owner_id == current_user_id)

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

        # --- Non-owner protection: merge partial tree into full existing tree ---
        if not is_owner:
            existing_setup = self.get_organization_setup(organization_id)
            if existing_setup:
                existing_root = existing_setup.get('root_nodes') or []
                existing_hub = existing_setup.get('hub_node') or {}

                # Count nodes before merge for sanity check
                existing_root_count = self._count_tree_nodes(existing_root)
                incoming_root_count = self._count_tree_nodes(updated_root_nodes)

                # Merge root_nodes — non-owners cannot create new top-level
                # branches, so partial-only nodes at the root are dropped.
                # New nodes the user added under nodes they can see show up
                # one level deeper and are merged normally there.
                if updated_root_nodes is not None:
                    updated_root_nodes = self._merge_tree_nodes(
                        existing_root, updated_root_nodes,
                        allow_new_siblings=False,
                    )

                # Merge hub_node children — same root-level restriction:
                # sub-users cannot mint new hub children, only edit ones they see.
                if updated_hub_node and isinstance(updated_hub_node, dict):
                    existing_hub_children = (existing_hub.get('children') or []) if isinstance(existing_hub, dict) else []
                    incoming_hub_children = updated_hub_node.get('children') or []
                    updated_hub_node['children'] = self._merge_tree_nodes(
                        existing_hub_children, incoming_hub_children,
                        allow_new_siblings=False,
                    )
                elif existing_hub:
                    # User sent no hub data — preserve existing
                    updated_hub_node = existing_hub

                # Count total nodes (root + hub) for sanity check
                existing_hub_count = self._count_tree_nodes(existing_hub.get('children')) if isinstance(existing_hub, dict) else 0
                merged_root_count = self._count_tree_nodes(updated_root_nodes)
                merged_hub_count = self._count_tree_nodes(updated_hub_node.get('children')) if isinstance(updated_hub_node, dict) else 0

                existing_total = existing_root_count + existing_hub_count
                merged_total = merged_root_count + merged_hub_count

                print(f"[Tree Merge] Non-owner save by user {current_user_id}: "
                      f"existing={existing_total} nodes (root={existing_root_count}, hub={existing_hub_count}), "
                      f"merged={merged_total} nodes (root={merged_root_count}, hub={merged_hub_count})")

                # Safety: merged tree should never have fewer total nodes than existing
                if merged_total < existing_total:
                    print(f"[Tree Merge] WARNING: Merged tree has fewer nodes ({merged_total}) "
                          f"than existing ({existing_total}). Aborting save to prevent data loss.")
                    raise ValueError(
                        f"Save rejected: merged tree would lose {existing_total - merged_total} nodes. "
                        f"Please refresh and try again."
                    )

        # --- Reconcile new nodes against parentNodeId from the flat locations array ---
        # The frontend ships the tree in two parallel forms (nested rootNodes
        # vs flat locations[] with parentNodeId). Sub-users sometimes end up
        # with a nested form where a freshly-added node sits at the root
        # instead of under the assigned parent — and the merge step (or our
        # ``allow_new_siblings=False`` guard) then drops or mis-places it.
        # The flat form is reliable, so we use parentNodeId here to splice
        # any newly-created locations into the correct parent's children.
        if location_id_mapping:
            updated_root_nodes = self._splice_new_nodes_by_parent_ref(
                updated_root_nodes or [], locations_data or [], location_id_mapping
            )
            if updated_hub_node and isinstance(updated_hub_node, dict):
                hub_children = updated_hub_node.get('children') or []
                updated_hub_node['children'] = self._splice_new_nodes_by_parent_ref(
                    hub_children, locations_data or [], location_id_mapping
                )

        # --- Enforce max_org_structure_nodes limit ---
        max_nodes = getattr(organization, 'max_org_structure_nodes', 50) or 50
        root_count = self._count_tree_nodes(updated_root_nodes)
        hub_count = 0
        if updated_hub_node and isinstance(updated_hub_node, dict):
            hub_count = 1  # hub-main itself
            hub_count += self._count_tree_nodes(updated_hub_node.get('children'))
        total_nodes = root_count + hub_count
        if total_nodes > max_nodes:
            raise ValueError(
                f"Node limit exceeded: the tree contains {total_nodes} nodes "
                f"but the maximum allowed is {max_nodes}. "
                f"Please reduce the number of nodes before saving."
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
            }),
            branch_level_name=setup_data.get('branch_level_name'),
            building_level_name=setup_data.get('building_level_name'),
            floor_level_name=setup_data.get('floor_level_name'),
            room_level_name=setup_data.get('room_level_name'),
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
            'branch_level_name': new_setup.branch_level_name,
            'building_level_name': new_setup.building_level_name,
            'floor_level_name': new_setup.floor_level_name,
            'room_level_name': new_setup.room_level_name,
            'created_date': new_setup.created_date.isoformat() if new_setup.created_date else None,
            'updated_date': new_setup.updated_date.isoformat() if new_setup.updated_date else None,
            'location_mappings': location_id_mapping  # Include mapping info for debugging
        }

    def update_organization_setup(self, organization_id: int, setup_data: Dict[str, Any], current_user_id: int = None) -> Dict[str, Any]:
        """
        Update organization setup by creating a new version.
        This preserves the old version and creates a new active one.
        """
        return self.create_organization_setup(organization_id, setup_data, current_user_id=current_user_id)

    def update_organization_setup_level_names(self, organization_id: int, level_names: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update only the level naming fields on the current active organization setup
        without creating a new version.
        """
        setup = self.db.query(OrganizationSetup).filter(
            and_(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            )
        ).first()

        if not setup:
            raise ValueError('No active organization setup found')

        for key in ('branch_level_name', 'building_level_name', 'floor_level_name', 'room_level_name'):
            if key in level_names:
                setattr(setup, key, level_names[key])

        # General-settings scalar toggles persisted on the same active setup (no new version).
        if 'input_destination' in level_names:
            setup.input_destination = bool(level_names['input_destination'])
        if 'show_all_location_options' in level_names:
            setup.show_all_location_options = bool(level_names['show_all_location_options'])

        # Persist — flush alone left the change uncommitted (rolled back at request end), so the
        # toggle reverted on refresh. Mirror update_ai_audit_permission which commits directly.
        self.db.commit()
        self.db.refresh(setup)

        return {
            'id': setup.id,
            'organization_id': setup.organization_id,
            'version': setup.version,
            'is_active': setup.is_active,
            'root_nodes': setup.root_nodes,
            'hub_node': setup.hub_node,
            'metadata': setup.setup_metadata,
            'branch_level_name': setup.branch_level_name,
            'building_level_name': setup.building_level_name,
            'floor_level_name': setup.floor_level_name,
            'room_level_name': setup.room_level_name,
            'input_destination': bool(setup.input_destination),
            'show_all_location_options': bool(setup.show_all_location_options) if setup.show_all_location_options is not None else True,
            'created_date': setup.created_date.isoformat() if setup.created_date else None,
            'updated_date': setup.updated_date.isoformat() if setup.updated_date else None
        }

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

    def upsert_notification_settings(self, organization_id: int, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create or update organization_notification_settings from a list of items.
        Each item: organization_id, event, role (organization_roles.key), channels_mask, email_time, is_active.
        """
        if not items:
            return []

        created = []
        for item in items:
            org_id = item.get('organization_id')
            if org_id is None:
                raise ValidationException('organization_id is required in each item', errors=['organization_id'])
            if int(org_id) != organization_id:
                raise ValidationException(
                    f'All items must belong to organization {organization_id}; got organization_id {org_id}',
                    errors=['organization_id']
                )
            event = item.get('event')
            if not event:
                raise ValidationException('event is required in each item', errors=['event'])
            role_key = item.get('role')
            if not role_key:
                raise ValidationException('role is required in each item', errors=['role'])

            role_id = self.role_presets.get_role_id_by_key(organization_id, str(role_key).strip().lower())
            if role_id is None:
                raise ValidationException(
                    f'Unknown role "{role_key}" for organization {organization_id}. Use organization_roles.key (e.g. admin, data_input, auditor, viewer).',
                    errors=['role']
                )

            channels_mask = int(item.get('channels_mask', 0))
            email_time = item.get('email_time')  # "08:00" or None
            if email_time is not None:
                email_time = str(email_time).strip()
            is_active = item.get('is_active', True)
            if isinstance(is_active, str):
                is_active = is_active.lower() in ('true', '1', 'yes')
            is_active = bool(is_active)

            self.db.execute(
                text("""
                    INSERT INTO organization_notification_settings
                        (organization_id, event, role_id, channels_mask, email_time, is_active, updated_date)
                    VALUES (:org_id, :event, :role_id, :channels_mask, :email_time, :is_active, NOW())
                    ON CONFLICT (organization_id, event, role_id) DO UPDATE SET
                        channels_mask = EXCLUDED.channels_mask,
                        email_time = EXCLUDED.email_time,
                        is_active = EXCLUDED.is_active,
                        updated_date = NOW(),
                        deleted_date = NULL
                """),
                {
                    'org_id': organization_id,
                    'event': event,
                    'role_id': role_id,
                    'channels_mask': channels_mask,
                    'email_time': email_time or None,
                    'is_active': is_active,
                }
            )
            created.append({
                'organization_id': organization_id,
                'event': event,
                'role': role_key,
                'role_id': role_id,
                'channels_mask': channels_mask,
                'email_time': email_time,
                'is_active': is_active,
            })
        self.db.flush()
        return created

    def get_notification_settings(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        Get organization notification settings in the same shape as upsert input/output.
        Returns list of items: organization_id, event, role (key), role_id, channels_mask, email_time, is_active.
        """
        result = self.db.execute(
            text("""
                SELECT ons.organization_id, ons.event, oroles.key AS role_key, ons.role_id,
                       ons.channels_mask, ons.email_time, ons.is_active
                FROM organization_notification_settings ons
                JOIN organization_roles oroles ON oroles.id = ons.role_id
                WHERE ons.organization_id = :org_id AND ons.deleted_date IS NULL
                ORDER BY ons.event, oroles.key
            """),
            {'org_id': organization_id}
        )
        rows = result.fetchall()
        data = []
        for row in rows:
            email_time = row.email_time
            if email_time is not None:
                # time type: format as "HH:MM"
                email_time = str(email_time)[:5] if hasattr(email_time, '__str__') else email_time
            data.append({
                'organization_id': row.organization_id,
                'event': row.event,
                'role': row.role_key,
                'role_id': row.role_id,
                'channels_mask': row.channels_mask,
                'email_time': email_time,
                'is_active': row.is_active,
            })
        return data

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
            # Only get users if explicitly provided in location_data (don't default to [])
            has_users_field = 'users' in location_data
            users = location_data.get('users') if has_users_field else None

            print(f"Processing location: nodeId={node_id}, to_create={to_create}, display_name={display_name}, has_users={has_users_field}, type={location_data.get('type')}")

            # Check if nodeId is numeric (existing location) or string (new location)
            is_numeric_id = self._is_numeric_id(node_id)

            # Cast to int up-front so SQLAlchemy compares ``id`` (bigint) against
            # an int instead of letting Postgres cast the string itself and
            # potentially overflow.
            node_id_int = None
            if is_numeric_id:
                try:
                    node_id_int = int(node_id)
                    # bigint range guard — anything outside this can't possibly
                    # match an existing row, so fall through to the create path.
                    if node_id_int < 1 or node_id_int > 9_223_372_036_854_775_807:
                        node_id_int = None
                        is_numeric_id = False
                except (ValueError, TypeError):
                    node_id_int = None
                    is_numeric_id = False

            if is_numeric_id:
                # This is an existing location with numeric database ID - update if any changes provided
                existing_location = self.db.query(UserLocation).filter(UserLocation.id == node_id_int).first()
                if existing_location:
                    updated = False

                    # Update members only if users field was explicitly provided
                    if has_users_field and users is not None:
                        existing_location.members = users
                        updated = True
                        print(f"  Updated existing location {node_id} with members: {users}")

                    # Update materials only if the field was explicitly provided (a list).
                    # The tree carries each node's materials from load, so this is idempotent
                    # for untouched nodes and applies the new selection for edited ones.
                    if 'materials' in location_data and isinstance(location_data.get('materials'), list):
                        existing_location.materials = location_data['materials']
                        updated = True
                        print(f"  Updated existing location {node_id} with materials: {location_data['materials']}")

                    # Update display_name and name_en if provided
                    if display_name:
                        # Check for duplicate destination names if this is a hub/destination
                        if existing_location.hub_type and display_name != existing_location.display_name:
                            from sqlalchemy import or_
                            duplicate = self.db.query(UserLocation).filter(
                                UserLocation.organization_id == organization_id,
                                UserLocation.hub_type.isnot(None),
                                UserLocation.deleted_date.is_(None),
                                UserLocation.id != node_id_int,  # Exclude the current location
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

                    # Update type if provided (for drag-and-drop reparenting)
                    location_type = location_data.get('type')
                    if location_type and location_type != existing_location.type:
                        old_type = existing_location.type
                        existing_location.type = location_type
                        updated = True
                        print(f"  Updated existing location {node_id} type: {old_type} -> {location_type}")

                    if updated:
                        self.db.flush()
                continue

            # Only process string-based IDs (new locations)
            if to_create and not is_numeric_id:
                # Reject placeholder/ghost rows up-front: a new location with no
                # usable name field is almost certainly a UI affordance (an
                # empty "+ add child" slot) that leaked into the locations
                # array. Persisting it produces "Node-undefined" boxes that
                # then attach to the wrong place via the merge path.
                _name_th = location_data.get('name_th')
                _name_en = location_data.get('name_en')
                if not (display_name or _name_th or _name_en):
                    print(f"  Skip placeholder location with no name: nodeId={node_id}")
                    continue

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
                    members=location_data.get('users', []),  # Store user assignments in members column
                    address=location_data.get('address'),  # Address of the location
                    materials=location_data.get('materials') or [],  # Material IDs assigned to this location
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

        Note: must use a strict digits-only check rather than ``int(s)`` —
        Python 3.6+ accepts ``_`` as a digit separator, so ``int("12933_1778147882242_12023")``
        silently parses the frontend's temp ID format ``<parent>_<ts>_<rand>``
        as a single huge integer, then later overflows Postgres' ``bigint``
        in queries like ``WHERE user_locations.id = <temp_id>``.
        """
        if isinstance(node_id, bool):
            return False  # bool is a subclass of int; treat explicitly
        if isinstance(node_id, int):
            return True
        if isinstance(node_id, float):
            return float(node_id).is_integer()
        if isinstance(node_id, str):
            s = node_id.strip()
            return bool(s) and s.isdigit()
        return False

    def _update_node_ids_in_structure(self, structure: Any, id_mapping: Dict[str, str]) -> Any:
        """
        Recursively update nodeIds in tree structure with new database IDs.
        Only updates string-based nodeIds that are in the mapping. Leaves numeric nodeIds unchanged.

        Drops any node whose ``nodeId`` is a non-numeric string AND not present
        in ``id_mapping`` — those represent temp IDs whose corresponding
        location row was rejected (e.g. placeholder rows skipped in
        _process_locations). Persisting them would leave the tree referencing
        non-existent IDs and produce "Node-undefined" stragglers.
        """
        if structure is None:
            return structure

        if isinstance(structure, dict):
            # If this dict has a nodeId that's a string AND not in the mapping,
            # drop the whole subtree so its (now non-existent) row doesn't stay
            # referenced in the tree.
            node_id_val = structure.get('nodeId')
            if isinstance(node_id_val, str):
                stripped = node_id_val.strip()
                if stripped and not stripped.isdigit() and stripped not in id_mapping:
                    print(f"  Drop unmapped tree node: nodeId={node_id_val} (location was skipped or never created)")
                    return None

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
            # Process each item in the list, filtering out dropped (None) entries
            # — see the "Drop unmapped tree node" branch above.
            return [
                processed
                for item in structure
                for processed in (self._update_node_ids_in_structure(item, id_mapping),)
                if processed is not None
            ]

        else:
            # Return primitive values as-is
            return structure