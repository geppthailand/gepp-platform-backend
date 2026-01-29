"""
Organization API handlers
"""

import json
from typing import Dict, Any

from .organization_service import OrganizationService
from .dto.organization_requests import CreateOrganizationSetupRequest, UpdateOrganizationSetupRequest
from .dto.organization_responses import OrganizationSetupResponse
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def organization_routes(event: Dict[str, Any], context: Any, **params) -> Dict[str, Any]:
    """
    Route handler for organization-related API endpoints
    """

    # Extract path and method
    path = event.get("rawPath", "")
    method = event['requestContext']['http'].get("method", "GET")
    db_session = params.get('db_session')

    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Content-Type': 'application/json'
    }

    # Handle OPTIONS request for CORS
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'message': 'CORS preflight'})
        }

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    user_id = current_user.get('user_id')
    user_organization_id = current_user.get('organization_id')
    user_email = current_user.get('email')

    if not user_id:
        raise UnauthorizedException('User ID not found in request')

    # Use the provided database session
    org_service = OrganizationService(db_session)

    if method == 'GET' and '/api/organizations/me' in path:
        return handle_get_my_organization(org_service, user_id, headers)

    elif method == 'GET' and '/api/organizations/my-organization' in path:
        return handle_get_my_organization(org_service, user_id, headers)

    elif method == 'GET' and '/api/organizations/roles' in path:
        return handle_get_organization_roles(org_service, user_id, headers)

    elif method == 'GET' and '/api/organizations/members' in path:
        return handle_get_organization_members(org_service, user_id, headers)

    elif method == 'POST' and '/api/organizations/members' in path:
        body = json.loads(event.get('body', '{}'))
        return handle_create_organization_member(org_service, user_id, body, headers)

    # Organization Role CRUD operations
    elif method == 'POST' and '/api/organizations/roles' in path:
        body = json.loads(event.get('body', '{}'))
        return handle_create_organization_role(org_service, user_id, body, headers)

    elif method == 'PUT' and '/api/organizations/roles/' in path:
        role_id = path.split('/')[-1]
        body = json.loads(event.get('body', '{}'))
        return handle_update_organization_role(org_service, user_id, role_id, body, headers)

    elif method == 'DELETE' and '/api/organizations/roles/' in path:
        role_id = path.split('/')[-1]
        return handle_delete_organization_role(org_service, user_id, role_id, headers)

    # Organization Setup endpoints
    elif method == 'GET' and '/api/organizations/setup' in path:
        return handle_get_organization_setup(org_service, user_id, headers)

    elif method == 'POST' and '/api/organizations/setup' in path:
        body = json.loads(event.get('body', '{}'))
        return handle_create_organization_setup(org_service, user_id, body, headers)

    elif method == 'PUT' and '/api/organizations/setup' in path:
        body = json.loads(event.get('body', '{}'))
        return handle_update_organization_setup(org_service, user_id, body, headers)

    # AI Audit Permission endpoint
    elif method == 'PUT' and '/api/organizations/ai-audit-permission' in path:
        body = json.loads(event.get('body', '{}'))
        return handle_update_ai_audit_permission(org_service, user_id, user_organization_id, body, headers)

    # Notification settings (create/upsert)
    elif method == 'POST' and '/api/organizations/notification-settings' in path:
        body = json.loads(event.get('body') or '{}')
        return handle_upsert_notification_settings(org_service, user_id, body, headers)

    else:
        raise NotFoundException('Organization endpoint not found')


def handle_get_my_organization(org_service: OrganizationService, user_id: int, headers: Dict[str, str]) -> Dict[str, Any]:
    """Get the organization that the current user belongs to"""
    organization = org_service.get_user_organization(user_id)

    if not organization:
        raise NotFoundException('User is not part of any organization')

    org_info = org_service.get_organization_info(organization.id)
    return org_info


def handle_get_organization_roles(org_service: OrganizationService, user_id: int, headers: Dict[str, str]) -> list:
    """Get available organization roles for the user's organization"""
    # Get user's organization
    organization = org_service.get_user_organization(user_id)

    if not organization:
        raise NotFoundException('User is not part of any organization')

    roles = org_service.get_organization_roles(organization.id)
    return roles


