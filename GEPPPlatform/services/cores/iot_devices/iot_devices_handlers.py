"""
IoT Devices HTTP handlers
Handles all /api/iot-devices/* routes
"""

from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import joinedload

from GEPPPlatform.services.cores.transactions.transaction_handlers import handle_create_transaction
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.users.user_service import UserService
from GEPPPlatform.services.cores.users.user_handlers import handle_get_location_allowed_materials
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from GEPPPlatform.models.cores.references import Material
from GEPPPlatform.models.cores.iot_devices import IoTDevice

from ....exceptions import APIException, UnauthorizedException, ValidationException, NotFoundException

import logging as _iot_log

_iot_logger = _iot_log.getLogger(__name__)


def _emit_iot_event(db_session, event_type: str, organization_id=None, user_id=None, properties: dict = None):
    """Fire-and-forget CRM event emission for IoT events.  Never raises."""
    try:
        from GEPPPlatform.services.admin.crm.crm_service import emit_event
        emit_event(
            db_session,
            event_type=event_type,
            event_category='iot',
            organization_id=organization_id,
            user_location_id=user_id,
            properties=properties or {},
            event_source='device',
            commit=False,
        )
    except Exception as _exc:
        _iot_logger.warning("CRM emit_event non-fatal (iot): %s", _exc)


