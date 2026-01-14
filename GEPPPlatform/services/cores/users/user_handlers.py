"""
User management API handlers
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .user_service import UserService
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_user_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for user management routes
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

    user_service = UserService(db_session)

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')
    current_user_email = current_user.get('email')

    # Route to specific handlers
    # IMPORTANT: Profile routes must come BEFORE generic /api/users/{user_id} routes
    # to avoid treating "profile" as a user_id

    if '/api/users/profile/upload-presigned-url' in path and method == 'POST':
        # Get presigned URL for profile image upload: /api/users/profile/upload-presigned-url
        return handle_get_profile_upload_presigned_url(user_service, data, current_user_id)

    elif '/api/users/profile' in path and method == 'GET':
        # Get current user's profile: /api/users/profile
        return handle_get_user_profile(user_service, current_user_id)

    elif '/api/users/profile' in path and method == 'PUT':
        # Update current user's profile: /api/users/profile
        return handle_update_user_profile(user_service, data, current_user_id)

    elif '/api/users/invite' in path and method == 'POST':
        return handle_send_invitation(user_service, data, current_user_id)

    elif '/api/users/invitation/' in path and method == 'POST':
        # Accept invitation: /api/users/invitation/{token}/accept
        token = path.split('/invitation/')[1].split('/')[0]
        return handle_accept_invitation(user_service, token, data)

    elif '/api/users/bulk' in path and method == 'POST':
        return handle_bulk_operations(user_service, data, current_user_id)

    # ==================== Organization-level Input Channel routes ====================
    # These routes manage QR input channels at the organization level (not tied to specific users)

    elif '/api/input-channels/' in path and method == 'GET':
        # Get channel by ID: /api/input-channels/{channel_id}
        channel_id = path.split('/input-channels/')[1].rstrip('/')
        return handle_get_organization_channel(db_session, channel_id, current_user_organization_id)

    elif '/api/input-channels/' in path and method == 'PUT':
        # Update channel: /api/input-channels/{channel_id}
        channel_id = path.split('/input-channels/')[1].rstrip('/')
        return handle_update_organization_channel(db_session, channel_id, data, current_user_organization_id)

    elif '/api/input-channels/' in path and method == 'DELETE':
        # Delete channel: /api/input-channels/{channel_id}
        channel_id = path.split('/input-channels/')[1].rstrip('/')
        return handle_delete_organization_channel(db_session, channel_id, current_user_organization_id)

    elif path == '/api/input-channels' and method == 'GET':
        # List all channels: /api/input-channels
        return handle_list_organization_channels(db_session, current_user_organization_id)

    elif path == '/api/input-channels' and method == 'POST':
        # Create channel: /api/input-channels
        return handle_create_organization_channel(db_session, data, current_user_organization_id)

    # ==================== Legacy User-based Input Channel routes (kept for backward compatibility) ====================
    elif '/api/users/' in path and '/input-channel/regenerate' in path and method == 'POST':
        # Regenerate QR code hash: /api/users/{user_id}/input-channel/regenerate
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_regenerate_input_channel(db_session, user_id, current_user_organization_id)

    elif '/api/users/' in path and '/input-channel' in path and method == 'GET':
        # Get input channel: /api/users/{user_id}/input-channel
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_get_input_channel(db_session, user_id)

    elif '/api/users/' in path and '/input-channel' in path and method == 'POST':
        # Create input channel: /api/users/{user_id}/input-channel
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_create_input_channel(db_session, user_id, data, current_user_organization_id)

    elif '/api/users/' in path and '/input-channel' in path and method == 'PUT':
        # Update input channel: /api/users/{user_id}/input-channel
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_update_input_channel(db_session, user_id, data)

    elif '/api/users/' in path and '/input-channel' in path and method == 'DELETE':
        # Delete input channel: /api/users/{user_id}/input-channel
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_delete_input_channel(db_session, user_id)

    elif '/api/users/' in path and '/suspend' in path and method == 'POST':
        # Suspend user: /api/users/{user_id}/suspend
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_suspend_user(user_service, user_id, data, current_user_id)

    elif '/api/users/' in path and '/reactivate' in path and method == 'POST':
        # Reactivate user: /api/users/{user_id}/reactivate
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_reactivate_user(user_service, user_id, current_user_id)

    elif '/api/users/' in path and '/reset-password' in path and method == 'POST':
        # Reset password: /api/users/{user_id}/reset-password
        user_id = path.split('/users/')[1].split('/')[0]
        return handle_reset_password(user_service, user_id, current_user_id)

    elif '/api/users/' in path and method == 'GET':
        # Get user details: /api/users/{user_id}
        user_id = path.split('/users/')[1].rstrip('/')
        return handle_get_user_details(user_service, user_id)

    elif '/api/users/' in path and method == 'PUT':
        # Update user: /api/users/{user_id}
        user_id = path.split('/users/')[1].rstrip('/')
        return handle_update_user(user_service, user_id, data, current_user_id)

    elif '/api/users/' in path and method == 'DELETE':
        # Delete user: /api/users/{user_id}
        user_id = path.split('/users/')[1].rstrip('/')
        return handle_delete_user(user_service, user_id, current_user_id)

    elif '/api/users' == path and method == 'GET':
        # List users with filters (pass current_user for organization filtering)
        return handle_list_users(user_service, query_params, current_user)

    elif '/api/users' == path and method == 'POST':
        # Create new user
        return handle_create_user(user_service, data, current_user_id)

    elif '/api/locations' == path and method == 'GET':
        # Get user locations (is_location = True)
        return handle_get_locations(user_service, query_params, current_user, headers)

    elif '/api/locations/' in path and method == 'PUT' and '/tags/' not in path:
        # Update location: /api/locations/{location_id}
        location_id = path.split('/locations/')[1].rstrip('/')
        return handle_update_location(db_session, location_id, data, current_user_organization_id)

    # ==================== Location Tags routes ====================

    elif '/api/locations/tags/' in path and method == 'GET':
        # Get tag by ID: /api/locations/tags/{tag_id}
        tag_id = path.split('/tags/')[1].rstrip('/')
        return handle_get_location_tag(db_session, tag_id, current_user_organization_id)

    elif '/api/locations/tags/' in path and method == 'PUT':
        # Update tag: /api/locations/tags/{tag_id}
        tag_id = path.split('/tags/')[1].rstrip('/')
        return handle_update_location_tag(db_session, tag_id, data, current_user_organization_id)

    elif '/api/locations/tags/' in path and method == 'DELETE':
        # Delete tag: /api/locations/tags/{tag_id}
        tag_id = path.split('/tags/')[1].rstrip('/')
        return handle_delete_location_tag(db_session, tag_id, current_user_organization_id)

    elif '/api/locations/tags' == path and method == 'GET':
        # List tags: /api/locations/tags?user_location_id=X or all for organization
        return handle_list_location_tags(db_session, query_params, current_user_organization_id)

    elif '/api/locations/tags' == path and method == 'POST':
        # Create tag: /api/locations/tags
        return handle_create_location_tag(db_session, data, current_user_organization_id, current_user_id)

    else:
        raise NotFoundException(f'Route not found: {path} [{method}]')


def handle_list_users(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """Handle GET /api/users - List users with filtering"""
    try:
        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('page_size', 20))

        # Map frontend field names to database field names
        sort_by_raw = query_params.get('sort_by', 'created_date')
        sort_field_mapping = {
            'createdAt': 'created_date',
            'updatedAt': 'updated_date',
            'displayName': 'display_name',
            'companyName': 'company_name'
        }
        sort_by = sort_field_mapping.get(sort_by_raw, sort_by_raw)
        sort_order = query_params.get('sort_order', 'desc')

        # Build filters
        filters = {}
        if query_params.get('query'):
            filters['query'] = query_params['query']

        if query_params.get('roles'):
            filters['roles'] = query_params['roles'].split(',')

        if query_params.get('organization_roles'):
            filters['organization_roles'] = query_params['organization_roles'].split(',')

        if query_params.get('platforms'):
            # Platform values as they appear in database (from screenshot, without BUSINESS and REWARDS)
            # Valid values: NA, WEB, MOBILE, API, GEPP_BUSINESS_WEB, GEPP_REWARD_APP, ADMIN_WEB, GEPP_EPR_WEB
            platform_list = [p.strip().upper() for p in query_params['platforms'].split(',')]

            # Map frontend aliases to actual database values (using full names only)
            platform_mapping = {
                'BUSINESS': 'GEPP_BUSINESS_WEB',  # Map old BUSINESS to GEPP_BUSINESS_WEB
                'REWARDS': 'GEPP_REWARD_APP',    # Map old REWARDS to GEPP_REWARD_APP
                'EPR': 'GEPP_EPR_WEB',
                'ADMIN': 'ADMIN_WEB'
            }

            mapped_platforms = []
            for platform in platform_list:
                mapped_platforms.append(platform_mapping.get(platform, platform))

            filters['platforms'] = mapped_platforms

        if query_params.get('organization_ids'):
            filters['organization_ids'] = query_params['organization_ids'].split(',')
        elif current_user and current_user.get('organization_id'):
            # If no organization_ids specified but user has organization, filter by user's organization
            filters['organization_ids'] = [str(current_user['organization_id'])]

        if query_params.get('status'):
            filters['status'] = query_params['status']

        # Get users
        result = user_service.get_users_with_filters(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        return result

    except ValueError as e:
        raise BadRequestException(f'Invalid query parameters: {str(e)}')
    except Exception as e:
        raise APIException(f'Failed to list users: {str(e)}')


def handle_create_user(
    user_service: UserService,
    data: Dict[str, Any],
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users - Create new user"""
    try:
        # Validate required fields
        required_fields = ['display_name']
        for field in required_fields:
            if field not in data:
                raise ValidationException(f'Missing required field: {field}')

        # Extract options
        auto_generate_credentials = data.pop('auto_generate_credentials', False)
        send_invitation = data.pop('send_invitation', False)

        # Create user
        result = user_service.create_user(
            user_data=data,
            created_by_id=current_user_id,
            auto_generate_credentials=auto_generate_credentials,
            send_invitation=send_invitation
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to create user: {str(e)}')


def handle_get_user_details(user_service: UserService, user_id: str) -> Dict[str, Any]:
    """Handle GET /api/users/{user_id} - Get user details"""
    try:
        result = user_service.get_user_details(user_id)
        if not result:
            raise NotFoundException('User not found')

        return result

    except Exception as e:
        raise APIException(f'Failed to get user details: {str(e)}')


def handle_update_user(
    user_service: UserService,
    user_id: str,
    data: Dict[str, Any],
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle PUT /api/users/{user_id} - Update user"""
    try:
        result = user_service.update_user(
            user_id=user_id,
            updates=data,
            updated_by_id=current_user_id
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to update user: {str(e)}')


def handle_delete_user(
    user_service: UserService,
    user_id: str,
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle DELETE /api/users/{user_id} - Delete user"""
    try:
        from .user_crud import UserCRUD
        crud = UserCRUD(user_service.db)

        success = crud.delete_user(
            user_id=user_id,
            soft_delete=True,  # Default to soft delete
            deleted_by_id=current_user_id
        )

        if success:
            return {'message': 'User deleted successfully'}
        else:
            raise NotFoundException('User not found or could not be deleted')

    except Exception as e:
        raise APIException(f'Failed to delete user: {str(e)}')


def handle_suspend_user(
    user_service: UserService,
    user_id: str,
    data: Dict[str, Any],
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users/{user_id}/suspend - Suspend user"""
    try:
        reason = data.get('reason')
        result = user_service.suspend_user(
            user_id=user_id,
            reason=reason,
            suspended_by_id=current_user_id
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to suspend user: {str(e)}')


def handle_reactivate_user(
    user_service: UserService,
    user_id: str,
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users/{user_id}/reactivate - Reactivate user"""
    try:
        result = user_service.reactivate_user(
            user_id=user_id,
            reactivated_by_id=current_user_id
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to reactivate user: {str(e)}')


def handle_reset_password(
    user_service: UserService,
    user_id: str,
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users/{user_id}/reset-password - Reset user password"""
    try:
        result = user_service.reset_password(
            user_id=user_id,
            reset_by_id=current_user_id
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to reset password: {str(e)}')


def handle_send_invitation(
    user_service: UserService,
    data: Dict[str, Any],
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users/invite - Send user invitation"""
    try:
        # Validate required fields
        required_fields = ['email', 'organization_id']
        for field in required_fields:
            if field not in data:
                raise ValidationException(f'Missing required field: {field}')

        result = user_service.send_invitation(
            invitation_data=data,
            invited_by_id=current_user_id
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to send invitation: {str(e)}')


def handle_accept_invitation(
    user_service: UserService,
    token: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle POST /api/users/invitation/{token}/accept - Accept invitation"""
    try:
        # Validate required fields for user creation
        required_fields = ['display_name', 'password']
        for field in required_fields:
            if field not in data:
                raise ValidationException(f'Missing required field: {field}')

        from .user_crud import UserCRUD
        crud = UserCRUD(user_service.db)

        success, user = crud.accept_invitation(token, data)

        if success and user:
            return {
                'success': True,
                'message': 'Invitation accepted successfully',
                'user': user_service._serialize_user(user)
            }
        else:
            raise BadRequestException('Invalid or expired invitation token')

    except Exception as e:
        raise APIException(f'Failed to accept invitation: {str(e)}')


def handle_bulk_operations(
    user_service: UserService,
    data: Dict[str, Any],
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/users/bulk - Bulk operations on users"""
    try:
        operation = data.get('operation')
        user_ids = data.get('user_ids', [])

        if not operation or not user_ids:
            raise ValidationException('Missing operation or user_ids')

        if operation == 'update_roles':
            organization_role_id = data.get('organization_role_id')

            result = user_service.bulk_update_roles(
                user_ids=user_ids,
                organization_role_id=organization_role_id,
                updated_by_id=current_user_id
            )

        elif operation == 'suspend':
            reason = data.get('reason')

            result = user_service.bulk_suspend_users(
                user_ids=user_ids,
                reason=reason,
                suspended_by_id=current_user_id
            )

        elif operation == 'invite':
            # Send invitations to multiple users
            from .user_crud import UserCRUD
            crud = UserCRUD(user_service.db)

            success_count = 0
            errors = []

            for user_id in user_ids:
                user = crud.get_user_by_id(user_id)
                if user and user.email:
                    try:
                        # Create invitation for existing user (resend)
                        invitation_result = user_service.resend_invitation(user_id)
                        if invitation_result.get('success'):
                            success_count += 1
                        else:
                            errors.append(f"Failed to invite user {user_id}")
                    except Exception as e:
                        errors.append(f"Error inviting user {user_id}: {str(e)}")
                else:
                    errors.append(f"User {user_id} not found or has no email")

            result = {
                'success': len(errors) == 0,
                'invited_count': success_count,
                'errors': errors
            }

        else:
            raise BadRequestException(f'Unknown operation: {operation}')

        return result

    except Exception as e:
        raise APIException(f'Failed to perform bulk operation: {str(e)}')


# Additional utility handlers

def handle_get_user_permissions(user_service: UserService, user_id: str) -> Dict[str, Any]:
    """Get user permissions (can be added as a route)"""
    try:
        permissions = user_service.permissions.get_user_permissions(user_id)
        return {'permissions': permissions}

    except Exception as e:
        raise APIException(f'Failed to get user permissions: {str(e)}')


def handle_get_organization_users(
    user_service: UserService,
    organization_id: str,
    query_params: Dict[str, Any]
) -> Dict[str, Any]:
    """Get users in an organization (can be added as a route)"""
    try:
        from .user_crud import UserCRUD
        crud = UserCRUD(user_service.db)

        include_hierarchy = query_params.get('include_hierarchy', 'true').lower() == 'true'

        users = crud.get_organization_users(
            organization_id=organization_id,
            include_hierarchy=include_hierarchy
        )

        return {
            'users': [user_service._serialize_user(user) for user in users],
            'organization_id': organization_id,
            'count': len(users)
        }

    except Exception as e:
        raise APIException(f'Failed to get organization users: {str(e)}')


def handle_get_locations(user_service: UserService, query_params: Dict[str, Any], current_user: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Handle GET /api/locations - Get user locations (is_location = True)"""
    try:
        # Get current user's organization ID for filtering
        organization_id = current_user.get('organization_id') if current_user else None

        if not organization_id:
            raise NotFoundException('User is not part of any organization')

        # Check if we should return all locations or filter by organization setup
        include_all = query_params.get('all', '').lower() == 'true'

        # Get user locations with filtering
        locations = user_service.get_locations(
            organization_id=organization_id,
            include_all=include_all
        )

        return {
            'success': True,
            'data': locations,
            'total': len(locations),
            'organization_id': organization_id,
            'include_all': include_all,
            'message': f'Retrieved {len(locations)} locations'
        }

    except Exception as e:
        raise APIException(f'Error fetching locations: {str(e)}')


def handle_update_location(
    db_session,
    location_id: str,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle PUT /api/locations/{location_id} - Update location"""
    try:
        from GEPPPlatform.models.users.user_location import UserLocation
        from GEPPPlatform.models.users.user_related import UserLocationTag
        from sqlalchemy import and_
        from datetime import datetime

        # Find the location
        location = db_session.query(UserLocation).filter(
            and_(
                UserLocation.id == int(location_id),
                UserLocation.organization_id == organization_id,
                UserLocation.is_location == True,
                UserLocation.deleted_date.is_(None)
            )
        ).first()

        if not location:
            raise NotFoundException(f'Location not found: {location_id}')

        # Update basic fields
        if 'name' in data:
            location.name_en = data['name']
            location.display_name = data['name']
        if 'address' in data:
            location.address = data['address']

        # Handle tag assignments
        if 'tag_ids' in data:
            tag_ids = data['tag_ids'] or []

            # Get existing tags for this location
            existing_tags = db_session.query(UserLocationTag).filter(
                and_(
                    UserLocationTag.user_location_id == int(location_id),
                    UserLocationTag.organization_id == organization_id,
                    UserLocationTag.deleted_date.is_(None)
                )
            ).all()

            # Note: Tags are managed separately through /api/locations/tags
            # The tag_ids here are for reference - the frontend should handle tag creation/assignment

        # Handle user assignments
        if 'users' in data:
            location.users = data['users']

        location.updated_date = datetime.utcnow()
        db_session.commit()

        # Get tags for this location
        tags = db_session.query(UserLocationTag).filter(
            and_(
                UserLocationTag.user_location_id == int(location_id),
                UserLocationTag.organization_id == organization_id,
                UserLocationTag.deleted_date.is_(None)
            )
        ).all()

        # Serialize response
        return {
            'success': True,
            'location': {
                'id': location.id,
                'name': location.display_name or location.name_en,
                'address': getattr(location, 'address', None),
                'users': getattr(location, 'users', []) or [],
                'tags': [
                    {
                        'id': tag.id,
                        'name': tag.name,
                        'note': tag.note,
                        'start_date': tag.start_date.isoformat() if tag.start_date else None,
                        'end_date': tag.end_date.isoformat() if tag.end_date else None,
                        'members': tag.members or []
                    }
                    for tag in tags
                ],
                'updated_date': location.updated_date.isoformat() if location.updated_date else None
            },
            'message': 'Location updated successfully'
        }

    except NotFoundException:
        raise
    except Exception as e:
        db_session.rollback()
        raise APIException(f'Failed to update location: {str(e)}')


def handle_get_user_profile(user_service: UserService, current_user_id: str) -> Dict[str, Any]:
    """Handle GET /api/users/profile - Get current user's profile"""
    try:
        result = user_service.get_user_profile(current_user_id)
        if not result:
            raise NotFoundException('User profile not found')

        return result

    except Exception as e:
        raise APIException(f'Failed to get user profile: {str(e)}')


def handle_update_user_profile(
    user_service: UserService,
    data: Dict[str, Any],
    current_user_id: str
) -> Dict[str, Any]:
    """Handle PUT /api/users/profile - Update current user's profile"""
    try:
        result = user_service.update_user_profile(
            user_id=current_user_id,
            updates=data
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to update user profile: {str(e)}')


def handle_get_profile_upload_presigned_url(
    user_service: UserService,
    data: Dict[str, Any],
    current_user_id: str
) -> Dict[str, Any]:
    """Handle POST /api/users/profile/upload-presigned-url - Get presigned URL for profile image upload"""
    try:
        # Validate required fields
        file_name = data.get('file_name')
        if not file_name:
            raise ValidationException('Missing required field: file_name')

        result = user_service.get_profile_image_presigned_url(
            user_id=current_user_id,
            file_name=file_name
        )

        return result

    except Exception as e:
        raise APIException(f'Failed to get presigned URL: {str(e)}')


# Input Channel Handlers
def handle_get_input_channel(db_session, user_id: str) -> Dict[str, Any]:
    """Handle GET /api/users/{user_id}/input-channel - Get input channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.get_input_channel(int(user_id))
        if not result:
            return {'channel': None, 'message': 'No input channel found'}

        return {'channel': result}

    except Exception as e:
        raise APIException(f'Failed to get input channel: {str(e)}')


def handle_create_input_channel(
    db_session,
    user_id: str,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle POST /api/users/{user_id}/input-channel - Create input channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.create_input_channel(
            user_location_id=int(user_id),
            organization_id=organization_id,
            data=data
        )

        return {'channel': result, 'message': 'Input channel created successfully'}

    except Exception as e:
        raise APIException(f'Failed to create input channel: {str(e)}')


def handle_update_input_channel(
    db_session,
    user_id: str,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle PUT /api/users/{user_id}/input-channel - Update input channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.update_input_channel(
            user_location_id=int(user_id),
            data=data
        )

        return {'channel': result, 'message': 'Input channel updated successfully'}

    except Exception as e:
        raise APIException(f'Failed to update input channel: {str(e)}')


def handle_regenerate_input_channel(
    db_session,
    user_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """Handle POST /api/users/{user_id}/input-channel/regenerate - Regenerate QR code hash"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        # Check if channel exists, if not create one
        existing = service.get_input_channel(int(user_id))
        if not existing:
            result = service.create_input_channel(
                user_location_id=int(user_id),
                organization_id=organization_id,
                data={}
            )
        else:
            result = service.regenerate_hash(int(user_id))

        return {'channel': result, 'message': 'QR code regenerated successfully'}

    except Exception as e:
        raise APIException(f'Failed to regenerate input channel: {str(e)}')


def handle_delete_input_channel(db_session, user_id: str) -> Dict[str, Any]:
    """Handle DELETE /api/users/{user_id}/input-channel - Delete input channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        success = service.delete_input_channel(int(user_id))
        if success:
            return {'message': 'Input channel deleted successfully'}
        else:
            raise NotFoundException('Input channel not found')

    except Exception as e:
        raise APIException(f'Failed to delete input channel: {str(e)}')


# ==================== Organization-level Input Channel Handlers ====================

def handle_list_organization_channels(db_session, organization_id: int) -> Dict[str, Any]:
    """Handle GET /api/input-channels - List all channels for organization"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        channels = service.get_organization_channels(organization_id)
        return {
            'channels': channels,
            'total': len(channels)
        }

    except Exception as e:
        raise APIException(f'Failed to list input channels: {str(e)}')


def handle_get_organization_channel(
    db_session,
    channel_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """Handle GET /api/input-channels/{channel_id} - Get channel by ID"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.get_channel_by_id(int(channel_id), organization_id)
        if not result:
            raise NotFoundException('Input channel not found')

        return {'channel': result}

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to get input channel: {str(e)}')


def handle_create_organization_channel(
    db_session,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle POST /api/input-channels - Create organization-level channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.create_organization_channel(
            organization_id=organization_id,
            data=data
        )

        return {'channel': result, 'message': 'Input channel created successfully'}

    except Exception as e:
        raise APIException(f'Failed to create input channel: {str(e)}')


def handle_update_organization_channel(
    db_session,
    channel_id: str,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle PUT /api/input-channels/{channel_id} - Update channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        result = service.update_organization_channel(
            channel_id=int(channel_id),
            organization_id=organization_id,
            data=data
        )

        return {'channel': result, 'message': 'Input channel updated successfully'}

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to update input channel: {str(e)}')


def handle_delete_organization_channel(
    db_session,
    channel_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """Handle DELETE /api/input-channels/{channel_id} - Delete channel"""
    try:
        from .input_channel_service import InputChannelService
        service = InputChannelService(db_session)

        success = service.delete_organization_channel(int(channel_id), organization_id)
        if success:
            return {'message': 'Input channel deleted successfully'}
        else:
            raise NotFoundException('Input channel not found')

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to delete input channel: {str(e)}')


# ==================== Location Tags Handlers ====================

def handle_list_location_tags(
    db_session,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle GET /api/locations/tags - List tags"""
    try:
        from .location_tag_service import LocationTagService
        service = LocationTagService(db_session)

        user_location_id = query_params.get('user_location_id')
        include_inactive = query_params.get('include_inactive', '').lower() == 'true'

        if user_location_id:
            # Get tags for specific location
            tags = service.get_tags_by_location(
                user_location_id=int(user_location_id),
                organization_id=organization_id,
                include_inactive=include_inactive
            )
        else:
            # Get all tags for organization
            tags = service.get_tags_by_organization(
                organization_id=organization_id,
                include_inactive=include_inactive
            )

        return {
            'tags': tags,
            'total': len(tags)
        }

    except Exception as e:
        raise APIException(f'Failed to list location tags: {str(e)}')


def handle_get_location_tag(
    db_session,
    tag_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """Handle GET /api/locations/tags/{tag_id} - Get tag by ID"""
    try:
        from .location_tag_service import LocationTagService
        service = LocationTagService(db_session)

        result = service.get_tag_by_id(int(tag_id), organization_id)
        if not result:
            raise NotFoundException('Location tag not found')

        return {'tag': result}

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to get location tag: {str(e)}')


def handle_create_location_tag(
    db_session,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: Optional[str]
) -> Dict[str, Any]:
    """Handle POST /api/locations/tags - Create tag"""
    try:
        from .location_tag_service import LocationTagService
        service = LocationTagService(db_session)

        # Validate required fields
        user_location_id = data.get('user_location_id')
        if not user_location_id:
            raise ValidationException('user_location_id is required')

        result = service.create_tag(
            user_location_id=int(user_location_id),
            organization_id=organization_id,
            data=data,
            created_by_id=int(current_user_id) if current_user_id else None
        )

        return {'tag': result, 'message': 'Location tag created successfully'}

    except (NotFoundException, BadRequestException, ValidationException):
        raise
    except Exception as e:
        raise APIException(f'Failed to create location tag: {str(e)}')


def handle_update_location_tag(
    db_session,
    tag_id: str,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """Handle PUT /api/locations/tags/{tag_id} - Update tag"""
    try:
        from .location_tag_service import LocationTagService
        service = LocationTagService(db_session)

        result = service.update_tag(
            tag_id=int(tag_id),
            organization_id=organization_id,
            data=data
        )

        return {'tag': result, 'message': 'Location tag updated successfully'}

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to update location tag: {str(e)}')


def handle_delete_location_tag(
    db_session,
    tag_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """Handle DELETE /api/locations/tags/{tag_id} - Delete tag"""
    try:
        from .location_tag_service import LocationTagService
        service = LocationTagService(db_session)

        success = service.delete_tag(int(tag_id), organization_id)
        if success:
            return {'message': 'Location tag deleted successfully'}
        else:
            raise NotFoundException('Location tag not found')

    except NotFoundException:
        raise
    except Exception as e:
        raise APIException(f'Failed to delete location tag: {str(e)}')
