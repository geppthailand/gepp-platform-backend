"""
Organization Service Request DTOs
Based on frontend OrganizationApiService patterns
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class ExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"


@dataclass
class CreateOrganizationRequest:
    """
    DTO for creating a new organization
    """
    name: str
    description: Optional[str] = None
    info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {'name': self.name}
        if self.description:
            result['description'] = self.description
        if self.info:
            result['info'] = self.info
        return result


@dataclass
class UpdateOrganizationRequest:
    """
    DTO for updating an existing organization
    """
    organization_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {}
        if self.name:
            result['name'] = self.name
        if self.description:
            result['description'] = self.description
        if self.info:
            result['info'] = self.info
        return result


@dataclass
class CreateRoleRequest:
    """
    DTO for creating a new organization role
    Maps to frontend CreateRoleRequest interface
    """
    key: str
    name: str
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {
            'key': self.key,
            'name': self.name
        }
        if self.description:
            result['description'] = self.description
        return result


@dataclass
class UpdateRoleRequest:
    """
    DTO for updating an existing organization role
    Maps to frontend UpdateRoleRequest interface
    """
    role_id: int
    key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {}
        if self.key:
            result['key'] = self.key
        if self.name:
            result['name'] = self.name
        if self.description:
            result['description'] = self.description
        return result


@dataclass
class CreateMemberRequest:
    """
    DTO for creating a new organization member
    Maps to frontend CreateMemberRequest interface
    """
    email_or_phone: str
    organization_role_id: int
    display_name: Optional[str] = None
    company_name: Optional[str] = None
    business_industry: Optional[str] = None
    business_sub_industry: Optional[str] = None
    locale: Optional[str] = "TH"
    send_invitation: Optional[bool] = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        is_email = "@" in self.email_or_phone

        result = {
            'organization_role_id': self.organization_role_id,
            'locale': self.locale,
            'send_invitation': self.send_invitation
        }

        if is_email:
            result['email'] = self.email_or_phone
        else:
            result['phone'] = self.email_or_phone

        if self.display_name:
            result['display_name'] = self.display_name
        if self.company_name:
            result['company_name'] = self.company_name
        if self.business_industry:
            result['business_industry'] = self.business_industry
        if self.business_sub_industry:
            result['business_sub_industry'] = self.business_sub_industry

        return result


@dataclass
class UpdateMemberRequest:
    """
    DTO for updating an existing organization member
    """
    member_id: str
    updates: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return self.updates


@dataclass
class OrganizationFiltersRequest:
    """
    DTO for organization member filtering and search
    """
    page: int = 1
    page_size: int = 20
    search: Optional[str] = None
    role_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for filtering operations"""
        result = {
            'page': self.page,
            'page_size': self.page_size
        }

        if self.search:
            result['search'] = self.search
        if self.role_id:
            result['role_id'] = self.role_id

        return result


@dataclass
class BulkAssignRolesRequest:
    """
    DTO for bulk role assignment to members
    Maps to frontend bulkAssignRoles method parameters
    """
    member_ids: List[str]
    role_id: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for bulk operations"""
        return {
            'member_ids': self.member_ids,
            'organization_role_id': self.role_id
        }


@dataclass
class ExportMembersRequest:
    """
    DTO for exporting organization members
    Maps to frontend exportMembers method parameters
    """
    format: ExportFormat = ExportFormat.CSV
    role_ids: Optional[List[int]] = None
    active_only: Optional[bool] = None
    include_inactive: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export operations"""
        result = {'format': self.format.value}

        if self.role_ids:
            result['role_ids'] = self.role_ids
        if self.active_only is not None:
            result['active_only'] = self.active_only
        if self.include_inactive is not None:
            result['include_inactive'] = self.include_inactive

        return result


