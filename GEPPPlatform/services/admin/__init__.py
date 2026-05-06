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

    current_user = commonParams.get('current_user') or {}
    admin_handler = AdminHandlers(db_session, current_user=current_user)

    # Remove /api/admin prefix from path for internal routing
    internal_path = path.replace('/api/admin', '')

    # Extract ID from path patterns like /organizations/123 or /subscription-plans/123/permissions/456
    path_parts = [p for p in internal_path.strip('/').split('/') if p]

    if method == "POST":
        if internal_path == "/login":
            return admin_handler.admin_login(data)

        # IoT devices: POST /admin/iot-devices/snapshot-aggregate
        # — manually trigger the 5-min health snapshot worker. Idempotent.
        if (
            len(path_parts) == 2
            and path_parts[0] == 'iot-devices'
            and path_parts[1] == 'snapshot-aggregate'
        ):
            return admin_handler.admin_service.aggregate_health_snapshot()

        # IoT hardwares: POST /admin/iot-hardwares/{id}/{pair|unpair}
        if (
            len(path_parts) == 3
            and path_parts[0] == 'iot-hardwares'
            and path_parts[2] in ('pair', 'unpair')
        ):
            try:
                hardware_id = int(path_parts[1])
            except ValueError:
                raise NotFoundException(f'POST endpoint not found: {internal_path}')
            current_user = commonParams.get('current_user', {})
            if path_parts[2] == 'pair':
                return admin_handler.admin_service.pair_iot_hardware(
                    hardware_id, data, current_user=current_user
                )
            return admin_handler.admin_service.unpair_iot_hardware(
                hardware_id, current_user=current_user
            )

        # IoT devices: POST /admin/iot-devices/{id}/{commands|tags|maintenance}
        if (
            len(path_parts) == 3
            and path_parts[0] == 'iot-devices'
            and path_parts[2] in ('commands', 'tags', 'maintenance')
        ):
            try:
                device_id = int(path_parts[1])
            except ValueError:
                raise NotFoundException(f'POST endpoint not found: {internal_path}')
            sub = path_parts[2]
            if sub == 'commands':
                return admin_handler.admin_service.issue_device_command(
                    device_id, data, current_user=commonParams.get('current_user', {})
                )
            if sub == 'tags':
                return admin_handler.admin_service.update_device_tags(
                    device_id, data
                )
            if sub == 'maintenance':
                return admin_handler.admin_service.update_device_maintenance(
                    device_id, data
                )

        # CRM sub-paths without id: /crm-segments/preview, /crm-templates/render-preview, /crm-templates/generate-ai
        if len(path_parts) == 2 and path_parts[0].startswith('crm-') and \
           path_parts[1] in ('preview', 'render-preview', 'generate-ai'):
            from .crm import handle_crm_admin_subroute
            return handle_crm_admin_subroute(
                resource=path_parts[0], resource_id=None, sub_path=path_parts[1],
                method=method, db_session=db_session, data=data,
                query_params=commonParams.get('query_params', {}),
                current_user=commonParams.get('current_user', {}),
            )

        if len(path_parts) == 1:
            # POST /admin/{resource}
            resource = path_parts[0]
            return admin_handler.create_resource(resource, data)

        # CRM sub-paths with id: /crm-campaigns/{id}/{start|pause|resume|archive|test}
        #                        /crm-segments/{id}/{evaluate|clone}
        if len(path_parts) == 3 and path_parts[0].startswith('crm-'):
            from .crm import handle_crm_admin_subroute
            return handle_crm_admin_subroute(
                resource=path_parts[0], resource_id=int(path_parts[1]), sub_path=path_parts[2],
                method=method, db_session=db_session, data=data,
                query_params=commonParams.get('query_params', {}),
                current_user=commonParams.get('current_user', {}),
            )

        if len(path_parts) == 4 and path_parts[2] == "permissions" and path_parts[3] == "batch":
            # POST /admin/subscription-plans/{id}/permissions/batch
            resource_id = int(path_parts[1])
            return admin_handler.batch_permissions(resource_id, data)
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

        # IoT hardwares: GET /admin/iot-hardwares (list)
        if len(path_parts) == 1 and path_parts[0] == 'iot-hardwares':
            return admin_handler.admin_service.list_iot_hardwares(query_params)

        # IoT devices: realtime / by-organization / tags / recent-activity
        # (no numeric id)
        if len(path_parts) == 2 and path_parts[0] == 'iot-devices':
            sub = path_parts[1]
            if sub == 'realtime':
                return admin_handler.admin_service.list_realtime(
                    query_params, headers=commonParams.get('headers', {}),
                )
            if sub == 'by-organization':
                return admin_handler.admin_service.list_by_organization()
            if sub == 'tags':
                return admin_handler.admin_service.list_device_tags()
            if sub == 'recent-activity':
                return admin_handler.admin_service.list_recent_activity(
                    query_params
                )
            if sub == 'online-history':
                return admin_handler.admin_service.list_online_history(
                    query_params
                )

        # IoT devices: GET /admin/iot-devices/{id}/{status|events|commands}
        if len(path_parts) == 3 and path_parts[0] == 'iot-devices':
            try:
                device_id = int(path_parts[1])
            except ValueError:
                raise NotFoundException(f"GET endpoint not found: {internal_path}")
            sub = path_parts[2]
            if sub == 'status':
                return admin_handler.admin_service.get_device_status(device_id)
            if sub == 'events':
                return admin_handler.admin_service.list_device_events(device_id, query_params)
            if sub == 'commands':
                return admin_handler.admin_service.list_device_commands(device_id, query_params)
            if sub == 'health-history':
                return admin_handler.admin_service.list_device_health_history(
                    device_id, query_params
                )
            raise NotFoundException(f"GET endpoint not found: {internal_path}")

        # GET /admin/crm-deliveries.csv — Sprint 4 CSV export (special path with dot extension)
        if len(path_parts) == 1 and path_parts[0] == 'crm-deliveries.csv':
            from .crm.crm_handlers import export_crm_deliveries_csv
            csv_body = export_crm_deliveries_csv(db_session, query_params)
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'text/csv',
                    'Content-Disposition': 'attachment; filename="deliveries.csv"',
                },
                'body': csv_body,
            }

        # GET /admin/crm-health  — CRM system observability endpoint
        if len(path_parts) == 1 and path_parts[0] == 'crm-health':
            from .crm.crm_health import get_crm_health
            return get_crm_health(db_session)

        # CRM analytics sub-paths (no numeric id): /crm-analytics/overview, /crm-analytics/timeseries, /crm-analytics/funnel
        if len(path_parts) >= 2 and path_parts[0] == 'crm-analytics':
            from .crm import handle_crm_admin_subroute
            sub_path = '/'.join(path_parts[1:])
            return handle_crm_admin_subroute(
                resource='crm-analytics', resource_id=None, sub_path=sub_path,
                method=method, db_session=db_session, data={},
                query_params=query_params, current_user=commonParams.get('current_user', {}),
            )

        if len(path_parts) == 1:
            # GET /admin/{resource}
            resource = path_parts[0]
            return admin_handler.list_resource(resource, query_params)
        elif len(path_parts) == 2:
            # GET /admin/{resource}/{id} — except 'fields' which is a crm sub-path
            resource = path_parts[0]
            if resource.startswith('crm-') and path_parts[1] in ('fields',):
                from .crm import handle_crm_admin_subroute
                return handle_crm_admin_subroute(
                    resource=resource, resource_id=None, sub_path=path_parts[1],
                    method=method, db_session=db_session, data={},
                    query_params=query_params, current_user=commonParams.get('current_user', {}),
                )
            resource_id = int(path_parts[1])
            return admin_handler.get_resource(resource, resource_id)
        elif len(path_parts) == 3:
            resource = path_parts[0]
            # CRM sub-paths: /crm-{segments|templates|campaigns}/{id}/{action}
            if resource.startswith('crm-'):
                from .crm import handle_crm_admin_subroute
                return handle_crm_admin_subroute(
                    resource=resource, resource_id=int(path_parts[1]), sub_path=path_parts[2],
                    method=method, db_session=db_session, data={},
                    query_params=query_params, current_user=commonParams.get('current_user', {}),
                )
            # GET /admin/organizations/{id}/transactions-export — XLSX export
            if resource == 'organizations' and path_parts[2] == 'transactions-export':
                from .transaction_export_service import AdminTransactionExportService
                from .db_target_resolver import session_for_target
                target = (query_params.get('dbTarget') or 'local')
                try:
                    # Mint a session against the requested DB if needed;
                    # the request's normal `db_session` is used otherwise.
                    target_session, owns_session = session_for_target(target, db_session)
                except PermissionError as e:
                    raise BadRequestException(str(e))
                try:
                    return AdminTransactionExportService(target_session).export(
                        int(path_parts[1]), query_params
                    )
                finally:
                    if owns_session:
                        target_session.close()
            # GET /admin/organizations/{id}/users or /organizations/{id}/locations
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
