"""
Material Tags management service
Handles CRUD operations for material tags (new tag-based system)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from ....models.cores.references import MaterialTag
from ....models.subscriptions.organizations import Organization
from ....exceptions import ValidationException, NotFoundException


class TagsService:
    """
    High-level material tags management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== MATERIAL TAG CRUD OPERATIONS ==========

    def create_tag(self, tag_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new material tag with validation
        """
        try:
            # Validate tag data
            validation_result = self._validate_tag_data(tag_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Tag validation failed: {error_messages}')

            # Create tag instance
            tag = MaterialTag(
                name=tag_data['name'],
                description=tag_data.get('description'),
                color=tag_data.get('color', '#808080'),
                is_global=tag_data.get('is_global', False),
                organization_id=tag_data.get('organization_id')
            )

            self.db.add(tag)
            self.db.flush()
            self.db.refresh(tag)

            return {
                'success': True,
                'tag': self._serialize_tag(tag)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_tags(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = 'name',
        sort_order: str = 'asc'
    ) -> Dict[str, Any]:
        """
        Get tags with filtering, pagination, and sorting
        """
        try:
            query = self.db.query(MaterialTag).filter(MaterialTag.is_active == True)

            # Apply filters
            if filters:
                query = self._apply_tag_filters(query, filters)

            # Get total count before pagination
            total_count = query.count()

            # Apply sorting
            if hasattr(MaterialTag, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(MaterialTag, sort_by).desc())
                else:
                    query = query.order_by(getattr(MaterialTag, sort_by))

            # Apply pagination
            offset = (page - 1) * page_size
            tags = query.offset(offset).limit(page_size).all()

            return {
                'data': [self._serialize_tag(tag) for tag in tags],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total_count,
                    'pages': (total_count + page_size - 1) // page_size,
                    'has_next': page * page_size < total_count,
                    'has_prev': page > 1
                }
            }

        except Exception as e:
            raise e

    def get_tag_by_id(self, tag_id: int, include_relations: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get tag by ID with optional relationship loading
        """
        try:
            query = self.db.query(MaterialTag).filter(
                MaterialTag.id == tag_id,
                MaterialTag.is_active == True
            )

            if include_relations:
                query = query.join(Organization, MaterialTag.organization_id == Organization.id, isouter=True)

            tag = query.first()
            if not tag:
                return None

            tag_data = self._serialize_tag(tag)

            # Add organization information if available
            if include_relations and tag.organization:
                tag_data['organization'] = {
                    'id': tag.organization.id,
                    'name': tag.organization.name,
                    'display_name': tag.organization.display_name
                }

            return tag_data

        except Exception as e:
            raise e

    def update_tag(self, tag_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update tag with validation
        """
        try:
            tag = self.db.query(MaterialTag).filter(
                MaterialTag.id == tag_id,
                MaterialTag.is_active == True
            ).first()

            if not tag:
                raise NotFoundException('Tag not found')

            # Validate updates
            validation_result = self._validate_tag_updates(tag, updates)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Tag update validation failed: {error_messages}')

            # Apply updates
            for key, value in updates.items():
                if hasattr(tag, key):
                    setattr(tag, key, value)

            self.db.flush()
            self.db.refresh(tag)

            return {
                'success': True,
                'tag': self._serialize_tag(tag)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def delete_tag(self, tag_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete tag (soft delete by default)
        """
        try:
            tag = self.db.query(MaterialTag).filter(MaterialTag.id == tag_id).first()
            if not tag:
                raise NotFoundException('Tag not found')

            # Check if tag is being used in any tag groups
            from ....models.cores.references import MaterialTagGroup
            group_count = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.tags.any(tag_id),
                MaterialTagGroup.is_active == True
            ).count()

            if group_count > 0:
                raise ValidationException(f'Cannot delete tag: {group_count} tag groups are using it')

            # Check if tag is being used in any materials
            from ....models.cores.references import Material
            # This is a simplified check - in practice, you'd need to check the JSONB tags column
            # For now, we'll allow deletion and handle cleanup elsewhere

            if soft_delete:
                tag.is_active = False
                from datetime import datetime, timezone
                tag.deleted_date = datetime.now(timezone.utc)
            else:
                self.db.delete(tag)

            self.db.flush()

            return {'success': True, 'message': 'Tag deleted successfully'}

        except Exception as e:
            self.db.rollback()
            raise e

    def list_tags(
        self,
        organization_id: Optional[int] = None,
        include_global: bool = True,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List tags with organization and global filtering
        """
        try:
            query = self.db.query(MaterialTag)

            if not include_inactive:
                query = query.filter(MaterialTag.is_active == True)

            # Filter by scope
            if organization_id:
                if include_global:
                    # Include both organization-specific and global tags
                    query = query.filter(
                        or_(
                            and_(MaterialTag.is_global == False, MaterialTag.organization_id == organization_id),
                            MaterialTag.is_global == True
                        )
                    )
                else:
                    # Only organization-specific tags
                    query = query.filter(
                        MaterialTag.is_global == False,
                        MaterialTag.organization_id == organization_id
                    )
            elif include_global:
                # Only global tags
                query = query.filter(MaterialTag.is_global == True)

            tags = query.order_by(MaterialTag.name).all()

            return [self._serialize_tag(tag) for tag in tags]

        except Exception as e:
            raise e

    def get_available_tags_for_organization(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        Get all tags available to an organization (global + organization-specific)
        """
        return self.list_tags(organization_id=organization_id, include_global=True)

    def get_global_tags(self) -> List[Dict[str, Any]]:
        """
        Get all global tags
        """
        try:
            tags = self.db.query(MaterialTag).filter(
                MaterialTag.is_global == True,
                MaterialTag.is_active == True
            ).order_by(MaterialTag.name).all()

            return [self._serialize_tag(tag) for tag in tags]

        except Exception as e:
            raise e

    def get_organization_tags(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        Get organization-specific tags only
        """
        return self.list_tags(organization_id=organization_id, include_global=False)

    def bulk_create_tags(self, tags_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk create multiple tags
        """
        try:
            created_tags = []
            errors = []

            for i, tag_data in enumerate(tags_data):
                try:
                    result = self.create_tag(tag_data)
                    if result['success']:
                        created_tags.append(result['tag'])
                except Exception as e:
                    errors.append(f'Tag {i+1}: {str(e)}')

            return {
                'success': len(errors) == 0,
                'created_count': len(created_tags),
                'tags': created_tags,
                'errors': errors
            }

        except Exception as e:
            self.db.rollback()
            raise e

    # ========== HELPER METHODS ==========

    def _validate_tag_data(self, tag_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tag creation data"""
        errors = []

        # Required fields
        if not tag_data.get('name'):
            errors.append('name is required')

        # Validate global/organization constraint
        is_global = tag_data.get('is_global', False)
        organization_id = tag_data.get('organization_id')

        if is_global and organization_id:
            errors.append('Global tags cannot have organization_id')

        if not is_global and not organization_id:
            errors.append('Organization-specific tags must have organization_id')

        # Validate organization exists if provided
        if organization_id:
            organization = self.db.query(Organization).filter(
                Organization.id == organization_id,
                Organization.is_active == True
            ).first()
            if not organization:
                errors.append('Invalid organization_id: organization not found')

        # Validate color format
        if 'color' in tag_data:
            color = tag_data['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        # Check for duplicate names in the same scope
        if tag_data.get('name'):
            if is_global:
                # Check global tags
                existing = self.db.query(MaterialTag).filter(
                    MaterialTag.name == tag_data['name'],
                    MaterialTag.is_global == True,
                    MaterialTag.is_active == True
                ).first()
            else:
                # Check organization tags
                existing = self.db.query(MaterialTag).filter(
                    MaterialTag.name == tag_data['name'],
                    MaterialTag.is_global == False,
                    MaterialTag.organization_id == organization_id,
                    MaterialTag.is_active == True
                ).first()

            if existing:
                scope = 'globally' if is_global else f'in organization {organization_id}'
                errors.append(f'Tag with name "{tag_data["name"]}" already exists {scope}')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_tag_updates(self, tag: MaterialTag, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tag updates"""
        errors = []

        # Validate global/organization constraint if being updated
        if 'is_global' in updates or 'organization_id' in updates:
            is_global = updates.get('is_global', tag.is_global)
            organization_id = updates.get('organization_id', tag.organization_id)

            if is_global and organization_id:
                errors.append('Global tags cannot have organization_id')

            if not is_global and not organization_id:
                errors.append('Organization-specific tags must have organization_id')

        # Check for duplicate names if name is being updated
        if 'name' in updates:
            new_name = updates['name']
            is_global = updates.get('is_global', tag.is_global)
            organization_id = updates.get('organization_id', tag.organization_id)

            if is_global:
                # Check global tags
                existing = self.db.query(MaterialTag).filter(
                    MaterialTag.id != tag.id,
                    MaterialTag.name == new_name,
                    MaterialTag.is_global == True,
                    MaterialTag.is_active == True
                ).first()
            else:
                # Check organization tags
                existing = self.db.query(MaterialTag).filter(
                    MaterialTag.id != tag.id,
                    MaterialTag.name == new_name,
                    MaterialTag.is_global == False,
                    MaterialTag.organization_id == organization_id,
                    MaterialTag.is_active == True
                ).first()

            if existing:
                scope = 'globally' if is_global else f'in organization {organization_id}'
                errors.append(f'Tag with name "{new_name}" already exists {scope}')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _apply_tag_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to tag query"""

        if 'search' in filters and filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    MaterialTag.name.ilike(search_term),
                    MaterialTag.description.ilike(search_term)
                )
            )

        if 'is_global' in filters:
            query = query.filter(MaterialTag.is_global == filters['is_global'])

        if 'organization_id' in filters and filters['organization_id']:
            if filters.get('include_global', True):
                # Include both organization-specific and global tags
                query = query.filter(
                    or_(
                        and_(MaterialTag.is_global == False, MaterialTag.organization_id == filters['organization_id']),
                        MaterialTag.is_global == True
                    )
                )
            else:
                # Only organization-specific tags
                query = query.filter(
                    MaterialTag.is_global == False,
                    MaterialTag.organization_id == filters['organization_id']
                )

        if 'color' in filters and filters['color']:
            query = query.filter(MaterialTag.color == filters['color'])

        return query

    def _serialize_tag(self, tag: MaterialTag) -> Dict[str, Any]:
        """Serialize tag for API response"""
        return {
            'id': tag.id,
            'is_active': tag.is_active,
            'created_date': tag.created_date.isoformat() if tag.created_date else None,
            'updated_date': tag.updated_date.isoformat() if tag.updated_date else None,
            'deleted_date': tag.deleted_date.isoformat() if tag.deleted_date else None,

            'name': tag.name,
            'description': tag.description,
            'color': tag.color,
            'is_global': tag.is_global,
            'organization_id': tag.organization_id,

            'scope': 'global' if tag.is_global else 'organization'
        }