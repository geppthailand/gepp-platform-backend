"""
Main Materials management service
Handles CRUD operations for main materials (legacy system)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ....models.cores.references import MainMaterial, MaterialCategory
from ....exceptions import ValidationException, NotFoundException


class MainMaterialsService:
    """
    High-level main materials management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== MAIN MATERIAL CRUD OPERATIONS ==========

    def create_main_material(self, main_material_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new main material with validation
        """
        try:
            # Validate main material data
            validation_result = self._validate_main_material_data(main_material_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Main material validation failed: {error_messages}')

            # Create main material instance
            main_material = MainMaterial(
                name_th=main_material_data['name_th'],
                name_en=main_material_data['name_en'],
                name_local=main_material_data.get('name_local'),
                code=main_material_data.get('code'),
                color=main_material_data.get('color', '#808080'),
                display_order=main_material_data.get('display_order', 0),
                material_tag_groups=main_material_data.get('material_tag_groups', [])
            )

            self.db.add(main_material)
            self.db.flush()
            self.db.refresh(main_material)

            return {
                'success': True,
                'main_material': self._serialize_main_material(main_material)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_main_materials(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'display_order',
        sort_order: str = 'asc'
    ) -> Dict[str, Any]:
        """
        Get main materials with filtering, pagination, and sorting
        """
        try:
            query = self.db.query(MainMaterial).filter(MainMaterial.is_active == True)

            # Apply filters
            if filters:
                query = self._apply_main_material_filters(query, filters)

            # Get total count before pagination
            total_count = query.count()

            # Apply sorting
            if hasattr(MainMaterial, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(MainMaterial, sort_by).desc())
                else:
                    query = query.order_by(getattr(MainMaterial, sort_by))

            # Apply pagination
            offset = (page - 1) * page_size
            main_materials = query.offset(offset).limit(page_size).all()

            return {
                'data': [self._serialize_main_material(main_material) for main_material in main_materials],
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

    def get_main_material_by_id(self, main_material_id: int, include_relations: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get main material by ID with optional relationship loading
        """
        try:
            query = self.db.query(MainMaterial).filter(
                MainMaterial.id == main_material_id,
                MainMaterial.is_active == True
            )

            # No relationships to join since MainMaterial doesn't have category_id

            main_material = query.first()
            if not main_material:
                return None

            main_material_data = self._serialize_main_material(main_material)

            # No category relationship available

            return main_material_data

        except Exception as e:
            raise e

    def update_main_material(self, main_material_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update main material with validation
        """
        try:
            main_material = self.db.query(MainMaterial).filter(
                MainMaterial.id == main_material_id,
                MainMaterial.is_active == True
            ).first()

            if not main_material:
                raise NotFoundException('Main material not found')

            # Validate updates
            validation_result = self._validate_main_material_updates(main_material, updates)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Main material update validation failed: {error_messages}')

            # Apply updates
            for key, value in updates.items():
                if hasattr(main_material, key):
                    setattr(main_material, key, value)

            self.db.flush()
            self.db.refresh(main_material)

            return {
                'success': True,
                'main_material': self._serialize_main_material(main_material)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def delete_main_material(self, main_material_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete main material (soft delete by default)
        """
        try:
            main_material = self.db.query(MainMaterial).filter(MainMaterial.id == main_material_id).first()
            if not main_material:
                raise NotFoundException('Main material not found')

            # Check if main material is being used by any materials
            from ....models.cores.references import Material
            material_count = self.db.query(Material).filter(
                Material.main_material_id == main_material_id,
                Material.is_active == True
            ).count()

            if material_count > 0:
                raise ValidationException(f'Cannot delete main material: {material_count} materials are using it')

            if soft_delete:
                main_material.is_active = False
                from datetime import datetime, timezone
                main_material.deleted_date = datetime.now(timezone.utc)
            else:
                self.db.delete(main_material)

            self.db.flush()

            return {'success': True, 'message': 'Main material deleted successfully'}

        except Exception as e:
            self.db.rollback()
            raise e

    def list_main_materials(
        self,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all main materials
        """
        try:
            query = self.db.query(MainMaterial)

            if not include_inactive:
                query = query.filter(MainMaterial.is_active == True)

            main_materials = query.order_by(MainMaterial.display_order, MainMaterial.name_en).all()

            return [self._serialize_main_material(main_material) for main_material in main_materials]

        except Exception as e:
            raise e

    def get_main_materials_by_tag_groups(self, tag_group_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Get all main materials that contain any of the specified tag groups
        """
        try:
            from sqlalchemy import func

            main_materials = self.db.query(MainMaterial).filter(
                MainMaterial.is_active == True,
                func.array_length(MainMaterial.material_tag_groups, 1) > 0
            )

            # Filter by tag groups if provided
            if tag_group_ids:
                for tag_group_id in tag_group_ids:
                    main_materials = main_materials.filter(
                        MainMaterial.material_tag_groups.any(tag_group_id)
                    )

            results = main_materials.order_by(MainMaterial.display_order, MainMaterial.name_en).all()

            return [self._serialize_main_material(main_material) for main_material in results]

        except Exception as e:
            raise e

    def bulk_update_display_order(self, order_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk update display order for main materials
        order_updates: [{'id': 1, 'display_order': 0}, {'id': 2, 'display_order': 1}, ...]
        """
        try:
            updated_count = 0
            errors = []

            for update in order_updates:
                main_material_id = update.get('id')
                new_order = update.get('display_order')

                if not main_material_id or new_order is None:
                    errors.append('Each update must have id and display_order')
                    continue

                main_material = self.db.query(MainMaterial).filter(
                    MainMaterial.id == main_material_id,
                    MainMaterial.is_active == True
                ).first()

                if not main_material:
                    errors.append(f'Main material {main_material_id} not found')
                    continue

                main_material.display_order = new_order
                updated_count += 1

            if errors:
                self.db.rollback()
                return {
                    'success': False,
                    'errors': errors,
                    'updated_count': 0
                }

            self.db.flush()

            return {
                'success': True,
                'updated_count': updated_count,
                'message': f'Updated display order for {updated_count} main materials'
            }

        except Exception as e:
            self.db.rollback()
            raise e

    # ========== HELPER METHODS ==========

    def _validate_main_material_data(self, main_material_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate main material creation data"""
        errors = []

        # Required fields
        required_fields = ['name_th', 'name_en']
        for field in required_fields:
            if not main_material_data.get(field):
                errors.append(f'{field} is required')

        # No category validation needed since MainMaterial doesn't have category_id

        # Validate numeric fields
        if 'display_order' in main_material_data:
            try:
                int(main_material_data['display_order'])
            except (ValueError, TypeError):
                errors.append('display_order must be a valid integer')

        # Validate color format
        if 'color' in main_material_data:
            color = main_material_data['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        # Check for duplicate names or codes
        existing = self.db.query(MainMaterial).filter(
            MainMaterial.is_active == True,
            or_(
                MainMaterial.name_en == main_material_data.get('name_en'),
                MainMaterial.name_th == main_material_data.get('name_th'),
                MainMaterial.code == main_material_data.get('code') if main_material_data.get('code') else False
            )
        ).first()

        if existing:
            errors.append('Main material with this name or code already exists')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_main_material_updates(self, main_material: MainMaterial, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate main material updates"""
        errors = []

        # No category validation needed since MainMaterial doesn't have category_id

        # Check for duplicate names or codes if being updated
        if 'name_en' in updates or 'name_th' in updates or 'code' in updates:
            name_en = updates.get('name_en', main_material.name_en)
            name_th = updates.get('name_th', main_material.name_th)
            code = updates.get('code', main_material.code)

            existing = self.db.query(MainMaterial).filter(
                MainMaterial.id != main_material.id,
                MainMaterial.is_active == True,
                or_(
                    MainMaterial.name_en == name_en,
                    MainMaterial.name_th == name_th,
                    MainMaterial.code == code if code else False
                )
            ).first()

            if existing:
                errors.append('Main material with this name or code already exists')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _apply_main_material_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to main material query"""

        if 'search' in filters and filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    MainMaterial.name_en.ilike(search_term),
                    MainMaterial.name_th.ilike(search_term),
                    MainMaterial.name_local.ilike(search_term),
                    MainMaterial.code.ilike(search_term)
                )
            )

        # No category filters available since MainMaterial doesn't have category_id

        return query

    def _serialize_main_material(self, main_material: MainMaterial) -> Dict[str, Any]:
        """Serialize main material for API response"""
        return {
            'id': main_material.id,
            'is_active': main_material.is_active,
            'created_date': main_material.created_date.isoformat() if main_material.created_date else None,
            'updated_date': main_material.updated_date.isoformat() if main_material.updated_date else None,
            'deleted_date': main_material.deleted_date.isoformat() if main_material.deleted_date else None,

            'name_th': main_material.name_th,
            'name_en': main_material.name_en,
            'name_local': main_material.name_local,
            'code': main_material.code,
            'color': main_material.color,
            'display_order': main_material.display_order,
            'material_tag_groups': main_material.material_tag_groups
        }