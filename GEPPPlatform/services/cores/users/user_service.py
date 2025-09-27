"""
High-level user management service
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import string

from .user_crud import UserCRUD
from .user_permissions import UserPermissionService
from ....models.users.user_location import UserLocation
from ....models.users.user_related import UserRoleEnum


class UserService:
    """
    High-level user management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db
        self.crud = UserCRUD(db)
        self.permissions = UserPermissionService(db)

    # ========== USER MANAGEMENT ==========

    def create_user(
        self,
        user_data: Dict[str, Any],
        created_by_id: Optional[str] = None,
        auto_generate_credentials: bool = False,
        send_invitation: bool = False
    ) -> Dict[str, Any]:
        """
        Create user with enhanced business logic
        """
        try:
            # Validate user data
            validation_result = self._validate_user_data(user_data)
            if not validation_result['valid']:
                from ....exceptions import ValidationException
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'User validation failed: {error_messages}')

            # Auto-generate credentials if needed
            if auto_generate_credentials:
                if not user_data.get('username') and user_data.get('email'):
                    user_data['username'] = user_data['email'].split('@')[0]

                if not user_data.get('password'):
                    user_data['password'] = self._generate_secure_password()

            # Set default organization role if not provided
            if not user_data.get('organization_role_id') and not user_data.get('role'):
                # Set a default viewer role if no role specified
                user_data['role'] = 'viewer'

            # Validate organization inheritance for sub-users
            self._validate_organization_inheritance(user_data, created_by_id)
            print("-=-=-=-=", user_data)
            # Create user
            user = self.crud.create_user(
                user_data=user_data,
                created_by_id=created_by_id,
                send_invitation=send_invitation
            )

            return {
                'success': True,
                'user': self._serialize_user(user),
                'generated_password': user_data.get('password') if auto_generate_credentials else None,
                'invitation_sent': send_invitation
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    def get_users_with_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_date',
        sort_order: str = 'desc'
    ) -> Dict[str, Any]:
        """
        Get users with enhanced filtering and metadata
        """
        users, total_count = self.crud.get_users(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        # Get aggregations
        aggregations = self._get_user_aggregations(filters)

        return {
            'data': [self._serialize_user(user) for user in users],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'pages': (total_count + page_size - 1) // page_size,
                'has_next': page * page_size < total_count,
                'has_prev': page > 1
            },
            'aggregations': aggregations
        }

    def get_user_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive user details
        """
        user = self.crud.get_user_by_id(user_id, include_relations=True)
        if not user:
            return None

        # Get additional user data
        activities = self.crud.get_user_activities(user_id, limit=20)
        permissions = self.permissions.get_user_permissions(user_id)

        return {
            'user': self._serialize_user(user, include_sensitive=False),
            'activities': [self._serialize_activity(activity) for activity in activities],
            'permissions': permissions,
            'organization_tree': self._get_user_organization_tree(user),
            'subscription_status': self._get_user_subscription_status(user_id)
        }

    def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
        updated_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update user with validation and business logic
        """
        try:
            # Validate updates
            validation_result = self._validate_user_updates(user_id, updates)
            if not validation_result['valid']:
                from ....exceptions import ValidationException
                error_messages = '; '.join(validation_result['errors'])
                raise ValidationException(f'User update validation failed: {error_messages}')

            # Apply updates
            user = self.crud.update_user(user_id, updates, updated_by_id)
            if not user:
                from ....exceptions import NotFoundException
                raise NotFoundException('User not found')

            return {
                'success': True,
                'user': self._serialize_user(user)
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    def suspend_user(
        self,
        user_id: str,
        reason: Optional[str] = None,
        suspended_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suspend user account
        """
        try:
            user = self.crud.update_user_status(
                user_id=user_id,
                status='suspended',
                reason=reason,
                updated_by_id=suspended_by_id
            )

            if not user:
                from ....exceptions import NotFoundException
                raise NotFoundException('User not found')

            return {
                'success': True,
                'user': self._serialize_user(user)
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    def reactivate_user(
        self,
        user_id: str,
        reactivated_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reactivate suspended user
        """
        try:
            # Clear expiration date and reactivate
            updates = {
                'is_active': True,
                'expired_date': None
            }

            user = self.crud.update_user(user_id, updates, reactivated_by_id)

            if not user:
                from ....exceptions import NotFoundException
                raise NotFoundException('User not found')

            return {
                'success': True,
                'user': self._serialize_user(user)
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    # ========== INVITATION MANAGEMENT ==========

    def send_invitation(
        self,
        invitation_data: Dict[str, Any],
        invited_by_id: str
    ) -> Dict[str, Any]:
        """
        Send user invitation
        """
        try:
            # Check if user already exists
            existing_user = self.crud.get_user_by_email(invitation_data['email'])
            if existing_user:
                from ....exceptions import ValidationException
                raise ValidationException('User with this email already exists')

            # Create invitation
            invitation = self.crud.create_invitation(invitation_data, invited_by_id)

            # Here you would send the actual email
            # For now, return the invitation details
            return {
                'success': True,
                'invitation': {
                    'id': invitation.id,
                    'email': invitation.email,
                    'token': invitation.invitation_token,
                    'expires_at': invitation.expires_at.isoformat(),
                    'invitation_url': f"/accept-invitation/{invitation.invitation_token}"
                }
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    def resend_invitation(self, user_id: str) -> Dict[str, Any]:
        """
        Resend invitation to user
        """
        # Implementation for resending invitations
        return {'success': True, 'message': 'Invitation resent'}

    def reset_password(
        self,
        user_id: str,
        reset_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reset user password and send reset link
        """
        try:
            user = self.crud.get_user_by_id(user_id)
            if not user or not user.email:
                from ....exceptions import NotFoundException
                raise NotFoundException('User not found or no email address')

            # Generate temporary password
            temp_password = self._generate_secure_password()

            # Update user password
            self.crud.update_user(
                user_id=user_id,
                updates={'password': temp_password},
                updated_by_id=reset_by_id
            )

            # Here you would send the password reset email
            return {
                'success': True,
                'message': 'Password reset email sent',
                'temp_password': temp_password  # In real app, don't return this
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    # ========== BULK OPERATIONS ==========

    def bulk_update_roles(
        self,
        user_ids: List[str],
        organization_role_id: Optional[str] = None,
        updated_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bulk update user organization roles
        """
        try:
            updated_users = []
            errors = []

            for user_id in user_ids:
                user = self.crud.assign_user_role(
                    user_id=user_id,
                    organization_role_id=organization_role_id,
                    assigned_by_id=updated_by_id
                )

                if user:
                    updated_users.append(self._serialize_user(user))
                else:
                    errors.append(f"Failed to update user {user_id}")

            return {
                'success': len(errors) == 0,
                'updated_count': len(updated_users),
                'errors': errors,
                'users': updated_users
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    def bulk_suspend_users(
        self,
        user_ids: List[str],
        reason: Optional[str] = None,
        suspended_by_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bulk suspend users
        """
        try:
            suspended_users = []
            errors = []

            for user_id in user_ids:
                result = self.suspend_user(user_id, reason, suspended_by_id)
                if result['success']:
                    suspended_users.append(result['user'])
                else:
                    errors.extend(result['errors'])

            return {
                'success': len(errors) == 0,
                'suspended_count': len(suspended_users),
                'errors': errors
            }

        except Exception as e:
            # Re-raise the exception to be handled by the caller
            raise e

    # ========== HELPER METHODS ==========

    def _validate_user_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user creation data"""
        errors = []

        # Required fields
        if not user_data.get('display_name'):
            errors.append('Display name is required')

        # Email validation
        if user_data.get('email'):
            if '@' not in user_data['email']:
                errors.append('Invalid email format')

            # Check if email already exists
            existing_user = self.crud.get_user_by_email(user_data['email'])
            if existing_user:
                errors.append('Email already exists')

        # Phone validation
        if user_data.get('phone'):
            # Basic phone validation
            phone = user_data['phone'].replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not phone.isdigit() or len(phone) < 10:
                errors.append('Invalid phone number format')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _validate_user_updates(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user updates"""
        errors = []

        # Check if user exists
        user = self.crud.get_user_by_id(user_id)
        if not user:
            errors.append('User not found')
            return {'valid': False, 'errors': errors}

        # Email uniqueness check
        if 'email' in updates and updates['email'] != user.email:
            existing_user = self.crud.get_user_by_email(updates['email'])
            if existing_user and existing_user.id != user_id:
                errors.append('Email already exists')

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def _generate_secure_password(self) -> str:
        """Generate secure random password"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        return password

    def _get_default_role_for_platform(self, platform: str) -> Optional[str]:
        """Get default role ID for platform"""
        # This would typically query the database for default roles
        # For now, return None to use system defaults
        return None

    def _serialize_user(self, user: UserLocation, include_sensitive: bool = False) -> Dict[str, Any]:
        """Serialize user for API response"""
        data = {
            'id': user.id,
            'is_user': user.is_user,
            'is_location': user.is_location,
            'display_name': user.display_name,
            'name_en': user.name_en,
            'name_th': user.name_th,
            'email': user.email,
            'phone': user.phone,
            'username': user.username,
            'platform': user.platform.value if user.platform else None,
            'company_name': user.company_name,
            'company_email': user.company_email,
            'company_phone': user.company_phone,
            'business_type': user.business_type,
            'business_industry': user.business_industry,
            'address': user.address,
            'postal_code': user.postal_code,
            'is_active': user.is_active,
            'created_date': user.created_date.isoformat() if user.created_date else None,
            'updated_date': user.updated_date.isoformat() if user.updated_date else None,
            'organization_id': user.organization_id,
            'parent_user_id': user.parent_user_id,
            'organization_level': user.organization_level,
        }

        # Add organization role information if available
        # Note: Platform roles have been removed, only organization roles remain

        if hasattr(user, 'organization_role') and user.organization_role:
            data['organization_role'] = {
                'id': user.organization_role.id,
                'name': user.organization_role.name,
                'description': user.organization_role.description
            }

        # Add location information if available
        if hasattr(user, 'country') and user.country:
            data['country'] = {
                'id': user.country.id,
                'name': user.country.name_en
            }

        if hasattr(user, 'province') and user.province:
            data['province'] = {
                'id': user.province.id,
                'name': user.province.name_en
            }

        return data

    def _serialize_activity(self, activity) -> Dict[str, Any]:
        """Serialize user activity"""
        return {
            'id': activity.id,
            'activity_type': activity.activity_type,
            'resource': activity.resource,
            'action': activity.action,
            'details': activity.details,
            'created_date': activity.created_date.isoformat(),
            'actor': {
                'id': activity.actor.id,
                'display_name': activity.actor.display_name
            } if activity.actor else None
        }

    def _get_user_aggregations(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get user statistics and aggregations"""
        # This would calculate various statistics
        return {
            'total_users': 0,
            'active_users': 0,
            'suspended_users': 0,
            'by_role': {},
            'by_platform': {}
        }

    def _get_user_organization_tree(self, user: UserLocation) -> Dict[str, Any]:
        """Get user's position in organization tree"""
        return {
            'level': user.organization_level,
            'path': user.organization_path,
            'parent': {
                'id': user.parent_user.id,
                'display_name': user.parent_user.display_name
            } if user.parent_user else None,
            'children_count': len(user.direct_children) if user.direct_children else 0
        }

    def _get_user_subscription_status(self, user_id: str) -> Dict[str, Any]:
        """Get user subscription status"""
        # This would check user's subscription status
        return {
            'has_active_subscription': True,
            'package_name': 'Business',
            'expires_at': None
        }

    def _validate_organization_inheritance(self, user_data: Dict[str, Any], created_by_id: Optional[str] = None):
        """
        Set organization_id from creator for sub-users.
        Frontend should not send organization_id - it will be automatically set from the creator.
        """
        # If no creator, no inheritance needed (standalone user creation/registration)
        if not created_by_id:
            return

        # Get creator's organization
        creator = self.crud.get_user_by_id(created_by_id)
        if not creator:
            raise ValueError(f"Creator user {created_by_id} not found")

        if not creator.organization_id:
            raise ValueError(f"Creator user {created_by_id} has no organization")

        # Remove any organization_id sent from frontend (it should not be sent)
        if 'organization_id' in user_data:
            del user_data['organization_id']

        # Automatically set organization_id from creator
        user_data['organization_id'] = creator.organization_id

        # If parent_user_id is provided, validate it's in the same organization
        if user_data.get('parent_user_id'):
            parent_user = self.crud.get_user_by_id(user_data['parent_user_id'])
            if not parent_user:
                raise ValueError(f"Parent user {user_data['parent_user_id']} not found")

            if parent_user.organization_id != creator.organization_id:
                raise ValueError(
                    f"Parent user organization_id ({parent_user.organization_id}) "
                    f"must match creator's organization_id ({creator.organization_id})"
                )

    def get_locations(self, organization_id: int, include_all: bool = False) -> List[Dict[str, Any]]:
        """
        Get user locations (is_location = True) for an organization

        Args:
            organization_id: The organization ID to filter by
            include_all: If True, return all locations. If False, filter by organization setup

        Returns all user_location columns except password, username, and email
        """
        # Get organization setup to determine which locations to include
        if not include_all:
            setup_location_ids = self._get_setup_location_ids(organization_id)
            if setup_location_ids is not None:
                locations = self.crud.get_user_locations(
                    organization_id=organization_id,
                    location_ids=setup_location_ids
                )
            else:
                # No setup found, return all locations
                locations = self.crud.get_user_locations(organization_id=organization_id)
        else:
            # Return all locations
            locations = self.crud.get_user_locations(organization_id=organization_id)

        # Serialize location data - include all columns except sensitive fields
        location_data = []
        for location in locations:
            location_dict = {
                # Base model fields
                'id': location.id,
                'is_active': location.is_active,
                'created_date': location.created_date.isoformat() if location.created_date else None,
                'updated_date': location.updated_date.isoformat() if location.updated_date else None,
                'deleted_date': location.deleted_date.isoformat() if location.deleted_date else None,

                # User flags
                'is_user': location.is_user,
                'is_location': location.is_location,

                # Basic Info (excluding email as requested)
                'name_th': location.name_th,
                'name_en': location.name_en,
                'display_name': location.display_name,

                # User-specific fields (excluding username, password, email as requested)
                'is_email_active': location.is_email_active,
                'email_notification': location.email_notification,
                'phone': location.phone,
                'facebook_id': location.facebook_id,
                'apple_id': location.apple_id,
                'google_id_gmail': location.google_id_gmail,

                # Platform and permissions
                'platform': location.platform.value if location.platform else None,
                'organization_role_id': location.organization_role_id,

                # Location and address information
                'coordinate': location.coordinate,
                'address': location.address,
                'postal_code': location.postal_code,
                'country_id': location.country_id,
                'province_id': location.province_id,
                'district_id': location.district_id,
                'subdistrict_id': location.subdistrict_id,

                # Business/Location specific fields
                'business_type': location.business_type,
                'business_industry': location.business_industry,
                'business_sub_industry': location.business_sub_industry,
                'company_name': location.company_name,
                'company_phone': location.company_phone,
                'company_email': location.company_email,
                'tax_id': location.tax_id,

                # Waste management specific fields
                'functions': location.functions,
                'type': location.type,
                'hub_type': location.hub_type,  # New field we added
                'population': location.population,
                'material': location.material,

                # Profile and documents
                'profile_image_url': location.profile_image_url,
                'national_id': location.national_id,
                'national_card_image': location.national_card_image,
                'business_registration_certificate': location.business_registration_certificate,

                # Relationships and hierarchy
                'organization_id': location.organization_id,
                'parent_location_id': location.parent_location_id,
                'created_by_id': location.created_by_id,
                'auditor_id': location.auditor_id,

                # Organizational tree structure
                'parent_user_id': location.parent_user_id,
                'organization_level': location.organization_level,
                'organization_path': location.organization_path,

                # Legacy and additional fields
                'sub_users': location.sub_users,
                'members': location.members,  # User assignments for this location
                'locale': location.locale,
                'nationality_id': location.nationality_id,
                'currency_id': location.currency_id,
                'phone_code_id': location.phone_code_id,
                'note': location.note,
                'expired_date': location.expired_date.isoformat() if location.expired_date else None,
                'footprint': float(location.footprint) if location.footprint else None,
            }
            location_data.append(location_dict)

        return location_data

    def _get_setup_location_ids(self, organization_id: int) -> List[int]:
        """
        Extract location IDs from organization setup (rootNodes and hubNode)
        Returns None if no setup is found
        """
        try:
            from ....models.subscriptions.organizations import OrganizationSetup

            # Get the latest organization setup
            setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            ).order_by(OrganizationSetup.created_date.desc()).first()

            if not setup:
                return None

            location_ids = set()

            # Extract IDs from root_nodes
            if setup.root_nodes:
                self._extract_node_ids(setup.root_nodes, location_ids)

            # Extract IDs from hub_node
            if setup.hub_node:
                if isinstance(setup.hub_node, dict):
                    # Extract ID from hub node itself if it has one
                    if 'nodeId' in setup.hub_node:
                        node_id = setup.hub_node['nodeId']
                        if isinstance(node_id, (int, str)) and str(node_id).isdigit():
                            location_ids.add(int(node_id))

                    # Extract IDs from hub children
                    if 'children' in setup.hub_node and isinstance(setup.hub_node['children'], list):
                        self._extract_node_ids(setup.hub_node['children'], location_ids)

            result = list(location_ids) if location_ids else None
            print(f"Organization {organization_id} setup filtering: found {len(location_ids) if location_ids else 0} location IDs: {result}")
            return result

        except Exception as e:
            # If there's an error, log it and return None to fall back to all locations
            print(f"Error extracting setup location IDs for organization {organization_id}: {str(e)}")
            return None

    def _extract_node_ids(self, nodes, location_ids: set):
        """
        Recursively extract nodeIds from a list of nodes
        """
        if not isinstance(nodes, list):
            return

        for node in nodes:
            if not isinstance(node, dict):
                continue

            # Extract nodeId if it exists and is numeric
            if 'nodeId' in node:
                node_id = node['nodeId']
                if isinstance(node_id, (int, str)) and str(node_id).isdigit():
                    location_ids.add(int(node_id))

            # Recursively extract from children
            if 'children' in node and isinstance(node['children'], list):
                self._extract_node_ids(node['children'], location_ids)