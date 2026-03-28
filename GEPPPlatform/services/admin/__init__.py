"""
Admin module for handling backoffice administration routes
"""

from .admin_handlers import AdminHandlers
from ...exceptions import (
    APIException,
    NotFoundException,
    BadRequestException,
)


def handle_admin_routes(path: str, data: dict, **commonParams):
    """
    Route handler for all /api/admin/* endpoints
    """
    method = commonParams["method"]
    db_session = commonParams.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    admin_handler = AdminHandlers(db_session)

    # Remove /api/admin prefix from path for internal routing
    internal_path = path.replace('/api/admin', '')

    # Extract ID from path patterns like /organizations/123 or /subscription-plans/123/permissions/456
    path_parts = [p for p in internal_path.strip('/').split('/') if p]

    if method == "POST":
        if internal_path == "/login":
            return admin_handler.admin_login(data)
        elif len(path_parts) == 1:
            # POST /admin/{resource}
            resource = path_parts[0]
            return admin_handler.create_resource(resource, data)
        elif len(path_parts) == 3 and path_parts[2] == "permissions":
            # POST /admin/subscription-plans/{id}/permissions
            resource = path_parts[0]
            resource_id = int(path_parts[1])
            return admin_handler.assign_permissions(resource, resource_id, data)
        else:
            raise NotFoundException(f"POST endpoint not found: {internal_path}")

    elif method == "GET":
        query_params = commonParams.get('query_params', {})
        if len(path_parts) == 2 and path_parts[1] == 'stats':
            # GET /admin/{resource}/stats (e.g., /admin/iot-devices/stats)
            resource = path_parts[0]
            if resource == 'iot-devices':
                return admin_handler.admin_service.get_iot_device_stats(query_params)
            raise NotFoundException(f"Stats not available for {resource}")
        if len(path_parts) == 1:
            # GET /admin/{resource}
            resource = path_parts[0]
            return admin_handler.list_resource(resource, query_params)
        elif len(path_parts) == 2:
            # GET /admin/{resource}/{id}
            resource = path_parts[0]
            resource_id = int(path_parts[1])
            return admin_handler.get_resource(resource, resource_id)
        elif len(path_parts) == 3:
            # GET /admin/organizations/{id}/users or /organizations/{id}/locations
            resource = path_parts[0]
            resource_id = int(path_parts[1])
            sub_resource = path_parts[2]
            return admin_handler.list_sub_resource(resource, resource_id, sub_resource, query_params)
        else:
            raise NotFoundException(f"GET endpoint not found: {internal_path}")

    elif method == "PUT":
        if len(path_parts) == 2:
            # PUT /admin/{resource}/{id}
            resource = path_parts[0]
            resource_id = int(path_parts[1])
            return admin_handler.update_resource(resource, resource_id, data)
        else:
            raise NotFoundException(f"PUT endpoint not found: {internal_path}")

    elif method == "DELETE":
        if len(path_parts) == 2:
            # DELETE /admin/{resource}/{id}
            resource = path_parts[0]
            resource_id = int(path_parts[1])
            return admin_handler.delete_resource(resource, resource_id)
        elif len(path_parts) == 4 and path_parts[2] == "permissions":
            # DELETE /admin/subscription-plans/{id}/permissions/{perm_id}
            resource_id = int(path_parts[1])
            perm_id = int(path_parts[3])
            return admin_handler.remove_permission(resource_id, perm_id)
        else:
            raise NotFoundException(f"DELETE endpoint not found: {internal_path}")

    else:
        raise BadRequestException(f"Method {method} not supported")
