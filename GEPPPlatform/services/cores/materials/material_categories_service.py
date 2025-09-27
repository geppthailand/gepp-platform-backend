"""
Material Categories management service
Handles CRUD operations for material categories (legacy system)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from ....models.cores.references import MaterialCategory
from ....exceptions import ValidationException, NotFoundException


class MaterialCategoriesService:
    """
    High-level material categories management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== MATERIAL CATEGORY CRUD OPERATIONS ==========

    def create_material_category(self, category_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new material category with validation
        """
        try:
            # Validate category data
            validation_result = self._validate_category_data(category_data)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Category validation failed: {error_messages}')

            # Create category instance
            category = MaterialCategory(
                name_th=category_data['name_th'],
                name_en=category_data['name_en'],
                code=category_data.get('code'),
                description=category_data.get('description'),
                color=category_data.get('color', '#808080')
            )

            self.db.add(category)
            self.db.flush()
            self.db.refresh(category)

            return {
                'success': True,
                'category': self._serialize_category(category)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_material_categories(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'display_order',
        sort_order: str = 'asc'
    ) -> Dict[str, Any]:
        """
        Get material categories with filtering, pagination, and sorting
        """
        try:
            query = self.db.query(MaterialCategory).filter(MaterialCategory.is_active == True)

            # Apply filters
            if filters:
                query = self._apply_category_filters(query, filters)

            # Get total count before pagination
            total_count = query.count()

            # Apply sorting
            if hasattr(MaterialCategory, sort_by):
                if sort_order.lower() == 'desc':
                    query = query.order_by(getattr(MaterialCategory, sort_by).desc())
                else:
                    query = query.order_by(getattr(MaterialCategory, sort_by))

            # Apply pagination
            offset = (page - 1) * page_size
            categories = query.offset(offset).limit(page_size).all()

            return {
                'data': [self._serialize_category(category) for category in categories],
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

    def get_material_category_by_id(self, category_id: int, include_relations: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get material category by ID with optional relationship loading
        """
        try:
            category = self.db.query(MaterialCategory).filter(
                MaterialCategory.id == category_id,
                MaterialCategory.is_active == True
            ).first()

            if not category:
                return None

            category_data = self._serialize_category(category)

            # Add related main materials count if requested
            if include_relations:
                from ....models.cores.references import MainMaterial
                main_materials_count = self.db.query(MainMaterial).filter(
                    MainMaterial.category_id == category_id,
                    MainMaterial.is_active == True
                ).count()

                category_data['main_materials_count'] = main_materials_count

                # Add materials count
                from ....models.cores.references import Material
                materials_count = self.db.query(Material).filter(
                    Material.category_id == category_id,
                    Material.is_active == True
                ).count()

                category_data['materials_count'] = materials_count

            return category_data

        except Exception as e:
            raise e

    def update_material_category(self, category_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update material category with validation
        """
        try:
            category = self.db.query(MaterialCategory).filter(
                MaterialCategory.id == category_id,
                MaterialCategory.is_active == True
            ).first()

            if not category:
                raise NotFoundException('Material category not found')

            # Validate updates
            validation_result = self._validate_category_updates(category, updates)
            if not validation_result['valid']:
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'Category update validation failed: {error_messages}')

            # Apply updates
            for key, value in updates.items():
                if hasattr(category, key):
                    setattr(category, key, value)

            self.db.flush()
            self.db.refresh(category)

            return {
                'success': True,
                'category': self._serialize_category(category)
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def delete_material_category(self, category_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete material category (soft delete by default)
        """
        try:
            category = self.db.query(MaterialCategory).filter(MaterialCategory.id == category_id).first()
            if not category:
                raise NotFoundException('Material category not found')

            # Check if category is being used by any main materials
            from ....models.cores.references import MainMaterial
            main_material_count = self.db.query(MainMaterial).filter(
                MainMaterial.category_id == category_id,
                MainMaterial.is_active == True
            ).count()

            if main_material_count > 0:
                raise ValidationException(f'Cannot delete category: {main_material_count} main materials are using it')

            # Check if category is being used by any materials (legacy system)
            from ....models.cores.references import Material
            material_count = self.db.query(Material).filter(
                Material.category_id == category_id,
                Material.is_active == True
            ).count()

            if material_count > 0:
                raise ValidationException(f'Cannot delete category: {material_count} materials are using it')

            if soft_delete:
                category.is_active = False
                from datetime import datetime, timezone
                category.deleted_date = datetime.now(timezone.utc)
            else:
                self.db.delete(category)

            self.db.flush()

            return {'success': True, 'message': 'Material category deleted successfully'}

        except Exception as e:
            self.db.rollback()
            raise e

    def list_material_categories(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        List all material categories
        """
        try:
            query = self.db.query(MaterialCategory)

            if not include_inactive:
                query = query.filter(MaterialCategory.is_active == True)

            categories = query.order_by(MaterialCategory.display_order, MaterialCategory.name_en).all()

            return [self._serialize_category(category) for category in categories]

        except Exception as e:
            raise e

    def get_categories_with_main_materials_count(self) -> List[Dict[str, Any]]:
        """
        Get all categories with their main materials count
        """
        try:
            from sqlalchemy import func
            from ....models.cores.references import MainMaterial

            # Query categories with main materials count
            results = self.db.query(
                MaterialCategory,
                func.count(MainMaterial.id).label('main_materials_count')
            ).outerjoin(
                MainMaterial,
                and_(
                    MainMaterial.category_id == MaterialCategory.id,
                    MainMaterial.is_active == True
                )
            ).filter(
                MaterialCategory.is_active == True
            ).group_by(MaterialCategory.id).order_by(
                MaterialCategory.display_order,
                MaterialCategory.name_en
            ).all()

            categories_data = []
            for category, count in results:
                category_data = self._serialize_category(category)
                category_data['main_materials_count'] = count
                categories_data.append(category_data)

            return categories_data

        except Exception as e:
            raise e

    def bulk_update_display_order(self, order_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk update display order for material categories
        order_updates: [{'id': 1, 'display_order': 0}, {'id': 2, 'display_order': 1}, ...]
        """
        try:
            updated_count = 0
            errors = []

            for update in order_updates:
                category_id = update.get('id')
                new_order = update.get('display_order')

                if not category_id or new_order is None:
                    errors.append('Each update must have id and display_order')
                    continue

                category = self.db.query(MaterialCategory).filter(
                    MaterialCategory.id == category_id,
                    MaterialCategory.is_active == True
                ).first()

                if not category:
                    errors.append(f'Category {category_id} not found')
                    continue

                category.display_order = new_order
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
                'message': f'Updated display order for {updated_count} categories'
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def get_category_hierarchy(self) -> List[Dict[str, Any]]:
        """
        Get category hierarchy with main materials and materials counts
        """
        try:
            from sqlalchemy import func
            from ....models.cores.references import MainMaterial, Material

            # Get categories with counts
            results = self.db.query(
                MaterialCategory,
                func.count(MainMaterial.id.distinct()).label('main_materials_count'),
                func.count(Material.id.distinct()).label('materials_count')
            ).outerjoin(
                MainMaterial,
                and_(
                    MainMaterial.category_id == MaterialCategory.id,
                    MainMaterial.is_active == True
                )
            ).outerjoin(
                Material,
                and_(
                    Material.category_id == MaterialCategory.id,
                    Material.is_active == True
                )
            ).filter(
                MaterialCategory.is_active == True
            ).group_by(MaterialCategory.id).order_by(
                MaterialCategory.display_order,
                MaterialCategory.name_en
            ).all()

            hierarchy = []
            for category, main_materials_count, materials_count in results:
                category_data = self._serialize_category(category)
                category_data['main_materials_count'] = main_materials_count
                category_data['materials_count'] = materials_count
                category_data['total_count'] = main_materials_count + materials_count
                hierarchy.append(category_data)

            return hierarchy

        except Exception as e:
            raise e

    # ========== HELPER METHODS ==========

    def _validate_category_data(self, category_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate category creation data"""
        errors = []

        # Required fields
        required_fields = ['name_th', 'name_en']
        for field in required_fields:
            if not category_data.get(field):
                errors.append(f'{field} is required')

        # Validate numeric fields
        if 'display_order' in category_data:
            try:
                int(category_data['display_order'])
            except (ValueError, TypeError):
                errors.append('display_order must be a valid integer')

        # Validate color format
        if 'color' in category_data:
            color = category_data['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        # Check for duplicate names
        if category_data.get('name_en') or category_data.get('name_th'):
            existing = self.db.query(MaterialCategory).filter(
                MaterialCategory.is_active == True,
                or_(
                    MaterialCategory.name_en == category_data.get('name_en'),
                    MaterialCategory.name_th == category_data.get('name_th')
                )
            ).first()

            if existing:
                errors.append('Category with this name already exists')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_category_updates(self, category: MaterialCategory, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate category updates"""
        errors = []

        # Check for duplicate names if names are being updated
        if 'name_en' in updates or 'name_th' in updates:
            name_en = updates.get('name_en', category.name_en)
            name_th = updates.get('name_th', category.name_th)

            existing = self.db.query(MaterialCategory).filter(
                MaterialCategory.id != category.id,
                MaterialCategory.is_active == True,
                or_(
                    MaterialCategory.name_en == name_en,
                    MaterialCategory.name_th == name_th
                )
            ).first()

            if existing:
                errors.append('Category with this name already exists')

        # Validate numeric fields
        if 'display_order' in updates:
            try:
                int(updates['display_order'])
            except (ValueError, TypeError):
                errors.append('display_order must be a valid integer')

        # Validate color format
        if 'color' in updates:
            color = updates['color']
            if not (color.startswith('#') and len(color) == 7):
                errors.append('Color must be a valid hex color code (e.g., #FF0000)')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _apply_category_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to category query"""

        if 'search' in filters and filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    MaterialCategory.name_en.ilike(search_term),
                    MaterialCategory.name_th.ilike(search_term),
                    MaterialCategory.description.ilike(search_term)
                )
            )

        if 'color' in filters and filters['color']:
            query = query.filter(MaterialCategory.color == filters['color'])

        return query

    def _serialize_category(self, category: MaterialCategory) -> Dict[str, Any]:
        """Serialize category for API response"""
        return {
            'id': category.id,
            'is_active': category.is_active,
            'created_date': category.created_date.isoformat() if category.created_date else None,
            'updated_date': category.updated_date.isoformat() if category.updated_date else None,
            'deleted_date': category.deleted_date.isoformat() if category.deleted_date else None,

            'name_th': category.name_th,
            'name_en': category.name_en,
            'code': category.code,
            'description': category.description,
            'color': category.color
        }