def handle_get_locations_by_membership(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any], db_session) -> Dict[str, Any]:
    """Handle POST /api/iot-devices/my-memberships - Get locations where current user is in members list (default role=dataInput)"""
    try:
        if not current_user or not current_user.get('user_id'):
            raise UnauthorizedException('Unauthorized')

        role = (query_params.get('role') or 'dataInput').strip()
        # Normalize common role variants used by clients/DB
        # DB memberships commonly store camelCase role (e.g. "dataInput")
        if role in ('data_input', 'data-input', 'datainput'):
            role = 'dataInput'
        organization_id = current_user.get('organization_id') if current_user else None

        if not organization_id:
            raise NotFoundException('User is not part of any organization')

        member_locations = user_service.get_locations_by_member(
            member_user_id=current_user['user_id'],
            role=role,
            organization_id=organization_id
        )

        member_origin_ids: List[int] = [
            int(loc.get('origin_id'))
            for loc in member_locations
            if loc.get('origin_id') is not None
        ]

        # Expand to include all descendants of member locations (based on org setup tree)
        def _expand_descendants_from_setup(
            setup_root_nodes,
            seed_ids: Set[int],
        ) -> Set[int]:
            if not setup_root_nodes or not seed_ids:
                return set(seed_ids)

            roots = setup_root_nodes
            if isinstance(roots, dict):
                roots = [roots]
            if not isinstance(roots, list):
                return set(seed_ids)

            expanded: Set[int] = set(seed_ids)

            def to_int(v) -> Optional[int]:
                if v is None:
                    return None
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
                return None

            def collect_all(node: Dict[str, Any]) -> None:
                nid = to_int(node.get('nodeId'))
                if nid is not None:
                    expanded.add(nid)
                children = node.get('children') or []
                if isinstance(children, list):
                    for ch in children:
                        if isinstance(ch, dict):
                            collect_all(ch)

            def walk(nodes: List[Dict[str, Any]]) -> None:
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    nid = to_int(node.get('nodeId'))
                    children = node.get('children') or []
                    if nid is not None and nid in seed_ids:
                        collect_all(node)
                    else:
                        if isinstance(children, list) and children:
                            walk([ch for ch in children if isinstance(ch, dict)])

            walk([n for n in roots if isinstance(n, dict)])
            return expanded

        setup = (
            db_session.query(OrganizationSetup)
            .filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True,
                OrganizationSetup.deleted_date.is_(None),
            )
            .order_by(OrganizationSetup.created_date.desc())
            .first()
        )

        expanded_ids = _expand_descendants_from_setup(
            setup.root_nodes if setup else None,
            set(member_origin_ids),
        )

        # Keep original membership order first, then append remaining descendants
        ordered_ids: List[int] = []
        seen: Set[int] = set()
        for mid in member_origin_ids:
            if mid not in seen:
                ordered_ids.append(mid)
                seen.add(mid)
        for did in sorted(expanded_ids - seen):
            ordered_ids.append(did)
            seen.add(did)

        # Build location paths for all returned locations
        location_paths = user_service._build_location_paths(
            organization_id=organization_id,
            location_data=[{'id': loc_id} for loc_id in ordered_ids],
        )
        
        # Get ALL materials (active and not deleted, no organization filtering)
        # Use eager loading to fetch category and main_material relationships
        all_materials = db_session.query(Material).options(
            joinedload(Material.category),
            joinedload(Material.main_material)
        ).filter(
            Material.is_active == True,
            Material.deleted_date.is_(None)
        ).all()
        
        # Format materials in the same structure as location materials
        materials_list = []
        for material in all_materials:
            material_obj = {
                'material_id': material.id,
                'name_en': material.name_en or '',
                'name_th': material.name_th or '',
                'category_id': material.category_id or 0,
                'main_material_id': material.main_material_id or 0,
                'unit_name_th': material.unit_name_th or 'กิโลกรัม',
                'unit_name_en': material.unit_name_en or 'Kilogram',
                'unit_weight': float(material.unit_weight) if material.unit_weight is not None else 1.0,
            }
            
            # Add category as object
            if material.category:
                material_obj['category'] = {
                    'id': material.category.id,
                    'name_en': material.category.name_en or '',
                    'name_th': material.category.name_th or '',
                    'code': material.category.code or '',
                }
            else:
                material_obj['category'] = None

            # Add main_material as object
            if material.main_material:
                material_obj['main_material'] = {
                    'id': material.main_material.id,
                    'name_en': material.main_material.name_en or '',
                    'name_th': material.main_material.name_th or '',
                    'name_local': material.main_material.name_local or '',
                    'code': material.main_material.code or '',
                }
            else:
                material_obj['main_material'] = None
            
            materials_list.append(material_obj)
        
        # Load tags and tenants per location (id, name, members)
        origin_ids = ordered_ids
        origin_to_loc = {}
        tag_ids_all = set()
        tenant_ids_all = set()
        if origin_ids:
            locations_orm = db_session.query(UserLocation).filter(
                UserLocation.id.in_(origin_ids),
                UserLocation.deleted_date.is_(None)
            ).all()
            origin_to_loc = {loc.id: loc for loc in locations_orm}
            for loc in locations_orm:
                for tid in (loc.tags or []):
                    tag_ids_all.add(int(tid) if isinstance(tid, str) and tid.isdigit() else tid)
                for tid in (loc.tenants or []):
                    tenant_ids_all.add(int(tid) if isinstance(tid, str) and tid.isdigit() else tid)
        tag_ids_all = [x for x in tag_ids_all if x is not None]
        tenant_ids_all = [x for x in tenant_ids_all if x is not None]
        tag_by_id = {}
        tenant_by_id = {}
        if tag_ids_all:
            tags_orm = db_session.query(UserLocationTag).filter(
                UserLocationTag.id.in_(tag_ids_all),
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.is_active == True,
                UserLocationTag.deleted_date.is_(None)
            ).all()
            tag_by_id = {t.id: t for t in tags_orm}
        if tenant_ids_all:
            tenants_orm = db_session.query(UserTenant).filter(
                UserTenant.id.in_(tenant_ids_all),
                UserTenant.organization_id == organization_id,
                UserTenant.is_active == True,
                UserTenant.deleted_date.is_(None)
            ).all()
            tenant_by_id = {t.id: t for t in tenants_orm}
        # Build locations_list with tags and tenants (id, name, members)
        locations_list = []
        for origin_id in ordered_ids:
            loc_orm = origin_to_loc.get(origin_id)
            if not loc_orm:
                continue
            location_path = location_paths.get(origin_id) or ''
            tags_list = []
            tenants_list = []
            if loc_orm:
                for tid in (loc_orm.tags or []):
                    tid_int = int(tid) if isinstance(tid, str) and tid.isdigit() else tid
                    t = tag_by_id.get(tid_int)
                    if t:
                        tags_list.append({
                            'id': t.id,
                            'name': t.name or f'Tag {t.id}',
                            'members': t.members or [],
                            'start_date': t.start_date.isoformat() if t.start_date else None,
                            'end_date': t.end_date.isoformat() if t.end_date else None
                        })
                for tid in (loc_orm.tenants or []):
                    tid_int = int(tid) if isinstance(tid, str) and tid.isdigit() else tid
                    t = tenant_by_id.get(tid_int)
                    if t:
                        tenants_list.append({
                            'id': t.id,
                            'name': t.name or f'Tenant {t.id}',
                            'members': t.members or [],
                            'start_date': t.start_date.isoformat() if t.start_date else None,
                            'end_date': t.end_date.isoformat() if t.end_date else None
                        })
            locations_list.append({
                'origin_id': origin_id,
                'display_name': (loc_orm.display_name if loc_orm and loc_orm.display_name else ''),
                'path': location_path,
                'tags': tags_list,
                'tenants': tenants_list
            })
        
        return {
            'success': True,
            'data': {
                'locations': locations_list,
                'materials': materials_list
            }
        }

    except Exception as e:
        raise APIException(f'Error fetching member locations: {str(e)}')

