"""
Location Tag Service for managing user location tags
Tags are used to categorize and organize waste origin points within locations
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from GEPPPlatform.models.users.user_related import UserLocationTag
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class LocationTagService:
    """Service for managing location tags"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_tags_by_location(
        self,
        user_location_id: int,
        organization_id: int,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all tags for a specific location"""
        conditions = [
            UserLocationTag.user_location_id == user_location_id,
            UserLocationTag.organization_id == organization_id,
            UserLocationTag.deleted_date.is_(None)
        ]

        if not include_inactive:
            conditions.append(UserLocationTag.is_active == True)

        tags = self.db.query(UserLocationTag).filter(
            and_(*conditions)
        ).order_by(UserLocationTag.created_date.desc()).all()

        return [self._serialize_tag(tag) for tag in tags]

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
        user_location_id: int,
        organization_id: int,
        data: Dict[str, Any],
        created_by_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new location tag"""
        # Validate that user_location exists and belongs to organization
        location = self.db.query(UserLocation).filter(
            and_(
                UserLocation.id == user_location_id,
                UserLocation.organization_id == organization_id,
                UserLocation.is_location == True,
                UserLocation.deleted_date.is_(None)
            )
        ).first()

        if not location:
            raise NotFoundException('Location not found or does not belong to organization')

        # Validate required fields
        name = data.get('name')
        if not name:
            raise BadRequestException('Tag name is required')

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

        # Create tag
        tag = UserLocationTag(
            name=name,
            note=data.get('note'),
            user_location_id=user_location_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
            members=data.get('members', []),
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )

        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)

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
            tag.name = data['name']

        if 'note' in data:
            tag.note = data['note']

        if 'members' in data:
            tag.members = data['members']

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

        if hard_delete:
            self.db.delete(tag)
        else:
            tag.deleted_date = datetime.utcnow()
            tag.is_active = False

        self.db.commit()
        return True

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

    def _serialize_tag(self, tag: UserLocationTag) -> Dict[str, Any]:
        """Serialize a tag to dictionary"""
        # Get location name
        location_name = None
        if tag.user_location:
            location_name = tag.user_location.display_name or tag.user_location.name_th or tag.user_location.name_en

        # Get creator name
        creator_name = None
        if tag.created_by:
            creator_name = tag.created_by.display_name or tag.created_by.name_th or tag.created_by.name_en

        # Get member details
        member_details = []
        if tag.members:
            members = self.db.query(UserLocation).filter(
                UserLocation.id.in_(tag.members)
            ).all()
            for member in members:
                member_details.append({
                    'id': member.id,
                    'display_name': member.display_name or member.name_th or member.name_en,
                    'is_user': member.is_user,
                    'is_location': member.is_location
                })

        return {
            'id': tag.id,
            'name': tag.name,
            'note': tag.note,
            'user_location_id': tag.user_location_id,
            'location_name': location_name,
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
            'userLocationId': tag.user_location_id,
            'locationName': location_name,
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
