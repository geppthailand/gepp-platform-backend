"""
Materials management service
Handles CRUD operations for materials with tag-based system support
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ....models.cores.references import Material, MaterialTag, MaterialTagGroup, MaterialCategory, MainMaterial
from ....exceptions import ValidationException, NotFoundException


class MaterialsService:
    """
    High-level materials management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== MATERIAL CRUD OPERATIONS ==========

    def create_material(self, material_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new material with validation and business logic
        Supports both legacy (category_id, main_material_id) and new (main_material_id with tags) systems
        """
        try:
            # Validate material data
            validation_result = self._validate_material_data(material_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Material validation failed: {error_messages}')

            # Create material instance
            material = Material(
                # Legacy structure
                category_id=material_data.get('category_id'),
                main_material_id=material_data.get('main_material_id'),

                # New tag-based structure (using main_material_id)
                tags=material_data.get('tags', []),

                # Multi-tenant support
                is_global=material_data.get('is_global', True),
                organization_id=material_data.get('organization_id'),

                # Material properties
                unit_name_th=material_data['unit_name_th'],
                unit_name_en=material_data['unit_name_en'],
                unit_weight=material_data.get('unit_weight', 1),
                color=material_data.get('color', '#808080'),
                calc_ghg=material_data.get('calc_ghg', 0),
                name_th=material_data['name_th'],
                name_en=material_data['name_en']
            )

            self.db.add(material)
            self.db.flush()
            self.db.refresh(material)

            return {
                'success': True,
                'material': self._serialize_material(material)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_materials(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_date',
        sort_order: str = 'desc',
        user_organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get materials with filtering, pagination, and sorting
        """
        try:
            # Base query with organization filtering
            query = self.db.query(Material).filter(Material.is_active == True)

            # Apply organization-based filtering: global materials OR user's organization materials
            if user_organization_id:
                query = query.filter(
                    or_(
                        Material.is_global == True,
                        Material.organization_id == user_organization_id
                    )
                )
            else:
                # If no user organization provided, only show global materials
                query = query.filter(Material.is_global == True)

            print(page_size)
            # Apply additional filters
            if filters:
                query = self._apply_material_filters(query, filters)

            # Get total count before pagination
            total_count = query.count()

            # Apply sorting
            if hasattr(Material, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(Material, sort_by).desc())
                else:
                    query = query.order_by(getattr(Material, sort_by))

            # Apply pagination
            offset = (page - 1) * page_size
            materials = query.offset(offset).limit(page_size).all()

            return {
                'data': [self._serialize_material(material) for material in materials],
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

    def get_material_by_id(self, material_id: int, include_relations: bool = False, user_organization_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get material by ID with optional relationship loading
        """
        try:
            query = self.db.query(Material).filter(
                Material.id == material_id,
                Material.is_active == True
            )

            # Apply organization-based filtering: global materials OR user's organization materials
            if user_organization_id:
                query = query.filter(
                    or_(
                        Material.is_global == True,
                        Material.organization_id == user_organization_id
                    )
                )
            else:
                # If no user organization provided, only show global materials
                query = query.filter(Material.is_global == True)

            if include_relations:
                query = query.join(MaterialCategory, Material.category_id == MaterialCategory.id, isouter=True) \
                            .join(MainMaterial, Material.main_material_id == MainMaterial.id, isouter=True)

            material = query.first()
            if not material:
                return None

            material_data = self._serialize_material(material)

            # Add resolved tag information if using tag-based system
            if material.main_material_id and material.tags:
                material_data['resolved_tags'] = self._resolve_material_tags(material.tags)

            return material_data

        except Exception as e:
            raise e

    def update_material(self, material_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update material with validation
        """
        try:
            material = self.db.query(Material).filter(
                Material.id == material_id,
                Material.is_active == True
            ).first()

            if not material:
                raise NotFoundException('Material not found')

            # Validate updates
            validation_result = self._validate_material_updates(material, updates)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Material update validation failed: {error_messages}')

            # Apply updates
            for key, value in updates.items():
                if hasattr(material, key):
                    setattr(material, key, value)

            self.db.flush()
            self.db.refresh(material)

            return {
                'success': True,
                'material': self._serialize_material(material)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def delete_material(self, material_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete material (soft delete by default)
        """
        try:
            material = self.db.query(Material).filter(Material.id == material_id).first()
            if not material:
                raise NotFoundException('Material not found')

            if soft_delete:
                material.is_active = False
                from datetime import datetime, timezone
                material.deleted_date = datetime.now(timezone.utc)
            else:
                self.db.delete(material)

            self.db.flush()

            return {'success': True, 'message': 'Material deleted successfully'}

        except Exception as e:
            self.db.rollback()
            raise e

    def list_materials(
        self,
        category_id: Optional[int] = None,
        main_material_id: Optional[int] = None,
        tag_combinations: Optional[List[List[int]]] = None,
        include_inactive: bool = False,
        user_organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List materials with various filtering options
        """
        try:
            query = self.db.query(Material)

            if not include_inactive:
                query = query.filter(Material.is_active == True)

            # Apply organization-based filtering: global materials OR user's organization materials
            if user_organization_id:
                query = query.filter(
                    or_(
                        Material.is_global == True,
                        Material.organization_id == user_organization_id
                    )
                )
            else:
                # If no user organization provided, only show global materials
                query = query.filter(Material.is_global == True)

            # Legacy filtering
            if category_id:
                query = query.filter(Material.category_id == category_id)

            if main_material_id:
                query = query.filter(Material.main_material_id == main_material_id)

            # Tag-based filtering
            if tag_combinations:
                # Filter by tag combinations using JSONB containment
                for tag_combo in tag_combinations:
                    query = query.filter(Material.tags.op('@>')(f'[{tag_combo}]'))

            materials = query.order_by(Material.name_en).all()

            return [self._serialize_material(material) for material in materials]

        except Exception as e:
            raise e

    # ========== HELPER METHODS ==========

    def _validate_material_data(self, material_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate material creation data"""
        errors = []

        # Required fields
        required_fields = ['name_th', 'name_en', 'unit_name_th', 'unit_name_en']
        for field in required_fields:
            if not material_data.get(field):
                errors.append(f'{field} is required')

        # System validation - must use either legacy or new system, not both
        has_legacy = material_data.get('category_id') or material_data.get('main_material_id')
        has_new = material_data.get('tags')

        if has_legacy and has_new:
            errors.append('Cannot mix legacy (category_id only) and new (main_material_id with tags) systems')

        if not has_legacy and not has_new:
            errors.append('Must specify either legacy system (category_id) or new system (main_material_id with/without tags)')

        # Validate tag combinations if using new system
        if material_data.get('main_material_id') and material_data.get('tags'):
            tag_validation = self._validate_tag_combinations(
                material_data['main_material_id'],
                material_data['tags']
            )
            if not tag_validation['valid']:
                errors.extend(tag_validation['errors'])

        # Validate numeric fields
        numeric_fields = ['unit_weight', 'calc_ghg']
        for field in numeric_fields:
            if field in material_data and material_data[field] is not None:
                try:
                    float(material_data[field])
                except (ValueError, TypeError):
                    errors.append(f'{field} must be a valid number')

        # Validate color format
        if 'color' in material_data:
            color = material_data['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        # Validate organization consistency
        is_global = material_data.get('is_global', True)
        organization_id = material_data.get('organization_id')

        if is_global and organization_id is not None:
            errors.append('Global materials cannot have an organization_id')
        elif not is_global and organization_id is None:
            errors.append('Non-global materials must have an organization_id')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_material_updates(self, material: Material, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate material updates"""
        errors = []

        # Validate tag combinations if updating tags
        if 'tags' in updates and material.main_material_id:
            tag_validation = self._validate_tag_combinations(
                material.main_material_id,
                updates['tags']
            )
            if not tag_validation['valid']:
                errors.extend(tag_validation['errors'])

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_tag_combinations(self, main_material_id: int, tags: List[List[int]]) -> Dict[str, Any]:
        """Validate that tag combinations are valid for the main material"""
        errors = []

        try:
            # Get main material with its allowed tag groups
            main_material = self.db.query(MainMaterial).filter(
                MainMaterial.id == main_material_id,
                MainMaterial.is_active == True
            ).first()

            if not main_material:
                errors.append(f'Main material {main_material_id} not found')
                return {'valid': False, 'errors': errors}

            allowed_tag_groups = main_material.material_tag_groups or []

            for tag_group_id, tag_id in tags:
                # Check if tag group is allowed for this main material
                if tag_group_id not in allowed_tag_groups:
                    errors.append(f'Tag group {tag_group_id} not allowed for main material {main_material_id}')
                    continue

                # Check if tag belongs to the specified group
                tag_group = self.db.query(MaterialTagGroup).filter(
                    MaterialTagGroup.id == tag_group_id,
                    MaterialTagGroup.is_active == True
                ).first()

                if not tag_group:
                    errors.append(f'Tag group {tag_group_id} not found')
                    continue

                if tag_id not in (tag_group.tags or []):
                    errors.append(f'Tag {tag_id} does not belong to group {tag_group_id}')

        except Exception as e:
            errors.append(f'Tag validation error: {str(e)}')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _apply_material_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to material query"""

        if 'search' in filters and filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    Material.name_en.ilike(search_term),
                    Material.name_th.ilike(search_term)
                )
            )

        if 'category_id' in filters and filters['category_id']:
            query = query.filter(Material.category_id == filters['category_id'])

        if 'main_material_id' in filters and filters['main_material_id']:
            query = query.filter(Material.main_material_id == filters['main_material_id'])

        # base_material_id filter removed - now using main_material_id only

        if 'has_tags' in filters:
            if filters['has_tags']:
                query = query.filter(Material.tags != '[]')
            else:
                query = query.filter(Material.tags == '[]')

        return query

    def _resolve_material_tags(self, tags: List[List[int]]) -> List[Dict[str, Any]]:
        """Resolve tag IDs to tag and group information"""
        resolved_tags = []

        for tag_group_id, tag_id in tags:
            # Get tag group
            tag_group = self.db.query(MaterialTagGroup).filter(
                MaterialTagGroup.id == tag_group_id,
                MaterialTagGroup.is_active == True
            ).first()

            # Get tag
            tag = self.db.query(MaterialTag).filter(
                MaterialTag.id == tag_id,
                MaterialTag.is_active == True
            ).first()

            if tag_group and tag:
                resolved_tags.append({
                    'group': {
                        'id': tag_group.id,
                        'name': tag_group.name,
                        'color': tag_group.color
                    },
                    'tag': {
                        'id': tag.id,
                        'name': tag.name,
                        'color': tag.color
                    }
                })

        return resolved_tags

    def _serialize_material(self, material: Material) -> Dict[str, Any]:
        """Serialize material for API response"""
        return {
            'id': material.id,
            'is_active': material.is_active,
            'created_date': material.created_date.isoformat() if material.created_date else None,
            'updated_date': material.updated_date.isoformat() if material.updated_date else None,
            'deleted_date': material.deleted_date.isoformat() if material.deleted_date else None,

            # Legacy structure
            'category_id': material.category_id,
            'main_material_id': material.main_material_id,

            # Tag-based structure (using main_material_id)
            'tags': material.tags,

            # Multi-tenant support
            'is_global': material.is_global,
            'organization_id': material.organization_id,

            # Material properties
            'unit_name_th': material.unit_name_th,
            'unit_name_en': material.unit_name_en,
            'unit_weight': float(material.unit_weight) if material.unit_weight else None,
            'color': material.color,
            'calc_ghg': float(material.calc_ghg) if material.calc_ghg else None,
            'name_th': material.name_th,
            'name_en': material.name_en,

            # System indicator
            'system_type': self._determine_system_type(material)
        }

    def _determine_system_type(self, material: Material) -> str:
        """Determine which system the material uses"""
        has_legacy = material.category_id and not material.main_material_id
        has_new = material.main_material_id and (material.tags and len(material.tags) > 0)
        has_simple = material.main_material_id and (not material.tags or len(material.tags) == 0)

        if has_legacy and (has_new or has_simple):
            return 'hybrid'
        elif has_new:
            return 'tag_based'
        elif has_simple:
            return 'main_material'
        elif has_legacy:
            return 'legacy'
        else:
            return 'undefined'