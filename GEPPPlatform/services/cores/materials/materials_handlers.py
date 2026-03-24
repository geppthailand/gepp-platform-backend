"""
Materials management HTTP handlers
Handles all /api/materials/* routes
"""

import json
from typing import Dict, Any, Optional

from .materials_service import MaterialsService
from .main_materials_service import MainMaterialsService
from .tags_service import TagsService
from .tag_groups_service import TagGroupsService
from .material_categories_service import MaterialCategoriesService
from ....exceptions import APIException, ValidationException, NotFoundException


def handle_materials_routes(event: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all materials-related endpoints

    Routes:
    - /api/materials/* - Materials CRUD
    - /api/materials/main-materials/* - Main materials CRUD
    - /api/materials/tags/* - Tags CRUD
    - /api/materials/tag-groups/* - Tag groups CRUD
    - /api/materials/categories/* - Categories CRUD
    """

    db_session = common_params.get('db_session')
    method = common_params.get('method', 'GET')
    query_params = common_params.get('query_params', {})
    path_params = common_params.get('path_params', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    data = event.get('body', {}) if isinstance(event.get('body'), dict) else {}

    # Parse numeric parameters
    def parse_int(value: Any, default: int = None) -> Optional[int]:
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def parse_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return default

    try:
        # Initialize services
        materials_service = MaterialsService(db_session)
        main_materials_service = MainMaterialsService(db_session)
        tags_service = TagsService(db_session)
        tag_groups_service = TagGroupsService(db_session)
        categories_service = MaterialCategoriesService(db_session)

        # Route to specific handlers
        if '/api/materials/categories' in path:
            return handle_material_categories_routes(
                categories_service, path, method, query_params, path_params, data, current_user
            )

        elif '/api/materials/location-materials' in path:
            if method == 'GET':
                return handle_get_location_materials(db_session, current_user)
            raise APIException("Method not allowed", status_code=405, error_code="METHOD_NOT_ALLOWED")

        elif '/api/materials/main-materials' in path:
            return handle_main_materials_routes(
                main_materials_service, path, method, query_params, path_params, data, current_user
            )

        elif '/api/materials/tag-groups' in path:
            return handle_tag_groups_routes(
                tag_groups_service, path, method, query_params, path_params, data, current_user
            )

        elif '/api/materials/tags' in path:
            return handle_tags_routes(
                tags_service, path, method, query_params, path_params, data, current_user
            )

        elif '/api/materials' in path:
            return handle_materials_routes_main(
                materials_service, path, method, query_params, path_params, data, current_user
            )

        else:
            raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")

    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(f"Internal server error: {str(e)}", status_code=500, error_code="INTERNAL_ERROR")


def handle_materials_routes_main(service: MaterialsService, path: str, method: str,
                                query_params: Dict, path_params: Dict, data: Dict,
                                current_user: Dict) -> Dict[str, Any]:
    """Handle /api/materials routes"""

    # Parse common parameters
    page = int(query_params.get('page', 1))
    page_size = min(int(query_params.get('page_size', 20)), 10000)
    sort_by = query_params.get('sort_by', 'created_date')
    sort_order = query_params.get('sort_order', 'desc')
    include_relations = query_params.get('include_relations', '').lower() == 'true'

    if method == 'GET':
        if path == '/api/materials':
            # List materials with filters
            filters = {}
            if query_params.get('search'):
                filters['search'] = query_params['search']
            if query_params.get('category_id'):
                filters['category_id'] = int(query_params['category_id'])
            if query_params.get('main_material_id'):
                filters['main_material_id'] = int(query_params['main_material_id'])
            # base_material_id removed - using main_material_id only
            if query_params.get('has_tags'):
                filters['has_tags'] = query_params['has_tags'].lower() == 'true'

            # Get user organization ID
            user_organization_id = current_user.get('organization_id')
            return service.get_materials(filters, page, page_size, sort_by, sort_order, user_organization_id)

        elif path_params.get('id'):
            # Get specific material
            material_id = int(path_params['id'])
            user_organization_id = current_user.get('organization_id')
            result = service.get_material_by_id(material_id, include_relations, user_organization_id)
            if not result:
                raise NotFoundException('Material not found')
            return result

    elif method == 'POST':
        if path == '/api/materials':
            # Create material
            return service.create_material(data)

    elif method == 'PUT':
        if path_params.get('id'):
            # Update material
            material_id = int(path_params['id'])
            return service.update_material(material_id, data)

    elif method == 'DELETE':
        if path_params.get('id'):
            # Delete material
            material_id = int(path_params['id'])
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return service.delete_material(material_id, soft_delete)

    raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")


def handle_main_materials_routes(service: MainMaterialsService, path: str, method: str,
                               query_params: Dict, path_params: Dict, data: Dict,
                               current_user: Dict) -> Dict[str, Any]:
    """Handle /api/materials/main-materials routes"""

    page = int(query_params.get('page', 1))
    page_size = min(int(query_params.get('page_size', 20)), 100)
    sort_by = query_params.get('sort_by', 'display_order')
    sort_order = query_params.get('sort_order', 'asc')
    include_relations = query_params.get('include_relations', '').lower() == 'true'

    if method == 'GET':
        if path == '/api/materials/main-materials':
            # List main materials
            filters = {}
            if query_params.get('search'):
                filters['search'] = query_params['search']
            if query_params.get('category_id'):
                filters['category_id'] = int(query_params['category_id'])

            return service.get_main_materials(filters, page, page_size, sort_by, sort_order)

        elif path_params.get('id'):
            # Get specific main material
            main_material_id = int(path_params['id'])
            result = service.get_main_material_by_id(main_material_id, include_relations)
            if not result:
                raise NotFoundException('Main material not found')
            return result

    elif method == 'POST':
        if path == '/api/materials/main-materials':
            # Create main material
            return service.create_main_material(data)

        elif path == '/api/materials/main-materials/bulk-order':
            # Bulk update display order
            return service.bulk_update_display_order(data.get('updates', []))

    elif method == 'PUT':
        if path_params.get('id'):
            # Update main material
            main_material_id = int(path_params['id'])
            return service.update_main_material(main_material_id, data)

    elif method == 'DELETE':
        if path_params.get('id'):
            # Delete main material
            main_material_id = int(path_params['id'])
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return service.delete_main_material(main_material_id, soft_delete)

    raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")


def handle_tags_routes(service: TagsService, path: str, method: str,
                      query_params: Dict, path_params: Dict, data: Dict,
                      current_user: Dict) -> Dict[str, Any]:
    """Handle /api/materials/tags routes"""

    organization_id = current_user.get('organization_id')
    page = int(query_params.get('page', 1))
    page_size = min(int(query_params.get('page_size', 50)), 100)
    sort_by = query_params.get('sort_by', 'name')
    sort_order = query_params.get('sort_order', 'asc')
    include_relations = query_params.get('include_relations', '').lower() == 'true'

    if method == 'GET':
        if path == '/api/materials/tags':
            # List tags
            filters = {}
            if query_params.get('search'):
                filters['search'] = query_params['search']
            if query_params.get('is_global') is not None:
                filters['is_global'] = query_params['is_global'].lower() == 'true'
            if query_params.get('organization_id'):
                filters['organization_id'] = int(query_params['organization_id'])
            elif organization_id:
                filters['organization_id'] = organization_id
                filters['include_global'] = query_params.get('include_global', 'true').lower() == 'true'

            return service.get_tags(filters, page, page_size, sort_by, sort_order)

        elif path == '/api/materials/tags/available':
            # Get available tags for organization
            if not organization_id:
                raise ValidationException('Organization ID is required')
            tags = service.get_available_tags_for_organization(organization_id)
            return {'data': tags}

        elif path == '/api/materials/tags/global':
            # Get global tags only
            tags = service.get_global_tags()
            return {'data': tags}

        elif path_params.get('id'):
            # Get specific tag
            tag_id = int(path_params['id'])
            result = service.get_tag_by_id(tag_id, include_relations)
            if not result:
                raise NotFoundException('Tag not found')
            return result

    elif method == 'POST':
        if path == '/api/materials/tags':
            # Create tag
            return service.create_tag(data)

        elif path == '/api/materials/tags/bulk':
            # Bulk create tags
            return service.bulk_create_tags(data.get('tags', []))

    elif method == 'PUT':
        if path_params.get('id'):
            # Update tag
            tag_id = int(path_params['id'])
            return service.update_tag(tag_id, data)

    elif method == 'DELETE':
        if path_params.get('id'):
            # Delete tag
            tag_id = int(path_params['id'])
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return service.delete_tag(tag_id, soft_delete)

    raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")


def handle_tag_groups_routes(service: TagGroupsService, path: str, method: str,
                           query_params: Dict, path_params: Dict, data: Dict,
                           current_user: Dict) -> Dict[str, Any]:
    """Handle /api/materials/tag-groups routes"""

    organization_id = current_user.get('organization_id')
    page = int(query_params.get('page', 1))
    page_size = min(int(query_params.get('page_size', 50)), 100)
    sort_by = query_params.get('sort_by', 'name')
    sort_order = query_params.get('sort_order', 'asc')
    include_relations = query_params.get('include_relations', '').lower() == 'true'

    if method == 'GET':
        if path == '/api/materials/tag-groups':
            # List tag groups
            filters = {}
            if query_params.get('search'):
                filters['search'] = query_params['search']
            if query_params.get('is_global') is not None:
                filters['is_global'] = query_params['is_global'].lower() == 'true'
            if query_params.get('organization_id'):
                filters['organization_id'] = int(query_params['organization_id'])
            elif organization_id:
                filters['organization_id'] = organization_id
                filters['include_global'] = query_params.get('include_global', 'true').lower() == 'true'

            return service.get_tag_groups(filters, page, page_size, sort_by, sort_order)

        elif path == '/api/materials/tag-groups/with-tags':
            # Get tag groups with their tags
            include_global = query_params.get('include_global', 'true').lower() == 'true'
            tag_groups = service.get_tag_groups_with_tags(organization_id, include_global)
            return {'data': tag_groups}

        elif path_params.get('id'):
            # Get specific tag group
            tag_group_id = int(path_params['id'])
            result = service.get_tag_group_by_id(tag_group_id, include_relations)
            if not result:
                raise NotFoundException('Tag group not found')
            return result

    elif method == 'POST':
        if path == '/api/materials/tag-groups':
            # Create tag group
            return service.create_tag_group(data)

        elif path_params.get('id') and '/tags' in path:
            # Add tags to group
            tag_group_id = int(path_params['id'])
            tag_ids = data.get('tag_ids', [])
            return service.add_tags_to_group(tag_group_id, tag_ids)

    elif method == 'PUT':
        if path_params.get('id'):
            # Update tag group
            tag_group_id = int(path_params['id'])
            return service.update_tag_group(tag_group_id, data)

    elif method == 'DELETE':
        if path_params.get('id') and '/tags' in path:
            # Remove tags from group
            tag_group_id = int(path_params['id'])
            tag_ids = data.get('tag_ids', [])
            return service.remove_tags_from_group(tag_group_id, tag_ids)

        elif path_params.get('id'):
            # Delete tag group
            tag_group_id = int(path_params['id'])
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return service.delete_tag_group(tag_group_id, soft_delete)

    raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")


def handle_material_categories_routes(service: MaterialCategoriesService, path: str, method: str,
                                    query_params: Dict, path_params: Dict, data: Dict,
                                    current_user: Dict) -> Dict[str, Any]:
    """Handle /api/materials/categories routes"""

    page = int(query_params.get('page', 1))
    page_size = min(int(query_params.get('page_size', 20)), 100)
    sort_by = query_params.get('sort_by', 'display_order')
    sort_order = query_params.get('sort_order', 'asc')
    include_relations = query_params.get('include_relations', '').lower() == 'true'

    if method == 'GET':
        if path == '/api/materials/categories':
            # List categories
            filters = {}
            if query_params.get('search'):
                filters['search'] = query_params['search']

            return service.get_material_categories(filters, page, page_size, sort_by, sort_order)

        elif path == '/api/materials/categories/hierarchy':
            # Get category hierarchy with counts
            categories = service.get_category_hierarchy()
            return {'data': categories}

        elif path == '/api/materials/categories/with-counts':
            # Get categories with main materials count
            categories = service.get_categories_with_main_materials_count()
            return {'data': categories}

        elif path_params.get('id'):
            # Get specific category
            category_id = int(path_params['id'])
            result = service.get_material_category_by_id(category_id, include_relations)
            if not result:
                raise NotFoundException('Category not found')
            return result

    elif method == 'POST':
        if path == '/api/materials/categories':
            # Create category
            return service.create_material_category(data)

        elif path == '/api/materials/categories/bulk-order':
            # Bulk update display order
            return service.bulk_update_display_order(data.get('updates', []))

    elif method == 'PUT':
        if path_params.get('id'):
            # Update category
            category_id = int(path_params['id'])
            return service.update_material_category(category_id, data)

    elif method == 'DELETE':
        if path_params.get('id'):
            # Delete category
            category_id = int(path_params['id'])
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return service.delete_material_category(category_id, soft_delete)

    raise APIException("Route not found", status_code=404, error_code="ROUTE_NOT_FOUND")


def handle_get_location_materials(db_session, current_user: Dict) -> Dict[str, Any]:
    """Handle GET /api/materials/location-materials
    Returns all materials available to the current user based on:
    1. Locations where the user is a member
    2. All descendant locations of those locations (via org tree)
    3. Union of material IDs stored in those locations' `materials` JSONB column
    """
    from GEPPPlatform.models.users.user_location import UserLocation
    from GEPPPlatform.models.cores.references import Material
    from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
    from sqlalchemy import and_, or_

    user_id = current_user.get('user_id')
    organization_id = current_user.get('organization_id')

    if not user_id or not organization_id:
        raise ValidationException('User context is required')

    uid_int = int(user_id)
    uid_str = str(user_id)

    # Step 1: Find all locations in the org that have the user as a member
    all_locations = db_session.query(UserLocation).filter(
        and_(
            UserLocation.organization_id == organization_id,
            UserLocation.is_location == True,
            UserLocation.is_active == True,
            UserLocation.deleted_date.is_(None)
        )
    ).all()

    def is_member_of(members_list):
        if not members_list:
            return False
        for m in members_list:
            if isinstance(m, dict):
                mid = m.get('user_id') or m.get('id')
                if mid is not None and (mid == uid_int or str(mid) == uid_str):
                    return True
            else:
                if m == uid_int or str(m) == uid_str:
                    return True
        return False

    member_loc_ids = {loc.id for loc in all_locations if is_member_of(loc.members)}

    # Step 2: Walk the org tree to collect member locations + all their descendants
    org_setup = db_session.query(OrganizationSetup).filter(
        and_(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.is_active == True,
            OrganizationSetup.deleted_date.is_(None)
        )
    ).order_by(OrganizationSetup.created_date.desc()).first()

    relevant_ids = set(member_loc_ids)

    if org_setup and org_setup.root_nodes and member_loc_ids:
        root_nodes = org_setup.root_nodes
        if not isinstance(root_nodes, list):
            root_nodes = [root_nodes] if root_nodes else []

        def collect_descendants(nodes, ids_set):
            for node in nodes:
                nid = int(node.get('nodeId', 0))
                ids_set.add(nid)
                children = node.get('children', [])
                if children:
                    collect_descendants(children, ids_set)

        def walk_tree(nodes):
            for node in nodes:
                nid = int(node.get('nodeId', 0))
                children = node.get('children', [])
                if nid in member_loc_ids and children:
                    collect_descendants(children, relevant_ids)
                elif children:
                    walk_tree(children)

        walk_tree(root_nodes)

    # Step 3: Collect all material IDs from relevant locations
    loc_map = {loc.id: loc for loc in all_locations}
    material_ids = set()
    for loc_id in relevant_ids:
        loc = loc_map.get(loc_id)
        if loc and loc.materials and isinstance(loc.materials, list):
            for mid in loc.materials:
                try:
                    material_ids.add(int(mid))
                except (ValueError, TypeError):
                    pass

    # Step 4: Fetch materials — if no IDs configured, return all org-accessible materials
    query = db_session.query(Material).filter(
        and_(
            Material.is_active == True,
            Material.deleted_date.is_(None),
            or_(
                Material.is_global == True,
                Material.organization_id == organization_id
            )
        )
    )

    if material_ids:
        query = query.filter(Material.id.in_(material_ids))

    total_count = query.count()
    materials = query.order_by(Material.name_th).all()

    service = MaterialsService(db_session)

    # Fetch material images
    images_map = service._fetch_material_images([m.id for m in materials])

    return {
        'data': [{**service._serialize_material(mat), 'images': images_map.get(mat.id, [])} for mat in materials],
        'pagination': {
            'page': 1,
            'page_size': total_count,
            'total': total_count,
            'pages': 1,
            'has_next': False,
            'has_prev': False,
        },
    }