@dataclass
class ImportMembersRequest:
    """
    DTO for importing organization members from file
    Maps to frontend importMembers method parameters
    """
    file_data: bytes
    file_name: str
    content_type: str
    default_role_id: Optional[int] = None
    send_invitations: Optional[bool] = False
    skip_duplicates: Optional[bool] = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for import operations"""
        result = {
            'file_name': self.file_name,
            'content_type': self.content_type
        }

        if self.default_role_id:
            result['default_role_id'] = self.default_role_id
        if self.send_invitations is not None:
            result['send_invitations'] = self.send_invitations
        if self.skip_duplicates is not None:
            result['skip_duplicates'] = self.skip_duplicates

        return result


@dataclass
class CreateOrganizationSetupRequest:
    """
    DTO for creating organization setup structure
    Maps to frontend organization structure data format with treeStructure wrapper
    """
    organization_id: Optional[str] = None
    tree_structure: Optional[Dict[str, Any]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {}

        # Extract root_nodes and hub_node from tree_structure
        if self.tree_structure:
            if 'rootNodes' in self.tree_structure:
                result['root_nodes'] = self.tree_structure['rootNodes']
            if 'hubNode' in self.tree_structure:
                result['hub_node'] = self.tree_structure['hubNode']

        if self.metadata is not None:
            result['metadata'] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreateOrganizationSetupRequest':
        """Create DTO from dictionary"""
        return cls(
            organization_id=data.get('organizationId'),
            tree_structure=data.get('treeStructure'),
            locations=data.get('locations'),
            metadata=data.get('metadata')
        )

    def validate(self) -> List[str]:
        """Validate the request data"""
        errors = []

        # tree_structure is required
        if not self.tree_structure:
            errors.append("treeStructure is required")
            return errors

        # At least one structure should be provided
        root_nodes = self.tree_structure.get('rootNodes')
        hub_node = self.tree_structure.get('hubNode')

        if not root_nodes and not hub_node:
            errors.append("At least one of rootNodes or hubNode must be provided in treeStructure")

        # Validate root_nodes structure if provided
        if root_nodes is not None:
            if not isinstance(root_nodes, list):
                errors.append("treeStructure.rootNodes must be a list")
            else:
                for i, node in enumerate(root_nodes):
                    if not isinstance(node, dict):
                        errors.append(f"treeStructure.rootNodes[{i}] must be a dictionary")
                    elif 'nodeId' not in node:
                        errors.append(f"treeStructure.rootNodes[{i}] must contain 'nodeId' field")

        # Validate hub_node structure if provided
        if hub_node is not None:
            if not isinstance(hub_node, dict):
                errors.append("treeStructure.hubNode must be a dictionary")
            elif 'children' not in hub_node:
                errors.append("treeStructure.hubNode must contain 'children' field")

        return errors


@dataclass
class UpdateOrganizationSetupRequest:
    """
    DTO for updating organization setup structure
    Creates a new version instead of updating existing one
    """
    organization_id: Optional[str] = None
    tree_structure: Optional[Dict[str, Any]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        result = {}

        # Extract root_nodes and hub_node from tree_structure
        if self.tree_structure:
            if 'rootNodes' in self.tree_structure:
                result['root_nodes'] = self.tree_structure['rootNodes']
            if 'hubNode' in self.tree_structure:
                result['hub_node'] = self.tree_structure['hubNode']
            if 'locations' in self.tree_structure:
                result['locations'] = self.tree_structure['locations']

        if self.metadata is not None:
            result['metadata'] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UpdateOrganizationSetupRequest':
        """Create DTO from dictionary"""
        print("^^^^^^", data['treeStructure'].get('locations'))
        return cls(
            organization_id=data.get('organizationId'),
            tree_structure=data.get('treeStructure'),
            locations=data['treeStructure'].get('locations'),
            metadata=data.get('metadata')
        )

    def validate(self) -> List[str]:
        """Validate the request data"""
        errors = []

        # tree_structure is required
        if not self.tree_structure:
            errors.append("treeStructure is required")
            return errors

        # At least one structure should be provided for update
        root_nodes = self.tree_structure.get('rootNodes')
        hub_node = self.tree_structure.get('hubNode')

        if not root_nodes and not hub_node:
            errors.append("At least one of rootNodes or hubNode must be provided in treeStructure")

        return errors