# ========== MAIN ROUTE HANDLER ==========

def handle_iot_devices_routes(event: Dict[str, Any], data: Dict[str, Any], **common_params) -> Dict[str, Any]:
    """
    Route handler for all IoT devices-related endpoints
    """
    db_session = common_params.get('db_session')
    method = common_params.get('method', '')
    query_params = common_params.get('query_params', {})
    current_device = common_params.get('current_device', {})
    current_user = common_params.get('current_user', {})
    path = event.get('rawPath', '')
    if not current_device or not current_device.get('device_id'):
        raise UnauthorizedException('Unauthorized device')
    
    # Check organization match between device and user (if user is present)
    if current_user and current_user.get('user_id'):
        device_id = current_device.get('device_id')
        device = db_session.query(IoTDevice).filter_by(
            id=device_id,
            is_active=True
        ).first()
        
        if not device:
            raise NotFoundException('Device not found')
        
        user_organization_id = current_user.get('organization_id')
        device_organization_id = device.organization_id
        
        # Only check if both have organization IDs set
        if user_organization_id is not None and device_organization_id is not None:
            if user_organization_id != device_organization_id:
                raise UnauthorizedException('User organization does not match device organization')
    
    try:
        if method == '':
            raise APIException(
                f"Method is invalid",
                status_code=405,
                error_code="INVALID_METHOD"
            )

        if path == '/api/iot-devices/my-memberships':
            # Use UserService for membership-based location lookup
            user_service = UserService(db_session)
            return handle_get_locations_by_membership(user_service, query_params, current_user, db_session)
        if path == '/api/iot-devices/records':
            data = data.get('data')
            if not data:
                raise ValidationException('Data is required')
            transaction_service = TransactionService(db_session)
            current_user_id = current_user.get('user_id')
            current_user_organization_id = current_user.get('organization_id')
            result = handle_create_transaction(
                transaction_service,
                data,
                current_user_id,
                current_user_organization_id
            )
            # ── CRM: emit scale_reading_received ──
            _emit_iot_event(
                db_session,
                event_type='scale_reading_received',
                organization_id=current_user_organization_id,
                user_id=current_user_id,
                properties={
                    'device_id': current_device.get('device_id'),
                    'transaction_id': result.get('transaction_id') if isinstance(result, dict) else None,
                    'origin_id': data.get('origin_id') if isinstance(data, dict) else None,
                },
            )
            return result
        if path == '/api/iot-devices/qr-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login_iot_user(data, **common_params)
        if path == '/api/iot-devices/manual-login':
            auth_handler = AuthHandlers(db_session)
            return auth_handler.login(data, **common_params)
        if path == '/api/iot-devices/user-id-login':
            auth_handler = AuthHandlers(db_session)
            # Use user_id from body to login, return as normal manual login
            user_id = data.get('user_id')
            
            if not user_id:
                raise ValidationException('user_id is required')
            
            # Get user by user_id
            user = db_session.query(UserLocation).filter_by(
                id=user_id,
                is_active=True
            ).first()
            
            if not user:
                raise UnauthorizedException('Invalid user_id')
            
            # Generate JWT auth and refresh tokens
            tokens = auth_handler.generate_jwt_tokens(user.id, user.organization_id, user.email)
            
            return {
                'success': True,
                'auth_token': tokens['auth_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': 3600,  # 60 minutes in seconds
                'user': {
                    'id': user.id,
                    'email': user.email or '',
                    'displayName': user.display_name or '',
                    'organization_id': user.organization_id or 0
                }
            }
        if '/api/iot-devices/locations/' in path and path.endswith('/allowed-materials') and method == 'POST':
            # GET /api/iot-devices/locations/{location_id}/allowed-materials
            if not current_user or not current_user.get('user_id'):
                raise UnauthorizedException('User token is required')
            location_id = path.split('/locations/')[1].split('/')[0]
            organization_id = current_user.get('organization_id')
            if not organization_id:
                raise ValidationException('User is not associated with an organization')
            # Verify user is a member of the requested location (including descendants)
            user_service = UserService(db_session)
            member_locations = user_service.get_locations_by_member(
                member_user_id=current_user['user_id'],
                organization_id=organization_id
            )
            member_origin_ids: Set[int] = {
                int(loc.get('origin_id'))
                for loc in member_locations
                if loc.get('origin_id') is not None
            }
            # Expand to include descendants via org setup tree
            setup = (
                db_session.query(OrganizationSetup)
                .filter(
                    OrganizationSetup.organization_id == organization_id,
                    OrganizationSetup.is_active == True,
                    OrganizationSetup.deleted_date.is_(None),
                )
                .order_by(OrganizationSetup.created_date.desc())
                .first()
            )
            if setup and setup.root_nodes:
                roots = setup.root_nodes
                if isinstance(roots, dict):
                    roots = [roots]
                if isinstance(roots, list):
                    def _to_int(v) -> Optional[int]:
                        if v is None:
                            return None
                        if isinstance(v, int):
                            return v
                        if isinstance(v, str) and v.isdigit():
                            return int(v)
                        return None

                    def _collect_all(node: Dict[str, Any], ids: Set[int]) -> None:
                        nid = _to_int(node.get('nodeId'))
                        if nid is not None:
                            ids.add(nid)
                        for ch in (node.get('children') or []):
                            if isinstance(ch, dict):
                                _collect_all(ch, ids)

                    def _walk(nodes: List[Dict[str, Any]], seed: Set[int], out: Set[int]) -> None:
                        for node in nodes:
                            if not isinstance(node, dict):
                                continue
                            nid = _to_int(node.get('nodeId'))
                            children = node.get('children') or []
                            if nid is not None and nid in seed:
                                _collect_all(node, out)
                            elif isinstance(children, list) and children:
                                _walk([ch for ch in children if isinstance(ch, dict)], seed, out)

                    expanded: Set[int] = set(member_origin_ids)
                    _walk([n for n in roots if isinstance(n, dict)], member_origin_ids, expanded)
                    member_origin_ids = expanded

            if int(location_id) not in member_origin_ids:
                raise UnauthorizedException('User is not a member of this location')
            return handle_get_location_allowed_materials(db_session, location_id, organization_id)

        # Unknown route under /api/iot-devices
        raise NotFoundException('Endpoint not found')

    except ValidationException as e:
        raise APIException(str(e), status_code=400, error_code="VALIDATION_ERROR")
    except UnauthorizedException as e:
        raise APIException(str(e), status_code=401, error_code="UNAUTHORIZED")
    except NotFoundException as e:
        raise APIException(str(e), status_code=404, error_code="NOT_FOUND")
    except Exception as e:
        raise APIException(
            f"Internal server error: {str(e)}",
            status_code=500,
            error_code="INTERNAL_ERROR"
        )
