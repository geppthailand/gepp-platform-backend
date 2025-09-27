"""
Organization Service Response DTOs
Based on frontend OrganizationApiService response patterns
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class OrganizationInfoResponse:
    """Organization detailed information"""
    company_name: str
    account_type: str
    business_type: str
    business_industry: str
    tax_id: str


@dataclass
class OrganizationResponse:
    """
    DTO for organization data response
    Maps to frontend Organization interface
    """
    id: int
    name: str
    description: Optional[str] = None
    info: Optional[OrganizationInfoResponse] = None
    created_date: Optional[str] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'name': self.name,
            'is_active': self.is_active
        }

        if self.description:
            result['description'] = self.description
        if self.info:
            result['info'] = self.info.__dict__
        if self.created_date:
            result['created_date'] = self.created_date

        return result


@dataclass
class OrganizationRolePermission:
    """Organization role permission"""
    id: int
    permission: str


@dataclass
class OrganizationRoleResponse:
    """
    DTO for organization role data response
    Maps to frontend OrganizationRole interface
    """
    id: int
    key: str
    name: str
    description: str
    is_system: bool
    created_date: Optional[str] = None
    updated_date: Optional[str] = None
    permissions: List[OrganizationRolePermission] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'is_system': self.is_system,
            'permissions': [perm.__dict__ for perm in self.permissions]
        }

        if self.created_date:
            result['created_date'] = self.created_date
        if self.updated_date:
            result['updated_date'] = self.updated_date

        return result


@dataclass
class OrganizationMemberRole:
    """Organization member role information"""
    id: int
    key: str
    name: str


@dataclass
class OrganizationMemberResponse:
    """
    DTO for organization member data response
    Maps to frontend OrganizationMember interface
    """
    id: str
    display_name: str
    email: str
    organization_role: Optional[OrganizationMemberRole] = None
    created_date: Optional[str] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'display_name': self.display_name,
            'email': self.email,
            'is_active': self.is_active
        }

        if self.organization_role:
            result['organization_role'] = self.organization_role.__dict__
        if self.created_date:
            result['created_date'] = self.created_date

        return result


@dataclass
class OrganizationMembersListResponse:
    """
    DTO for paginated organization members list
    Maps to frontend getOrganizationMembers response
    """
    data: List[OrganizationMemberResponse]
    total: int
    page: int
    size: int
    has_more: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'data': [member.to_dict() for member in self.data],
            'total': self.total,
            'page': self.page,
            'size': self.size,
            'hasMore': self.has_more
        }


@dataclass
class OrganizationLevel:
    """Organization structure level"""
    level: int
    members: List[OrganizationMemberResponse]


@dataclass
class OrganizationStructureResponse:
    """
    DTO for organization hierarchy/structure
    Maps to frontend getOrganizationStructure response
    """
    levels: List[OrganizationLevel]
    total_members: int
    max_depth: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'levels': [
                {
                    'level': level.level,
                    'members': [member.to_dict() for member in level.members]
                }
                for level in self.levels
            ],
            'total_members': self.total_members,
            'max_depth': self.max_depth
        }


@dataclass
class OrganizationActivity:
    """Recent organization activity"""
    type: str
    count: int
    date: str


@dataclass
class OrganizationStatsResponse:
    """
    DTO for organization statistics
    Maps to frontend getOrganizationStats response
    """
    total_members: int
    active_members: int
    invited_members: int
    suspended_members: int
    roles_distribution: Dict[str, int]
    recent_activity: List[OrganizationActivity]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'total_members': self.total_members,
            'active_members': self.active_members,
            'invited_members': self.invited_members,
            'suspended_members': self.suspended_members,
            'roles_distribution': self.roles_distribution,
            'recent_activity': [activity.__dict__ for activity in self.recent_activity]
        }


@dataclass
class BulkAssignRolesResponse:
    """
    DTO for bulk role assignment results
    Maps to frontend bulkAssignRoles response
    """
    updated_count: int
    errors: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {'updated_count': self.updated_count}
        if self.errors:
            result['errors'] = self.errors
        return result


@dataclass
class ResendInvitationResponse:
    """
    DTO for resend invitation results
    Maps to frontend resendMemberInvitation response
    """
    message: str
    invitation_sent: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class ValidationPermissionResponse:
    """
    DTO for permission validation results
    Maps to frontend validateRolePermission response
    """
    has_permission: bool
    role: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class ExportMembersResponse:
    """
    DTO for export members results
    Maps to frontend exportMembers response
    """
    download_url: str
    expires_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return self.__dict__


@dataclass
class ImportError:
    """Import operation error"""
    row: int
    email: str
    message: str


@dataclass
class ImportMembersResponse:
    """
    DTO for import members results
    Maps to frontend importMembers response
    """
    imported_count: int
    skipped_count: int
    error_count: int
    errors: Optional[List[ImportError]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'imported_count': self.imported_count,
            'skipped_count': self.skipped_count,
            'error_count': self.error_count
        }

        if self.errors:
            result['errors'] = [error.__dict__ for error in self.errors]

        return result


@dataclass
class OrganizationSetupResponse:
    """
    DTO for organization setup structure response
    Maps to frontend organization structure data format
    """
    id: int
    organization_id: int
    version: str
    is_active: bool
    root_nodes: Optional[List[Dict[str, Any]]] = None
    hub_node: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_date: Optional[str] = None
    updated_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'organization_id': self.organization_id,
            'version': self.version,
            'is_active': self.is_active
        }

        if self.root_nodes is not None:
            result['root_nodes'] = self.root_nodes
        if self.hub_node is not None:
            result['hub_node'] = self.hub_node
        if self.metadata is not None:
            result['metadata'] = self.metadata
        if self.created_date:
            result['created_date'] = self.created_date
        if self.updated_date:
            result['updated_date'] = self.updated_date

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrganizationSetupResponse':
        """Create DTO from dictionary"""
        return cls(
            id=data['id'],
            organization_id=data['organization_id'],
            version=data['version'],
            is_active=data['is_active'],
            root_nodes=data.get('root_nodes'),
            hub_node=data.get('hub_node'),
            metadata=data.get('metadata'),
            created_date=data.get('created_date'),
            updated_date=data.get('updated_date')
        )