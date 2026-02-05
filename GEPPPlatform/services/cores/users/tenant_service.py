"""
Tenant Service for managing user tenants
Tenants are organization-level and can be associated with multiple locations (many-to-many)
Works exactly like the location tag service.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from GEPPPlatform.models.users.user_related import UserTenant
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class TenantService:
    """Service for managing tenants with many-to-many relationships (same as location tags)"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_tenants_by_location(
        self,
        user_location_id: int,
        organization_id: int,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all tenants associated with a specific location"""
        conditions = [
            UserTenant.organization_id == organization_id,
            UserTenant.deleted_date.is_(None)
        ]

        if not include_inactive:
            conditions.append(UserTenant.is_active == True)

        all_tenants = self.db.query(UserTenant).filter(
            and_(*conditions)
        ).order_by(UserTenant.created_date.desc()).all()

        location_tenants = []
        location_id_int = user_location_id
        location_id_str = str(user_location_id)

        for tenant in all_tenants:
            tenant_locations = tenant.user_locations or []
            if location_id_int in tenant_locations or location_id_str in tenant_locations:
                location_tenants.append(self._serialize_tenant(tenant))

        return location_tenants

    def get_tenants_by_organization(
        self,
        organization_id: int,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all tenants for an organization"""
        conditions = [
            UserTenant.organization_id == organization_id,
            UserTenant.deleted_date.is_(None)
        ]

        if not include_inactive:
            conditions.append(UserTenant.is_active == True)

        tenants = self.db.query(UserTenant).filter(
            and_(*conditions)
        ).order_by(UserTenant.created_date.desc()).all()

        return [self._serialize_tenant(t) for t in tenants]

    def get_tenant_by_id(
        self,
        tenant_id: int,
        organization_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific tenant by ID"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            return None

        return self._serialize_tenant(tenant)

    def create_tenant(
        self,
        organization_id: int,
        data: Dict[str, Any],
        created_by_id: Optional[int] = None,
        user_location_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new organization-level tenant, optionally associating with a location"""
        name = data.get('name')
        if not name:
            raise BadRequestException('Tenant name is required')

        existing_tenant = self.db.query(UserTenant).filter(
            and_(
                func.lower(UserTenant.name) == func.lower(name),
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if existing_tenant:
            raise BadRequestException('ชื่อ Tenant นี้มีอยู่แล้วในองค์กร กรุณาใช้ชื่ออื่น')

        start_date = None
        end_date = None
        if data.get('start_date'):
            try:
                start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        if data.get('end_date'):
            try:
                end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        initial_locations = []
        if user_location_id:
            location = self.db.query(UserLocation).filter(
                and_(
                    UserLocation.id == user_location_id,
                    UserLocation.organization_id == organization_id,
                    UserLocation.is_location == True,
                    UserLocation.deleted_date.is_(None)
                )
            ).first()
            if location:
                initial_locations = [user_location_id]

        tenant = UserTenant(
            name=name,
            note=data.get('note'),
            organization_id=organization_id,
            created_by_id=created_by_id,
            user_location_id=user_location_id,
            user_locations=initial_locations,
            members=data.get('members', []),
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )

        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)

        if user_location_id and initial_locations:
            self._update_location_tenants(user_location_id, tenant.id, add=True)
            self.db.commit()

        return self._serialize_tenant(tenant)

    def update_tenant(
        self,
        tenant_id: int,
        organization_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing tenant"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            raise NotFoundException('Tenant not found')

        if 'name' in data:
            existing_tenant = self.db.query(UserTenant).filter(
                and_(
                    func.lower(UserTenant.name) == func.lower(data['name']),
                    UserTenant.organization_id == organization_id,
                    UserTenant.id != tenant_id,
                    UserTenant.deleted_date.is_(None)
                )
            ).first()

            if existing_tenant:
                raise BadRequestException('ชื่อ Tenant นี้มีอยู่แล้วในองค์กร กรุณาใช้ชื่ออื่น')

            tenant.name = data['name']

        if 'note' in data:
            tenant.note = data['note']

        if 'members' in data:
            tenant.members = data['members']

        if 'user_locations' in data:
            old_locations = set(tenant.user_locations or [])
            new_locations = set(data['user_locations'] or [])

            for loc_id in old_locations - new_locations:
                self._update_location_tenants(int(loc_id), tenant_id, add=False)

            for loc_id in new_locations - old_locations:
                self._update_location_tenants(int(loc_id), tenant_id, add=True)

            tenant.user_locations = list(new_locations)

        if 'start_date' in data:
            if data['start_date']:
                try:
                    tenant.start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            else:
                tenant.start_date = None

        if 'end_date' in data:
            if data['end_date']:
                try:
                    tenant.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            else:
                tenant.end_date = None

        if 'is_active' in data:
            tenant.is_active = data['is_active']

        tenant.updated_date = datetime.utcnow()

        self.db.commit()
        self.db.refresh(tenant)

        return self._serialize_tenant(tenant)

    def delete_tenant(
        self,
        tenant_id: int,
        organization_id: int,
        hard_delete: bool = False
    ) -> bool:
        """Delete a tenant (soft delete by default)"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            return False

        for loc_id in (tenant.user_locations or []):
            self._update_location_tenants(int(loc_id), tenant_id, add=False)

        if hard_delete:
            self.db.delete(tenant)
        else:
            tenant.deleted_date = datetime.utcnow()
            tenant.is_active = False
            tenant.user_locations = []

        self.db.commit()
        return True

    def attach_tenant_to_location(
        self,
        tenant_id: int,
        user_location_id: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Attach an existing tenant to a location (many-to-many)"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            raise NotFoundException('Tenant not found')

        location = self.db.query(UserLocation).filter(
            and_(
                UserLocation.id == user_location_id,
                UserLocation.organization_id == organization_id,
                UserLocation.is_location == True,
                UserLocation.deleted_date.is_(None)
            )
        ).first()

        if not location:
            raise NotFoundException('Location not found')

        current_locations = list(tenant.user_locations or [])
        if user_location_id not in current_locations and str(user_location_id) not in [str(x) for x in current_locations]:
            current_locations.append(user_location_id)
            tenant.user_locations = current_locations
            tenant.updated_date = datetime.utcnow()

        self._update_location_tenants(user_location_id, tenant_id, add=True)

        self.db.commit()
        self.db.refresh(tenant)

        return self._serialize_tenant(tenant)

    def detach_tenant_from_location(
        self,
        tenant_id: int,
        user_location_id: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Detach a tenant from a location (does not delete the tenant)"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            raise NotFoundException('Tenant not found')

        current_locations = list(tenant.user_locations or [])
        new_locations = [loc for loc in current_locations
                        if loc != user_location_id and str(loc) != str(user_location_id)]

        if len(new_locations) != len(current_locations):
            tenant.user_locations = new_locations
            tenant.updated_date = datetime.utcnow()

        self._update_location_tenants(user_location_id, tenant_id, add=False)

        self.db.commit()
        self.db.refresh(tenant)

        return self._serialize_tenant(tenant)

    def assign_members_to_tenant(
        self,
        tenant_id: int,
        organization_id: int,
        member_ids: List[int]
    ) -> Dict[str, Any]:
        """Assign members (user_locations) to a tenant"""
        tenant = self.db.query(UserTenant).filter(
            and_(
                UserTenant.id == tenant_id,
                UserTenant.organization_id == organization_id,
                UserTenant.deleted_date.is_(None)
            )
        ).first()

        if not tenant:
            raise NotFoundException('Tenant not found')

        valid_members = self.db.query(UserLocation.id).filter(
            and_(
                UserLocation.id.in_(member_ids),
                UserLocation.organization_id == organization_id,
                UserLocation.deleted_date.is_(None)
            )
        ).all()

        valid_member_ids = [m[0] for m in valid_members]

        tenant.members = valid_member_ids
        tenant.updated_date = datetime.utcnow()

        self.db.commit()
        self.db.refresh(tenant)

        return self._serialize_tenant(tenant)

    def _update_location_tenants(self, location_id: int, tenant_id: int, add: bool = True):
        """Helper to update a location's tenants JSONB array"""
        location = self.db.query(UserLocation).filter(
            UserLocation.id == location_id
        ).first()

        if not location:
            return

        current_tenants = list(location.tenants or [])

        if add:
            if tenant_id not in current_tenants and str(tenant_id) not in [str(x) for x in current_tenants]:
                current_tenants.append(tenant_id)
                location.tenants = current_tenants
        else:
            new_tenants = [t for t in current_tenants
                          if t != tenant_id and str(t) != str(tenant_id)]
            if len(new_tenants) != len(current_tenants):
                location.tenants = new_tenants

    def _serialize_tenant(self, tenant: UserTenant) -> Dict[str, Any]:
        """Serialize a tenant to dictionary"""
        creator_name = None
        if tenant.created_by:
            creator_name = tenant.created_by.display_name or tenant.created_by.name_th or tenant.created_by.name_en

        member_details = []
        if tenant.members:
            member_ids = [int(m) if isinstance(m, str) else m for m in tenant.members]
            members = self.db.query(UserLocation).filter(
                UserLocation.id.in_(member_ids)
            ).all()
            for member in members:
                member_details.append({
                    'id': member.id,
                    'display_name': member.display_name or member.name_th or member.name_en,
                    'is_user': member.is_user,
                    'is_location': member.is_location
                })

        location_details = []
        if tenant.user_locations:
            location_ids = [int(loc) if isinstance(loc, str) else loc for loc in tenant.user_locations]
            locations = self.db.query(UserLocation).filter(
                UserLocation.id.in_(location_ids)
            ).all()
            for loc in locations:
                location_details.append({
                    'id': loc.id,
                    'display_name': loc.display_name or loc.name_th or loc.name_en,
                    'is_user': loc.is_user,
                    'is_location': loc.is_location
                })

        return {
            'id': tenant.id,
            'name': tenant.name,
            'note': tenant.note,
            'user_locations': tenant.user_locations or [],
            'location_details': location_details,
            'organization_id': tenant.organization_id,
            'created_by_id': tenant.created_by_id,
            'creator_name': creator_name,
            'members': tenant.members or [],
            'member_details': member_details,
            'start_date': tenant.start_date.isoformat() if tenant.start_date else None,
            'end_date': tenant.end_date.isoformat() if tenant.end_date else None,
            'is_active': tenant.is_active,
            'created_date': tenant.created_date.isoformat() if tenant.created_date else None,
            'updated_date': tenant.updated_date.isoformat() if tenant.updated_date else None,
            'userLocations': tenant.user_locations or [],
            'locationDetails': location_details,
            'organizationId': tenant.organization_id,
            'createdById': tenant.created_by_id,
            'creatorName': creator_name,
            'memberDetails': member_details,
            'startDate': tenant.start_date.isoformat() if tenant.start_date else None,
            'endDate': tenant.end_date.isoformat() if tenant.end_date else None,
            'isActive': tenant.is_active,
            'createdDate': tenant.created_date.isoformat() if tenant.created_date else None,
            'updatedDate': tenant.updated_date.isoformat() if tenant.updated_date else None,
        }
