"""
Location Tag Service for managing user location tags
Tags are organization-level and can be associated with multiple locations (many-to-many)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from sqlalchemy.dialects.postgresql import JSONB

from GEPPPlatform.models.users.user_related import UserLocationTag
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class LocationTagService:
    """Service for managing location tags with many-to-many relationships"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_tags_by_location(
        self,
        user_location_id: int,
        organization_id: int,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all tags associated with a specific location"""
        conditions = [
            UserLocationTag.organization_id == organization_id,
            UserLocationTag.deleted_date.is_(None)
        ]

        if not include_inactive:
            conditions.append(UserLocationTag.is_active == True)

        # Get all tags for the organization first
        all_tags = self.db.query(UserLocationTag).filter(
            and_(*conditions)
        ).order_by(UserLocationTag.created_date.desc()).all()

        # Filter tags that have this location in their user_locations array
        location_tags = []
        location_id_int = user_location_id
        location_id_str = str(user_location_id)

        for tag in all_tags:
            tag_locations = tag.user_locations or []
            if location_id_int in tag_locations or location_id_str in tag_locations:
                location_tags.append(self._serialize_tag(tag))

        return location_tags

    def get_tags_by_organization(
        self,
        organization_id: int,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all tags for an organization"""
        conditions = [
            UserLocationTag.organization_id == organization_id,
            UserLocationTag.deleted_date.is_(None)
        ]

        if not include_inactive:
            conditions.append(UserLocationTag.is_active == True)

        tags = self.db.query(UserLocationTag).filter(
            and_(*conditions)
        ).order_by(UserLocationTag.created_date.desc()).all()

        return [self._serialize_tag(tag) for tag in tags]

    def get_tag_by_id(
        self,
        tag_id: int,
        organization_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific tag by ID"""
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            return None

        return self._serialize_tag(tag)

    def create_tag(
        self,
        organization_id: int,
        data: Dict[str, Any],
        created_by_id: Optional[int] = None,
        user_location_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new organization-level tag, optionally associating with a location"""
        # Validate required fields
        name = data.get('name')
        if not name:
            raise BadRequestException('Tag name is required')

        # Check for duplicate tag name in the same organization (case-insensitive)
        existing_tag = self.db.query(UserLocationTag).filter(
            and_(
                func.lower(UserLocationTag.name) == func.lower(name),
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if existing_tag:
            raise BadRequestException('ชื่อ Tag นี้มีอยู่แล้วในองค์กร กรุณาใช้ชื่ออื่น')

        # Parse dates if provided
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

        # Initial user_locations list
        initial_locations = []
        if user_location_id:
            # Validate that user_location exists and belongs to organization
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

        # Create tag
        # Note: user_location_id is set for backward compatibility until DB migration completes
        tag = UserLocationTag(
            name=name,
            note=data.get('note'),
            organization_id=organization_id,
            created_by_id=created_by_id,
            user_location_id=user_location_id,  # Legacy field for backward compatibility
            user_locations=initial_locations,
            members=data.get('members', []),
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )

        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)

        # Update the location's tags array if initial location was provided
        if user_location_id and initial_locations:
            self._update_location_tags(user_location_id, tag.id, add=True)
            self.db.commit()  # Commit the location's tags array update

        return self._serialize_tag(tag)

    def update_tag(
        self,
        tag_id: int,
        organization_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing location tag"""
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            raise NotFoundException('Tag not found')

        # Update fields
        if 'name' in data:
            # Check for duplicate tag name in the same organization (case-insensitive), excluding current tag
            existing_tag = self.db.query(UserLocationTag).filter(
                and_(
                    func.lower(UserLocationTag.name) == func.lower(data['name']),
                    UserLocationTag.organization_id == organization_id,
                    UserLocationTag.id != tag_id,
                    UserLocationTag.deleted_date.is_(None)
                )
            ).first()

            if existing_tag:
                raise BadRequestException('ชื่อ Tag นี้มีอยู่แล้วในองค์กร กรุณาใช้ชื่ออื่น')

            tag.name = data['name']

        if 'note' in data:
            tag.note = data['note']

        if 'members' in data:
            tag.members = data['members']

        if 'user_locations' in data:
            # Handle updating the user_locations array
            old_locations = set(tag.user_locations or [])
            new_locations = set(data['user_locations'] or [])

            # Remove tag from locations that are no longer associated
            for loc_id in old_locations - new_locations:
                self._update_location_tags(int(loc_id), tag_id, add=False)

            # Add tag to newly associated locations
            for loc_id in new_locations - old_locations:
                self._update_location_tags(int(loc_id), tag_id, add=True)

            tag.user_locations = list(new_locations)

        if 'start_date' in data:
            if data['start_date']:
                try:
                    tag.start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            else:
                tag.start_date = None

        if 'end_date' in data:
            if data['end_date']:
                try:
                    tag.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            else:
                tag.end_date = None

        if 'is_active' in data:
            tag.is_active = data['is_active']

        tag.updated_date = datetime.utcnow()

        self.db.commit()
        self.db.refresh(tag)

        return self._serialize_tag(tag)

    def delete_tag(
        self,
        tag_id: int,
        organization_id: int,
        hard_delete: bool = False
    ) -> bool:
        """Delete a location tag (soft delete by default)"""
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            return False

        # Remove tag from all associated locations
        for loc_id in (tag.user_locations or []):
            self._update_location_tags(int(loc_id), tag_id, add=False)

        if hard_delete:
            self.db.delete(tag)
        else:
            tag.deleted_date = datetime.utcnow()
            tag.is_active = False
            tag.user_locations = []

        self.db.commit()
        return True

    def attach_tag_to_location(
        self,
        tag_id: int,
        user_location_id: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Attach an existing tag to a location (many-to-many)"""
        # Validate tag exists
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            raise NotFoundException('Tag not found')

        # Validate location exists
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

        # Add location to tag's user_locations if not already there
        current_locations = list(tag.user_locations or [])
        if user_location_id not in current_locations and str(user_location_id) not in [str(x) for x in current_locations]:
            current_locations.append(user_location_id)
            tag.user_locations = current_locations
            tag.updated_date = datetime.utcnow()

        # Add tag to location's tags array
        self._update_location_tags(user_location_id, tag_id, add=True)

        self.db.commit()
        self.db.refresh(tag)

        return self._serialize_tag(tag)

    def detach_tag_from_location(
        self,
        tag_id: int,
        user_location_id: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Detach a tag from a location (does not delete the tag)"""
        # Validate tag exists
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            raise NotFoundException('Tag not found')

        # Remove location from tag's user_locations
        current_locations = list(tag.user_locations or [])
        # Handle both int and string representations
        new_locations = [loc for loc in current_locations
                        if loc != user_location_id and str(loc) != str(user_location_id)]

        if len(new_locations) != len(current_locations):
            tag.user_locations = new_locations
            tag.updated_date = datetime.utcnow()

        # Remove tag from location's tags array
        self._update_location_tags(user_location_id, tag_id, add=False)

        self.db.commit()
        self.db.refresh(tag)

        return self._serialize_tag(tag)

    def assign_members_to_tag(
        self,
        tag_id: int,
        organization_id: int,
        member_ids: List[int]
    ) -> Dict[str, Any]:
        """Assign members (user_locations) to a tag"""
        tag = self.db.query(UserLocationTag).filter(
            and_(
                UserLocationTag.id == tag_id,
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).first()

        if not tag:
            raise NotFoundException('Tag not found')

        # Validate that all member IDs belong to the organization
        valid_members = self.db.query(UserLocation.id).filter(
            and_(
                UserLocation.id.in_(member_ids),
                UserLocation.organization_id == organization_id,
                UserLocation.deleted_date.is_(None)
            )
        ).all()

        valid_member_ids = [m[0] for m in valid_members]

        tag.members = valid_member_ids
        tag.updated_date = datetime.utcnow()

        self.db.commit()
        self.db.refresh(tag)

        return self._serialize_tag(tag)

    def _update_location_tags(self, location_id: int, tag_id: int, add: bool = True):
        """Helper to update a location's tags JSONB array"""
        location = self.db.query(UserLocation).filter(
            UserLocation.id == location_id
        ).first()

        if not location:
            return

        current_tags = list(location.tags or [])

        if add:
            # Add tag if not already present
            if tag_id not in current_tags and str(tag_id) not in [str(x) for x in current_tags]:
                current_tags.append(tag_id)
                location.tags = current_tags
        else:
            # Remove tag if present
            new_tags = [t for t in current_tags
                       if t != tag_id and str(t) != str(tag_id)]
            if len(new_tags) != len(current_tags):
                location.tags = new_tags

    def _serialize_tag(self, tag: UserLocationTag) -> Dict[str, Any]:
        """Serialize a tag to dictionary"""
        # Get creator name
        creator_name = None
        if tag.created_by:
            creator_name = tag.created_by.display_name or tag.created_by.name_th or tag.created_by.name_en

        # Get member details
        member_details = []
        if tag.members:
            # Handle both int and string IDs
            member_ids = [int(m) if isinstance(m, str) else m for m in tag.members]
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

        # Get location details for associated locations
        location_details = []
        if tag.user_locations:
            # Handle both int and string IDs
            location_ids = [int(loc) if isinstance(loc, str) else loc for loc in tag.user_locations]
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
            'id': tag.id,
            'name': tag.name,
            'note': tag.note,
            'user_locations': tag.user_locations or [],
            'location_details': location_details,
            'organization_id': tag.organization_id,
            'created_by_id': tag.created_by_id,
            'creator_name': creator_name,
            'members': tag.members or [],
            'member_details': member_details,
            'start_date': tag.start_date.isoformat() if tag.start_date else None,
            'end_date': tag.end_date.isoformat() if tag.end_date else None,
            'is_active': tag.is_active,
            'created_date': tag.created_date.isoformat() if tag.created_date else None,
            'updated_date': tag.updated_date.isoformat() if tag.updated_date else None,
            # Camel case aliases for frontend
            'userLocations': tag.user_locations or [],
            'locationDetails': location_details,
            'organizationId': tag.organization_id,
            'createdById': tag.created_by_id,
            'creatorName': creator_name,
            'memberDetails': member_details,
            'startDate': tag.start_date.isoformat() if tag.start_date else None,
            'endDate': tag.end_date.isoformat() if tag.end_date else None,
            'isActive': tag.is_active,
            'createdDate': tag.created_date.isoformat() if tag.created_date else None,
            'updatedDate': tag.updated_date.isoformat() if tag.updated_date else None,
        }
