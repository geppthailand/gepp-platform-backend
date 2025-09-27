"""
Material Tag Groups management service
Handles CRUD operations for material tag groups (new tag-based system)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from ....models.cores.references import MaterialTagGroup, MaterialTag
from ....models.subscriptions.organizations import Organization
from ....exceptions import ValidationException, NotFoundException


class TagGroupsService:
    """
    High-level material tag groups management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== MATERIAL TAG GROUP CRUD OPERATIONS ==========

    def create_tag_group(self, tag_group_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new material tag group with validation
        """
        try:
            # Validate tag group data
            validation_result = self._validate_tag_group_data(tag_group_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Tag group validation failed: {error_messages}')

            # Create tag group instance
            tag_group = MaterialTagGroup(
                name=tag_group_data['name'],
                description=tag_group_data.get('description'),
                color=tag_group_data.get('color', '#808080'),
                is_global=tag_group_data.get('is_global', False),
                tags=tag_group_data.get('tags', []),
                organization_id=tag_group_data.get('organization_id')
            )

            self.db.add(tag_group)
            self.db.flush()
            self.db.refresh(tag_group)

            return {
                'success': True,
                'tag_group': self._serialize_tag_group(tag_group)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_tag_groups(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = 'name',
        sort_order: str = 'asc'
    ) -> Dict[str, Any]:
        """
        Get tag groups with filtering, pagination, and sorting
        """
        try:
            query = self.db.query(MaterialTagGroup).filter(MaterialTagGroup.is_active == True)

            # Apply filters
            if filters:
                query = self._apply_tag_group_filters(query, filters)

            # Get total count before pagination
            total_count = query.count()

            # Apply sorting
            if hasattr(MaterialTagGroup, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(MaterialTagGroup, sort_by).desc())
                else:
                    query = query.order_by(getattr(MaterialTagGroup, sort_by))

            # Apply pagination
            offset = (page - 1) * page_size
            tag_groups = query.offset(offset).limit(page_size).all()

            return {
                'data': [self._serialize_tag_group(tag_group) for tag_group in tag_groups],
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

    def get_tag_group_by_id(self, tag_group_id: int, include_relations: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get tag group by ID with optional relationship loading
        """
        try:
            query = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.id == tag_group_id,
                MaterialTagGroup.is_active == True
            )

            if include_relations:
                query = query.join(Organization, MaterialTagGroup.organization_id == Organization.id, isouter=True)

            tag_group = query.first()
            if not tag_group:
                return None

            tag_group_data = self._serialize_tag_group(tag_group)

            # Add organization information if available
            if include_relations and tag_group.organization:
                tag_group_data['organization'] = {
                    'id': tag_group.organization.id,
                    'name': tag_group.organization.name,
                    'display_name': tag_group.organization.display_name
                }

            # Add detailed tag information if requested
            if include_relations and tag_group.tags:
                tag_group_data['tag_details'] = self._get_tag_details(tag_group.tags)

            return tag_group_data

        except Exception as e:
            raise e

    def update_tag_group(self, tag_group_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update tag group with validation
        """
        try:
            tag_group = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.id == tag_group_id,
                MaterialTagGroup.is_active == True
            ).first()

            if not tag_group:
                raise NotFoundException('Tag group not found')

            # Validate updates
            validation_result = self._validate_tag_group_updates(tag_group, updates)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Tag group update validation failed: {error_messages}')

            # Apply updates
            for key, value in updates.items():
                if hasattr(tag_group, key):
                    setattr(tag_group, key, value)

            self.db.flush()
            self.db.refresh(tag_group)

            return {
                'success': True,
                'tag_group': self._serialize_tag_group(tag_group)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def delete_tag_group(self, tag_group_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete tag group (soft delete by default)
        """
        try:
            tag_group = self.db.query(MaterialTagGroup).filter(MaterialTagGroup.id == tag_group_id).first()
            if not tag_group:
                raise NotFoundException('Tag group not found')

            # Check if tag group is being used in any main materials
            from ....models.cores.references import MainMaterial
            main_material_count = self.db.query(MainMaterial).filter(
                MainMaterial.tag_groups.any(tag_group_id),
                MainMaterial.is_active == True
            ).count()

            if main_material_count > 0:
                raise ValidationException(f'Cannot delete tag group: {main_material_count} main materials are using it')

            if soft_delete:
                tag_group.is_active = False
                from datetime import datetime, timezone
                tag_group.deleted_date = datetime.now(timezone.utc)
            else:
                self.db.delete(tag_group)

            self.db.flush()

            return {'success': True, 'message': 'Tag group deleted successfully'}

        except Exception as e:
            self.db.rollback()
            raise e

    def list_tag_groups(
        self,
        organization_id: Optional[int] = None,
        include_global: bool = True,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List tag groups with organization and global filtering
        """
        try:
            query = self.db.query(MaterialTagGroup)

            if not include_inactive:
                query = query.filter(MaterialTagGroup.is_active == True)

            # Filter by scope
            if organization_id:
                if include_global:
                    # Include both organization-specific and global tag groups
                    query = query.filter(
                        or_(
                            and_(MaterialTagGroup.is_global == False, MaterialTagGroup.organization_id == organization_id),
                            MaterialTagGroup.is_global == True
                        )
                    )
                else:
                    # Only organization-specific tag groups
                    query = query.filter(
                        MaterialTagGroup.is_global == False,
                        MaterialTagGroup.organization_id == organization_id
                    )
            elif include_global:
                # Only global tag groups
                query = query.filter(MaterialTagGroup.is_global == True)

            tag_groups = query.order_by(MaterialTagGroup.name).all()

            return [self._serialize_tag_group(tag_group) for tag_group in tag_groups]

        except Exception as e:
            raise e

    def add_tags_to_group(self, tag_group_id: int, tag_ids: List[int]) -> Dict[str, Any]:
        """
        Add tags to a tag group
        """
        try:
            tag_group = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.id == tag_group_id,
                MaterialTagGroup.is_active == True
            ).first()

            if not tag_group:
                raise NotFoundException('Tag group not found')

            # Validate that all tags exist and are compatible
            validation_result = self._validate_tags_for_group(tag_group, tag_ids)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Tag validation failed: {error_messages}')

            # Add new tags to existing tags (avoid duplicates)
            current_tags = set(tag_group.tags or [])
            new_tags = set(tag_ids)
            updated_tags = list(current_tags.union(new_tags))

            tag_group.tags = updated_tags
            self.db.flush()
            self.db.refresh(tag_group)

            return {
                'success': True,
                'tag_group': self._serialize_tag_group(tag_group),
                'added_count': len(new_tags - current_tags)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def remove_tags_from_group(self, tag_group_id: int, tag_ids: List[int]) -> Dict[str, Any]:
        """
        Remove tags from a tag group
        """
        try:
            tag_group = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.id == tag_group_id,
                MaterialTagGroup.is_active == True
            ).first()

            if not tag_group:
                raise NotFoundException('Tag group not found')

            # Remove tags from the group
            current_tags = set(tag_group.tags or [])
            tags_to_remove = set(tag_ids)
            updated_tags = list(current_tags - tags_to_remove)

            tag_group.tags = updated_tags
            self.db.flush()
            self.db.refresh(tag_group)

            return {
                'success': True,
                'tag_group': self._serialize_tag_group(tag_group),
                'removed_count': len(tags_to_remove.intersection(current_tags))
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_tag_groups_with_tags(
        self,
        organization_id: Optional[int] = None,
        include_global: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get tag groups with their associated tag details
        """
        try:
            tag_groups = self.list_tag_groups(
                organization_id=organization_id,
                include_global=include_global
            )

            # Add tag details to each group
            for tag_group in tag_groups:
                if tag_group.get('tags'):
                    tag_group['tag_details'] = self._get_tag_details(tag_group['tags'])

            return tag_groups

        except Exception as e:
            raise e

    # ========== HELPER METHODS ==========

    def _validate_tag_group_data(self, tag_group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tag group creation data"""
        errors = []

        # Required fields
        if not tag_group_data.get('name'):
            errors.append('name is required')

        # Validate global/organization constraint
        is_global = tag_group_data.get('is_global', False)
        organization_id = tag_group_data.get('organization_id')

        if is_global and organization_id:
            errors.append('Global tag groups cannot have organization_id')

        if not is_global and not organization_id:
            errors.append('Organization-specific tag groups must have organization_id')

        # Validate organization exists if provided
        if organization_id:
            organization = self.db.query(Organization).filter(
                Organization.id == organization_id,
                Organization.is_active == True
            ).first()
            if not organization:
                errors.append('Invalid organization_id: organization not found')

        # Validate color format
        if 'color' in tag_group_data:
            color = tag_group_data['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        # Validate tags if provided
        if 'tags' in tag_group_data and tag_group_data['tags']:
            tag_validation = self._validate_tag_ids(tag_group_data['tags'], organization_id, is_global)
            if not tag_validation['valid']:
                errors.extend(tag_validation['errors'])

        # Check for duplicate names in the same scope
        if tag_group_data.get('name'):
            if is_global:
                # Check global tag groups
                existing = self.db.query(MaterialTagGroup).filter(
                    MaterialTagGroup.name == tag_group_data['name'],
                    MaterialTagGroup.is_global == True,
                    MaterialTagGroup.is_active == True
                ).first()
            else:
                # Check organization tag groups
                existing = self.db.query(MaterialTagGroup).filter(
                    MaterialTagGroup.name == tag_group_data['name'],
                    MaterialTagGroup.is_global == False,
                    MaterialTagGroup.organization_id == organization_id,
                    MaterialTagGroup.is_active == True
                ).first()

            if existing:
                scope = 'globally' if is_global else f'in organization {organization_id}'
                errors.append(f'Tag group with name "{tag_group_data["name"]}" already exists {scope}')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_tag_group_updates(self, tag_group: MaterialTagGroup, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tag group updates"""
        errors = []

        # Validate global/organization constraint if being updated
        if 'is_global' in updates or 'organization_id' in updates:
            is_global = updates.get('is_global', tag_group.is_global)
            organization_id = updates.get('organization_id', tag_group.organization_id)

            if is_global and organization_id:
                errors.append('Global tag groups cannot have organization_id')

            if not is_global and not organization_id:
                errors.append('Organization-specific tag groups must have organization_id')

        # Check for duplicate names if name is being updated
        if 'name' in updates:
            new_name = updates['name']
            is_global = updates.get('is_global', tag_group.is_global)
            organization_id = updates.get('organization_id', tag_group.organization_id)

            if is_global:
                # Check global tag groups
                existing = self.db.query(MaterialTagGroup).filter(
                    MaterialTagGroup.id != tag_group.id,
                    MaterialTagGroup.name == new_name,
                    MaterialTagGroup.is_global == True,
                    MaterialTagGroup.is_active == True
                ).first()
            else:
                # Check organization tag groups
                existing = self.db.query(MaterialTagGroup).filter(
                    MaterialTagGroup.id != tag_group.id,
                    MaterialTagGroup.name == new_name,
                    MaterialTagGroup.is_global == False,
                    MaterialTagGroup.organization_id == organization_id,
                    MaterialTagGroup.is_active == True
                ).first()

            if existing:
                scope = 'globally' if is_global else f'in organization {organization_id}'
                errors.append(f'Tag group with name "{new_name}" already exists {scope}')

        # Validate tags if being updated
        if 'tags' in updates:
            is_global = updates.get('is_global', tag_group.is_global)
            organization_id = updates.get('organization_id', tag_group.organization_id)
            tag_validation = self._validate_tag_ids(updates['tags'], organization_id, is_global)
            if not tag_validation['valid']:
                errors.extend(tag_validation['errors'])

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_tags_for_group(self, tag_group: MaterialTagGroup, tag_ids: List[int]) -> Dict[str, Any]:
        """Validate that tags are compatible with the tag group"""
        return self._validate_tag_ids(tag_ids, tag_group.organization_id, tag_group.is_global)

    def _validate_tag_ids(self, tag_ids: List[int], organization_id: Optional[int], is_global: bool) -> Dict[str, Any]:
        """Validate that tag IDs exist and are compatible with the scope"""
        errors = []

        for tag_id in tag_ids:
            tag = self.db.query(MaterialTag).filter(
                MaterialTag.id == tag_id,
                MaterialTag.is_active == True
            ).first()

            if not tag:
                errors.append(f'Tag {tag_id} not found')
                continue

            # Check scope compatibility
            if is_global:
                # Global tag groups can contain both global and organization tags
                if not tag.is_global and tag.organization_id != organization_id:
                    errors.append(f'Tag {tag_id} belongs to a different organization')
            else:
                # Organization tag groups can only contain global tags or tags from the same organization
                if not tag.is_global and tag.organization_id != organization_id:
                    errors.append(f'Tag {tag_id} is not accessible to this organization')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _get_tag_details(self, tag_ids: List[int]) -> List[Dict[str, Any]]:
        """Get detailed information for a list of tag IDs"""
        if not tag_ids:
            return []

        tags = self.db.query(MaterialTag).filter(
            MaterialTag.id.in_(tag_ids),
            MaterialTag.is_active == True
        ).all()

        return [
            {
                'id': tag.id,
                'name': tag.name,
                'description': tag.description,
                'color': tag.color,
                'is_global': tag.is_global,
                'organization_id': tag.organization_id
            }
            for tag in tags
        ]

    def _apply_tag_group_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to tag group query"""

        if 'search' in filters and filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    MaterialTagGroup.name.ilike(search_term),
                    MaterialTagGroup.description.ilike(search_term)
                )
            )

        if 'is_global' in filters:
            query = query.filter(MaterialTagGroup.is_global == filters['is_global'])

        if 'organization_id' in filters and filters['organization_id']:
            if filters.get('include_global', True):
                # Include both organization-specific and global tag groups
                query = query.filter(
                    or_(
                        and_(MaterialTagGroup.is_global == False, MaterialTagGroup.organization_id == filters['organization_id']),
                        MaterialTagGroup.is_global == True
                    )
                )
            else:
                # Only organization-specific tag groups
                query = query.filter(
                    MaterialTagGroup.is_global == False,
                    MaterialTagGroup.organization_id == filters['organization_id']
                )

        if 'has_tags' in filters:
            if filters['has_tags']:
                query = query.filter(MaterialTagGroup.tags != '{}')
            else:
                query = query.filter(MaterialTagGroup.tags == '{}')

        return query

    def _serialize_tag_group(self, tag_group: MaterialTagGroup) -> Dict[str, Any]:
        """Serialize tag group for API response"""
        return {
            'id': tag_group.id,
            'is_active': tag_group.is_active,
            'created_date': tag_group.created_date.isoformat() if tag_group.created_date else None,
            'updated_date': tag_group.updated_date.isoformat() if tag_group.updated_date else None,
            'deleted_date': tag_group.deleted_date.isoformat() if tag_group.deleted_date else None,

            'name': tag_group.name,
            'description': tag_group.description,
            'color': tag_group.color,
            'is_global': tag_group.is_global,
            'tags': tag_group.tags or [],
            'organization_id': tag_group.organization_id,

            'scope': 'global' if tag_group.is_global else 'organization',
            'tag_count': len(tag_group.tags) if tag_group.tags else 0
        }