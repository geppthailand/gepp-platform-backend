"""
Audit Rules API Handlers
Handles HTTP requests for audit rules management
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .audit_rules_service import AuditRulesService
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_audit_rules_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for audit rules routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    path_params = params.get('path_params', {})
    query_params = params.get('query_params', {})
    headers = params.get('headers', {})

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    audit_service = AuditRulesService(db_session)

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')

    # Route to specific handlers
    if '/api/audit/rules/' in path and method == 'GET':
        # Get rule by ID: /api/audit/rules/{rule_id}
        rule_id = int(path.split('/rules/')[1].rstrip('/'))
        return handle_get_rule_by_id(audit_service, rule_id)

    elif '/api/audit/rules/' in path and method == 'PUT':
        # Update rule: /api/audit/rules/{rule_id}
        rule_id = int(path.split('/rules/')[1].rstrip('/'))
        return handle_update_rule(audit_service, rule_id, data, current_user_id, current_user_organization_id)

    elif '/api/audit/rules/' in path and method == 'DELETE':
        # Delete rule: /api/audit/rules/{rule_id}
        rule_id = int(path.split('/rules/')[1].rstrip('/'))
        return handle_delete_rule(audit_service, rule_id, current_user_id)

    elif '/api/audit/rules/active' == path and method == 'GET':
        # Get active rules
        return handle_get_active_rules(audit_service, query_params, current_user_organization_id)

    elif '/api/audit/rules/type/' in path and method == 'GET':
        # Get rules by type: /api/audit/rules/type/{rule_type}
        rule_type = path.split('/type/')[1].rstrip('/')
        return handle_get_rules_by_type(audit_service, rule_type)

    elif '/api/audit/rules/global' == path and method == 'GET':
        # Get global rules
        return handle_get_global_rules(audit_service)

    elif '/api/audit/rules/all' == path and method == 'GET':
        # Get all rules (debug endpoint)
        return handle_get_all_rules(audit_service)

    elif '/api/audit/rules' == path and method == 'GET':
        # List rules with filters
        return handle_list_rules(audit_service, query_params, current_user_organization_id)

    elif '/api/audit/rules' == path and method == 'POST':
        # Create new rule
        return handle_create_rule(audit_service, data, current_user_id, current_user_organization_id)

    else:
        raise NotFoundException(f'Route not found: {path} [{method}]')


def handle_list_rules(
    audit_service: AuditRulesService,
    query_params: Dict[str, Any],
    current_user_organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle listing audit rules with filtering
    """
    try:
        # Parse query parameters
        filters = {}

        # Rule type filter
        if query_params.get('rule_type'):
            filters['rule_type'] = query_params['rule_type']

        # Active status filter
        if query_params.get('is_active') is not None:
            filters['is_active'] = query_params['is_active'].lower() == 'true'

        # Global status filter
        if query_params.get('is_global') is not None:
            filters['is_global'] = query_params['is_global'].lower() == 'true'

        # Organization filter
        if query_params.get('organization_id'):
            filters['organization_id'] = int(query_params['organization_id'])
        elif current_user_organization_id:
            # If no organization specified, include user's organization rules
            filters['organization_id'] = current_user_organization_id

        # Search filter
        if query_params.get('search'):
            filters['search'] = query_params['search']

        # Pagination
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('size', 50))

        # Sorting
        sort_by = query_params.get('sort_by', 'created_date')
        sort_order = query_params.get('sort_order', 'desc')

        result = audit_service.get_rules_with_filters(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        return {
            'success': True,
            'data': result['data'],
            'meta': result['meta'],
            'aggregations': result.get('aggregations', {})
        }

    except ValueError as e:
        raise BadRequestException(f'Invalid query parameters: {str(e)}')
    except Exception as e:
        raise APIException(f'Failed to list audit rules: {str(e)}')


def handle_get_rule_by_id(audit_service: AuditRulesService, rule_id: int) -> Dict[str, Any]:
    """
    Handle getting audit rule by ID
    """
    try:
        result = audit_service.get_rule_by_id(rule_id)
        return {
            'success': True,
            'data': result['rule']
        }
    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to get audit rule: {str(e)}')


def handle_create_rule(
    audit_service: AuditRulesService,
    data: Dict[str, Any],
    current_user_id: Optional[int] = None,
    current_user_organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle creating new audit rule
    """
    try:
        # Set organization_id from current user if not provided in data
        if not data.get('organization_id') and current_user_organization_id:
            data['organization_id'] = current_user_organization_id

        result = audit_service.create_rule(data, current_user_id)
        return {
            'success': True,
            'data': result['rule'],
            'message': result['message']
        }
    except ValidationException:
        raise
    except Exception as e:
        raise APIException(f'Failed to create audit rule: {str(e)}')


def handle_update_rule(
    audit_service: AuditRulesService,
    rule_id: int,
    data: Dict[str, Any],
    current_user_id: Optional[int] = None,
    current_user_organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle updating audit rule
    """
    try:
        # Set organization_id from current user if not provided and rule is non-global
        if data.get('is_global') == False and not data.get('organization_id') and current_user_organization_id:
            data['organization_id'] = current_user_organization_id

        result = audit_service.update_rule(rule_id, data, current_user_id)
        return {
            'success': True,
            'data': result['rule'],
            'message': result['message']
        }
    except (NotFoundException, ValidationException):
        raise
    except Exception as e:
        raise APIException(f'Failed to update audit rule: {str(e)}')


def handle_delete_rule(
    audit_service: AuditRulesService,
    rule_id: int,
    current_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle deleting audit rule
    """
    try:
        result = audit_service.delete_rule(rule_id, current_user_id)
        return {
            'success': True,
            'message': result['message']
        }
    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to delete audit rule: {str(e)}')


def handle_get_active_rules(
    audit_service: AuditRulesService,
    query_params: Dict[str, Any],
    current_user_organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle getting active rules for current user's organization
    """
    try:
        # Use organization ID from query params or current user
        organization_id = None
        if query_params.get('organization_id'):
            organization_id = int(query_params['organization_id'])
        elif current_user_organization_id:
            organization_id = current_user_organization_id

        result = audit_service.get_active_rules(organization_id)
        return {
            'success': True,
            'data': result['data'],
            'meta': result.get('meta', {})
        }
    except Exception as e:
        raise APIException(f'Failed to get active audit rules: {str(e)}')


def handle_get_rules_by_type(audit_service: AuditRulesService, rule_type: str) -> Dict[str, Any]:
    """
    Handle getting rules by type
    """
    try:
        result = audit_service.get_rules_by_type(rule_type)
        return {
            'success': True,
            'data': result['data'],
            'meta': result.get('meta', {})
        }
    except ValidationException:
        raise
    except Exception as e:
        raise APIException(f'Failed to get rules by type: {str(e)}')


def handle_get_global_rules(audit_service: AuditRulesService) -> Dict[str, Any]:
    """
    Handle getting global rules
    """
    try:
        result = audit_service.get_global_rules()
        return {
            'success': True,
            'data': result['data'],
            'meta': result.get('meta', {})
        }
    except Exception as e:
        raise APIException(f'Failed to get global audit rules: {str(e)}')


def handle_get_all_rules(audit_service: AuditRulesService) -> Dict[str, Any]:
    """
    Handle getting all rules (debug endpoint)
    """
    try:
        result = audit_service.get_rules_with_filters({}, page_size=1000)
        return {
            'success': True,
            'data': result['data'],
            'meta': result.get('meta', {}),
            'debug_info': {
                'total_count': result.get('meta', {}).get('total', 0),
                'aggregations': result.get('aggregations', {})
            }
        }
    except Exception as e:
        raise APIException(f'Failed to get all audit rules: {str(e)}')


# ========== BULK OPERATIONS ==========

def handle_bulk_operations(
    audit_service: AuditRulesService,
    data: Dict[str, Any],
    current_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle bulk operations on audit rules
    """
    try:
        operation = data.get('operation')
        rule_ids = data.get('rule_ids', [])

        if not operation:
            raise BadRequestException('Operation is required')

        if not rule_ids:
            raise BadRequestException('Rule IDs are required')

        results = []
        errors = []

        if operation == 'activate':
            for rule_id in rule_ids:
                try:
                    result = audit_service.update_rule(rule_id, {'is_active': True}, current_user_id)
                    results.append({
                        'rule_id': rule_id,
                        'success': True,
                        'message': 'Rule activated'
                    })
                except Exception as e:
                    errors.append({
                        'rule_id': rule_id,
                        'error': str(e)
                    })

        elif operation == 'deactivate':
            for rule_id in rule_ids:
                try:
                    result = audit_service.update_rule(rule_id, {'is_active': False}, current_user_id)
                    results.append({
                        'rule_id': rule_id,
                        'success': True,
                        'message': 'Rule deactivated'
                    })
                except Exception as e:
                    errors.append({
                        'rule_id': rule_id,
                        'error': str(e)
                    })

        elif operation == 'delete':
            for rule_id in rule_ids:
                try:
                    result = audit_service.delete_rule(rule_id, current_user_id)
                    results.append({
                        'rule_id': rule_id,
                        'success': True,
                        'message': 'Rule deleted'
                    })
                except Exception as e:
                    errors.append({
                        'rule_id': rule_id,
                        'error': str(e)
                    })

        else:
            raise BadRequestException(f'Invalid operation: {operation}')

        return {
            'success': len(errors) == 0,
            'results': results,
            'errors': errors,
            'summary': {
                'total_requested': len(rule_ids),
                'successful': len(results),
                'failed': len(errors)
            }
        }

    except (BadRequestException, ValidationException):
        raise
    except Exception as e:
        raise APIException(f'Bulk operation failed: {str(e)}')


# ========== STATISTICS ==========

def handle_get_rule_statistics(
    audit_service: AuditRulesService,
    query_params: Dict[str, Any],
    current_user_organization_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Handle getting audit rules statistics
    """
    try:
        filters = {}
        if current_user_organization_id:
            filters['organization_id'] = current_user_organization_id

        result = audit_service.get_rules_with_filters(filters, page_size=1000)

        return {
            'success': True,
            'statistics': {
                'total_rules': result['meta']['total'],
                'rule_type_distribution': result['aggregations']['rule_type_counts'],
                'active_rules': result['aggregations']['active_count'],
                'global_rules': result['aggregations']['global_count'],
                'organization_rules': result['meta']['total'] - result['aggregations']['global_count']
            }
        }

    except Exception as e:
        raise APIException(f'Failed to get rule statistics: {str(e)}')