def handle_get_organization_members(org_service: OrganizationService, user_id: int, headers: Dict[str, str]) -> Dict[str, Any]:
    """Get members of the user's organization"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        members = org_service.get_organization_members(organization.id)

        return {'success': True, 'data': members}

    except Exception as e:
        raise APIException(f'Error fetching members: {str(e)}')


def handle_create_organization_member(org_service: OrganizationService, user_id: int, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Create a new member for the user's organization"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Validate required fields
        required_fields = ['emailOrPhone', 'organization_role_id']
        for field in required_fields:
            if field not in body:
                raise ValidationException(f'Missing required field: {field}')

        # Validate organization role
        role_id = body['organization_role_id']
        if not org_service.validate_organization_role(organization.id, role_id):
            raise ValidationException('Invalid organization role')

        # Prepare user data
        user_data = {
            'email': body['emailOrPhone'],  # Assuming email for now
            'display_name': body.get('display_name', body['emailOrPhone'].split('@')[0]),
            'organization_role_id': role_id,
            'company_name': body.get('company_name'),
            'business_industry': body.get('business_industry'),
            'business_sub_industry': body.get('business_sub_industry'),
            'locale': body.get('locale', 'TH'),
            'send_invitation': body.get('send_invitation', True)
        }

        # Create the member
        new_member = org_service.create_organization_member(
            organization_id=organization.id,
            user_data=user_data,
            created_by_user_id=user_id
        )

        return {
            'success': True,
            'data': {
                'id': new_member.id,
                'display_name': new_member.display_name,
                'email': new_member.email,
                'organization_id': new_member.organization_id
            },
            'message': 'Organization member created successfully'
        }

    except Exception as e:
        raise APIException(f'Error creating member: {str(e)}')


def handle_create_organization_role(org_service: OrganizationService, user_id: int, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Create a new role for the user's organization"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Validate required fields
        required_fields = ['key', 'name']
        for field in required_fields:
            if field not in body:
                raise ValidationException(f'Missing required field: {field}')

        # Create the role
        role_data = org_service.create_organization_role(organization.id, body)

        return {
            'success': True,
            'data': role_data,
            'message': 'Organization role created successfully'
        }

    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise APIException(f'Error creating role: {str(e)}')


def handle_update_organization_role(org_service: OrganizationService, user_id: int, role_id: str, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Update an organization role"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Convert role_id to int
        try:
            role_id_int = int(role_id)
        except ValueError:
            raise BadRequestException('Invalid role ID')

        # Update the role
        role_data = org_service.update_organization_role(organization.id, role_id_int, body)

        return {
            'success': True,
            'data': role_data,
            'message': 'Organization role updated successfully'
        }

    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise APIException(f'Error updating role: {str(e)}')


def handle_delete_organization_role(org_service: OrganizationService, user_id: int, role_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Delete an organization role"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Convert role_id to int
        try:
            role_id_int = int(role_id)
        except ValueError:
            raise BadRequestException('Invalid role ID')

        # Delete the role
        success = org_service.delete_organization_role(organization.id, role_id_int)

        if success:
            return {
                'success': True,
                'message': 'Organization role deleted successfully'
            }
        else:
            raise BadRequestException('Failed to delete role')

    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise APIException(f'Error deleting role: {str(e)}')


def handle_get_organization_setup(org_service: OrganizationService, user_id: int, headers: Dict[str, str]) -> Dict[str, Any]:
    """Get the organization setup structure for the user's organization"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Get organization setup
        setup_data = org_service.get_organization_setup(organization.id)

        # Extract organization data
        organization_data = {
            'id': organization.id,
            'display_name': organization.organization_info.display_name if organization.organization_info else None
        }

        if not setup_data:
            # Return null/None if no setup found as specified in requirements
            return {
                'success': True,
                'data': None,
                'organization': organization_data,
                'message': 'No organization setup found'
            }

        # Convert to response DTO
        setup_response = OrganizationSetupResponse.from_dict(setup_data)

        return {
            'success': True,
            'data': setup_response.to_dict(),
            'organization': organization_data,
            'message': 'Organization setup retrieved successfully'
        }

    except Exception as e:
        raise APIException(f'Error fetching organization setup: {str(e)}')


def handle_create_organization_setup(org_service: OrganizationService, user_id: int, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Create organization setup structure for the user's organization"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Convert to request DTO and validate
        setup_request = CreateOrganizationSetupRequest.from_dict(body)
        validation_errors = setup_request.validate()

        if validation_errors:
            raise ValidationException(validation_errors)

        # Prepare setup data including locations
        setup_data_dict = setup_request.to_dict()
        # Add locations from the original request body
        if 'locations' in body:
            setup_data_dict['locations'] = body['locations']

        # Create organization setup
        setup_data = org_service.create_organization_setup(
            organization_id=organization.id,
            setup_data=setup_data_dict
        )

        # Convert to response DTO
        setup_response = OrganizationSetupResponse.from_dict(setup_data)

        return {
            'success': True,
            'data': setup_response.to_dict(),
            'message': 'Organization setup created successfully'
        }

    except ValidationException as e:
        raise BadRequestException(f'Validation error: {"; ".join(e.errors) if hasattr(e, "errors") else str(e)}')
    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise APIException(f'Error creating organization setup: {str(e)}')


def handle_update_organization_setup(org_service: OrganizationService, user_id: int, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Update organization setup structure (creates new version)"""
    try:
        # Get user's organization
        organization = org_service.get_user_organization(user_id)

        if not organization:
            raise NotFoundException('User is not part of any organization')

        # Convert to request DTO and validate
        setup_request = UpdateOrganizationSetupRequest.from_dict(body)
        validation_errors = setup_request.validate()

        if validation_errors:
            raise ValidationException(validation_errors)

        # Prepare setup data including locations
        setup_data_dict = setup_request.to_dict()
        # Add locations from the original request body
        if 'locations' in body:
            setup_data_dict['locations'] = body['locations']

        # Update organization setup (creates new version)
        setup_data = org_service.update_organization_setup(
            organization_id=organization.id,
            setup_data=setup_data_dict
        )

        # Convert to response DTO
        setup_response = OrganizationSetupResponse.from_dict(setup_data)

        return {
            'success': True,
            'data': setup_response.to_dict(),
            'message': 'Organization setup updated successfully'
        }

    except ValidationException as e:
        raise BadRequestException(f'Validation error: {"; ".join(e.errors) if hasattr(e, "errors") else str(e)}')
    except ValueError as e:
        raise BadRequestException(str(e))
    except Exception as e:
        raise APIException(f'Error updating organization setup: {str(e)}')


def handle_upsert_notification_settings(
    org_service: OrganizationService,
    user_id: int,
    body: Any,
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """Create or update organization notification settings from a list of items.
    Body format: { "data": [ { organization_id, event, role, ... }, ... ] }
    """
    if not isinstance(body, dict) or 'data' not in body:
        raise ValidationException('Request body must be { "data": [ ... ] } with data as array of notification setting items')
    items = body['data']
    if not isinstance(items, list):
        raise ValidationException('Body "data" must be a JSON array of notification setting items')

    organization = org_service.get_user_organization(user_id)
    if not organization:
        raise NotFoundException('User is not part of any organization')

    data = org_service.upsert_notification_settings(organization.id, items)
    return {
        'success': True,
        'data': data,
        'message': f'Notification settings saved ({len(data)} item(s))',
    }


def handle_update_ai_audit_permission(
    org_service: OrganizationService,
    user_id: int,
    organization_id: int,
    body: Dict[str, Any],
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """Update organization's AI audit permission"""
    try:
        # Validate input
        allow_ai_audit = body.get('allow_ai_audit')
        if allow_ai_audit is None:
            raise ValidationException('allow_ai_audit field is required')

        if not isinstance(allow_ai_audit, bool):
            raise ValidationException('allow_ai_audit must be a boolean value')

        # Verify user belongs to the organization
        user_org = org_service.get_user_organization(user_id)
        if not user_org or user_org.id != organization_id:
            raise UnauthorizedException('User does not have permission to update this organization')

        # Update the permission
        result = org_service.update_ai_audit_permission(organization_id, allow_ai_audit)

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'data': {
                    'organization_id': organization_id,
                    'allow_ai_audit': allow_ai_audit
                },
                'message': f'AI audit permission {"enabled" if allow_ai_audit else "disabled"} successfully'
            })
        }

    except ValidationException as e:
        raise BadRequestException(str(e))
    except UnauthorizedException:
        raise
    except Exception as e:
        raise APIException(f'Error updating AI audit permission: {str(e)}')