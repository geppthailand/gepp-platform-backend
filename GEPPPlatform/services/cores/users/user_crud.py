"""
User CRUD operations with advanced features
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import and_, or_, func, text, desc, asc, literal
from datetime import datetime, timedelta
import uuid
import hashlib
import bcrypt

from ....models.users.user_location import UserLocation
from ....models.users.user_related import (
    UserBank, UserSubscription, UserActivity, UserDevice,
    UserPreference, UserInvitation, UserRoleEnum
)
from ....models.cores.roles import SystemRole
from ....models.subscriptions.subscription_models import OrganizationRole

class UserCRUD:
    """
    Comprehensive CRUD operations for user management
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== CREATE OPERATIONS ==========

    def create_user(
        self,
        user_data: Dict[str, Any],
        created_by_id: Optional[str] = None,
        send_invitation: bool = False
    ) -> UserLocation:
        """
        Create a new user with full setup
        """
        # Prepare user data
        user = UserLocation(
            is_user=True,
            is_location=user_data.get('is_location', False),

            # Basic info
            name_th=user_data.get('name_th'),
            name_en=user_data.get('name_en'),
            display_name=user_data.get('display_name', user_data.get('name_en', '')),
            first_name=user_data.get('first_name'),
            last_name=user_data.get('last_name'),

            # Contact
            email=user_data.get('email'),
            phone=user_data.get('phone'),
            username=user_data.get('username'),

            # Platform and roles
            platform=user_data.get('platform', 'GEPP_BUSINESS_WEB'),
            organization_role_id=user_data.get('organization_role_id') or self._get_organization_role_id(user_data.get('role')),  # For business roles (admin, data_input, etc.)

            # Business info
            company_name=user_data.get('company_name'),
            company_phone=user_data.get('company_phone'),
            company_email=user_data.get('company_email'),
            tax_id=user_data.get('tax_id'),
            business_type=user_data.get('business_type'),
            business_industry=user_data.get('business_industry'),
            business_sub_industry=user_data.get('business_sub_industry'),

            # Location
            address=user_data.get('address'),
            postal_code=user_data.get('postal_code'),
            coordinate=user_data.get('coordinate'),
            country_id=user_data.get('country_id', 212),  # Default Thailand
            province_id=user_data.get('province_id'),
            district_id=user_data.get('district_id'),
            subdistrict_id=user_data.get('subdistrict_id'),

            # Organization
            organization_id=self._get_organization_id_for_user(user_data, created_by_id),
            parent_user_id=user_data.get('parent_user_id'),
            created_by_id=created_by_id,

            # Additional
            locale=user_data.get('locale', 'TH'),
            note=user_data.get('note'),
            functions=user_data.get('functions'),
        )

        # Set password if provided
        if user_data.get('password'):
            user.password = self._hash_password(user_data['password'])

        # Set organizational hierarchy
        if user.parent_user_id:
            parent = self.get_user_by_id(user.parent_user_id)
            if parent:
                user.organization_level = parent.organization_level + 1
                user.organization_path = f"{parent.organization_path}{parent.id}/"
        else:
            user.organization_level = 0
            user.organization_path = "/"

        # Organization ID is already set by _get_organization_id_for_user above

        # Set parent user to creator if not specified (for sub-users)
        if not user.parent_user_id and created_by_id:
            user.parent_user_id = created_by_id

        self.db.add(user)
        self.db.flush()  # Get the ID

        # Update organization path with actual ID
        if not user.parent_user_id:
            user.organization_path = f"/{user.id}/"

        # Create default preferences
        preferences = UserPreference(
            user_location_id=user.id,
            language=user_data.get('language', 'th'),
            timezone=user_data.get('timezone', 'Asia/Bangkok'),
            theme=user_data.get('theme', 'light'),
        )
        self.db.add(preferences)

        # Set organization account type based on user data
        self._set_organization_account_type(user, user_data)

        # Update organization_role_id if it wasn't set and we have organization_id
        if not user.organization_role_id and user.organization_id and user_data.get('role'):
            user.organization_role_id = self._get_organization_role_id(
                user_data.get('role'),
                user.organization_id
            )

        # Send invitation if requested
        if send_invitation and user.email:
            self._create_invitation(user, created_by_id)

        # Log activity
        if created_by_id:
            self._log_activity(
                user_id=user.id,
                actor_id=created_by_id,
                activity_type='user_created',
                details={'method': 'invitation' if send_invitation else 'direct'}
            )

        self.db.commit()
        return user

    def create_user_bank(self, user_id: str, bank_data: Dict[str, Any]) -> UserBank:
        """Create bank account information for user"""
        user_bank = UserBank(
            user_location_id=user_id,
            organization_id=bank_data.get('organization_id'),
            bank_id=bank_data.get('bank_id'),
            account_number=bank_data.get('account_number'),
            account_name=bank_data.get('account_name'),
            account_type=bank_data.get('account_type', 'savings'),
            branch_name=bank_data.get('branch_name'),
            branch_code=bank_data.get('branch_code'),
            is_primary=bank_data.get('is_primary', False),
            note=bank_data.get('note')
        )

        # If this is set as primary, unset other primary accounts
        if user_bank.is_primary:
            self.db.query(UserBank).filter(
                UserBank.user_location_id == user_id,
                UserBank.is_primary == True
            ).update({'is_primary': False})

        self.db.add(user_bank)
        self.db.commit()
        return user_bank

    def create_user_subscription(
        self,
        user_id: str,
        subscription_data: Dict[str, Any]
    ) -> UserSubscription:
        """Create user subscription"""
        subscription = UserSubscription(
            user_location_id=user_id,
            organization_id=subscription_data['organization_id'],
            subscription_package_id=subscription_data['subscription_package_id'],
            start_date=subscription_data.get('start_date', datetime.now().date()),
            end_date=subscription_data.get('end_date'),
            billing_cycle=subscription_data.get('billing_cycle', 'monthly'),
            auto_renew=subscription_data.get('auto_renew', True),
            usage_data=subscription_data.get('usage_data', {})
        )

        self.db.add(subscription)
        self.db.commit()
        return subscription

    # ========== READ OPERATIONS ==========

    def get_users(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_date',
        sort_order: str = 'desc',
        include_relations: bool = True
    ) -> Tuple[List[UserLocation], int]:
        """
        Get users with advanced filtering and pagination
        """
        query = self.db.query(UserLocation).filter(
            UserLocation.is_user == True
        )

        # Exclude organization owners from user lists
        # Join with Organization table to check if user is an owner
        from GEPPPlatform.models.subscriptions.organizations import Organization
        query = query.outerjoin(Organization, Organization.owner_id == UserLocation.id).filter(
            Organization.owner_id.is_(None)
        )

        # Apply relationships loading
        if include_relations:
            query = query.options(
                joinedload(UserLocation.organization_role),
                joinedload(UserLocation.country),
                joinedload(UserLocation.province),
                selectinload(UserLocation.direct_children)
            )

        # Apply filters
        if filters:
            query = self._apply_filters(query, filters)

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting
        if hasattr(UserLocation, sort_by):
            if sort_order.lower() == 'desc':
                query = query.order_by(desc(getattr(UserLocation, sort_by)))
            else:
                query = query.order_by(asc(getattr(UserLocation, sort_by)))

        # Apply pagination
        if page_size > 0:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        users = query.all()
        return users, total_count

    def get_user_by_id(self, user_id: str, include_relations: bool = True) -> Optional[UserLocation]:
        """Get user by ID with optional relations"""
        query = self.db.query(UserLocation).filter(UserLocation.id == user_id)

        if include_relations:
            query = query.options(
                joinedload(UserLocation.organization_role),
                joinedload(UserLocation.country),
                joinedload(UserLocation.province),
                selectinload(UserLocation.direct_children),
                selectinload(UserLocation.subusers)
            )

        return query.first()

    def get_user_by_email(self, email: str) -> Optional[UserLocation]:
        """Get user by email (only active, non-deleted users)"""
        return self.db.query(UserLocation).filter(
            and_(
                UserLocation.email == email,
                UserLocation.is_user == True,
                UserLocation.is_active == True,
                UserLocation.deleted_date.is_(None)
            )
        ).first()

    def get_user_activities(
        self,
        user_id: str,
        limit: int = 50,
        activity_types: Optional[List[str]] = None
    ) -> List[UserActivity]:
        """Get user activities with optional filtering"""
        query = self.db.query(UserActivity).filter(
            UserActivity.user_location_id == user_id
        ).options(
            joinedload(UserActivity.actor)
        ).order_by(desc(UserActivity.created_date))

        if activity_types:
            query = query.filter(UserActivity.activity_type.in_(activity_types))

        return query.limit(limit).all()

    def get_organization_users(
        self,
        organization_id: str,
        include_hierarchy: bool = True
    ) -> List[UserLocation]:
        """Get all users in an organization (excluding organization owners)"""
        # Exclude organization owners from organization user lists
        from GEPPPlatform.models.subscriptions.organizations import Organization

        query = self.db.query(UserLocation).filter(
            and_(
                UserLocation.organization_id == organization_id,
                UserLocation.is_user == True
            )
        ).outerjoin(Organization, Organization.owner_id == UserLocation.id).filter(
            Organization.owner_id.is_(None)
        )

        if include_hierarchy:
            query = query.options(
                joinedload(UserLocation.parent_user),
                selectinload(UserLocation.direct_children)
            )

        return query.all()

    # ========== UPDATE OPERATIONS ==========

    def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
        updated_by_id: Optional[str] = None
    ) -> Optional[UserLocation]:
        """Update user with activity logging"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # Track changes for logging
        changes = {}
        for key, new_value in updates.items():
            if hasattr(user, key):
                old_value = getattr(user, key)
                if old_value != new_value:
                    changes[key] = {'old': old_value, 'new': new_value}
                    setattr(user, key, new_value)

        # Handle password updates
        if 'password' in updates:
            user.password = self._hash_password(updates['password'])
            changes['password'] = {'old': '[HIDDEN]', 'new': '[UPDATED]'}

        # Update organizational hierarchy if parent changed
        if 'parent_user_id' in updates:
            self._update_user_hierarchy(user)

        user.updated_date = datetime.now()

        # Log changes
        if changes and updated_by_id:
            self._log_activity(
                user_id=user_id,
                actor_id=updated_by_id,
                activity_type='user_updated',
                details={'changes': changes}
            )

        self.db.commit()
        return user

    def update_user_status(
        self,
        user_id: str,
        status: str,
        reason: Optional[str] = None,
        updated_by_id: Optional[str] = None
    ) -> Optional[UserLocation]:
        """Update user status (active/suspended/etc.)"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # Map status to is_active
        user.is_active = status == 'active'

        if status == 'suspended':
            user.expired_date = datetime.now()

        # Log status change
        if updated_by_id:
            self._log_activity(
                user_id=user_id,
                actor_id=updated_by_id,
                activity_type='status_changed',
                details={'status': status, 'reason': reason}
            )

        self.db.commit()
        return user

    def assign_user_role(
        self,
        user_id: str,
        organization_role_id: Optional[str] = None,
        assigned_by_id: Optional[str] = None
    ) -> Optional[UserLocation]:
        """Assign organization role to user"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        changes = {}
        if organization_role_id is not None:
            old_organization_role = user.organization_role_id
            user.organization_role_id = organization_role_id
            changes['organization_role_id'] = {'old': old_organization_role, 'new': organization_role_id}

        # Log role changes
        if changes and assigned_by_id:
            self._log_activity(
                user_id=user_id,
                actor_id=assigned_by_id,
                activity_type='role_assigned',
                details={'changes': changes}
            )

        self.db.commit()
        return user

    # ========== DELETE OPERATIONS ==========

    def delete_user(
        self,
        user_id: str,
        soft_delete: bool = True,
        deleted_by_id: Optional[str] = None
    ) -> bool:
        """Delete user (soft or hard delete)"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        if soft_delete:
            user.is_active = False
            user.deleted_date = datetime.now()

            # Log deletion
            if deleted_by_id:
                self._log_activity(
                    user_id=user_id,
                    actor_id=deleted_by_id,
                    activity_type='user_deleted',
                    details={'type': 'soft_delete'}
                )
        else:
            # Hard delete - remove all related data
            # Delete related records first
            self.db.query(UserBank).filter(UserBank.user_location_id == user_id).delete()
            self.db.query(UserSubscription).filter(UserSubscription.user_location_id == user_id).delete()
            self.db.query(UserActivity).filter(UserActivity.user_location_id == user_id).delete()
            self.db.query(UserDevice).filter(UserDevice.user_location_id == user_id).delete()
            self.db.query(UserPreference).filter(UserPreference.user_location_id == user_id).delete()

            self.db.delete(user)

        self.db.commit()
        return True

    # ========== INVITATION OPERATIONS ==========

    def create_invitation(
        self,
        invitation_data: Dict[str, Any],
        invited_by_id: str
    ) -> UserInvitation:
        """Create user invitation"""
        invitation = UserInvitation(
            email=invitation_data['email'],
            phone=invitation_data.get('phone'),
            invited_by_id=invited_by_id,
            organization_id=invitation_data['organization_id'],
            intended_role=invitation_data.get('intended_role'),
            intended_organization_role=invitation_data.get('intended_organization_role'),
            intended_platform=invitation_data.get('intended_platform'),
            invitation_token=self._generate_invitation_token(),
            expires_at=datetime.now() + timedelta(days=7),
            custom_message=invitation_data.get('custom_message'),
            invitation_data=invitation_data.get('additional_data', {})
        )

        self.db.add(invitation)
        self.db.commit()
        return invitation

    def accept_invitation(self, token: str, user_data: Dict[str, Any]) -> Tuple[bool, Optional[UserLocation]]:
        """Accept invitation and create user"""
        invitation = self.db.query(UserInvitation).filter(
            and_(
                UserInvitation.invitation_token == token,
                UserInvitation.status == 'pending',
                UserInvitation.expires_at > datetime.now()
            )
        ).first()

        if not invitation:
            return False, None

        # Create user with invitation data
        user_data.update({
            'email': invitation.email,
            'phone': invitation.phone or user_data.get('phone'),
            'organization_id': invitation.organization_id,
            'role_id': invitation.intended_role,
            'organization_role_id': invitation.intended_organization_role,
            'platform': invitation.intended_platform,
        })

        user = self.create_user(user_data, created_by_id=invitation.invited_by_id)

        # Update invitation
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.now()
        invitation.created_user_id = user.id

        self.db.commit()
        return True, user

    # ========== HELPER METHODS ==========

    def _apply_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to user query"""
        if filters.get('query'):
            search_term = f"%{filters['query']}%"
            query = query.filter(
                or_(
                    UserLocation.display_name.ilike(search_term),
                    UserLocation.name_en.ilike(search_term),
                    UserLocation.name_th.ilike(search_term),
                    UserLocation.email.ilike(search_term),
                    UserLocation.company_name.ilike(search_term)
                )
            )

        if filters.get('roles'):
            # Map 'roles' filter to organization_role_id since we removed platform roles
            query = query.filter(UserLocation.organization_role_id.in_(filters['roles']))

        if filters.get('organization_roles'):
            query = query.filter(UserLocation.organization_role_id.in_(filters['organization_roles']))

        if filters.get('platforms'):
            query = query.filter(UserLocation.platform.in_(filters['platforms']))

        if filters.get('organization_ids'):
            query = query.filter(UserLocation.organization_id.in_(filters['organization_ids']))

        if filters.get('status'):
            if filters['status'] == 'active':
                query = query.filter(UserLocation.is_active == True)
            elif filters['status'] == 'inactive':
                query = query.filter(UserLocation.is_active == False)

        if filters.get('created_from'):
            query = query.filter(UserLocation.created_date >= filters['created_from'])

        if filters.get('created_to'):
            query = query.filter(UserLocation.created_date <= filters['created_to'])

        return query

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _generate_invitation_token(self) -> str:
        """Generate unique invitation token"""
        return str(uuid.uuid4())

    def _update_user_hierarchy(self, user: UserLocation):
        """Update user's organizational hierarchy"""
        if user.parent_user_id:
            parent = self.get_user_by_id(user.parent_user_id)
            if parent:
                user.organization_level = parent.organization_level + 1
                user.organization_path = f"{parent.organization_path}{parent.id}/"
        else:
            user.organization_level = 0
            user.organization_path = f"/{user.id}/"

    def _log_activity(
        self,
        user_id: str,
        actor_id: str,
        activity_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log user activity"""
        activity = UserActivity(
            user_location_id=user_id,
            actor_id=actor_id,
            activity_type=activity_type,
            resource='user',
            action=activity_type,
            details=details or {}
        )
        self.db.add(activity)

    def _create_invitation(self, user: UserLocation, invited_by_id: Optional[str]):
        """Create invitation record for user"""
        if invited_by_id and user.email:
            invitation = UserInvitation(
                email=user.email,
                phone=user.phone,
                invited_by_id=invited_by_id,
                organization_id=user.organization_id,
                intended_role=user.organization_role_id,
                intended_organization_role=user.organization_role_id,
                intended_platform=user.platform,
                invitation_token=self._generate_invitation_token(),
                expires_at=datetime.now() + timedelta(days=7),
                created_user_id=user.id,
                status='sent'
            )
            self.db.add(invitation)

    def _set_organization_account_type(self, user: UserLocation, user_data: Dict[str, Any]):
        """Set account type at organization level based on user data"""
        if not user.organization_id:
            return

        # Import here to avoid circular imports
        from ....models.subscriptions.organizations import OrganizationInfo

        # Get the organization info
        org_info = self.db.query(OrganizationInfo).filter(
            OrganizationInfo.id == user.organization_id
        ).first()

        if not org_info:
            return

        # Determine account type based on user data
        # If user has business-related fields, set as business, otherwise personal
        has_business_info = any([
            user_data.get('company_name'),
            user_data.get('tax_id'),
            user_data.get('business_type'),
            user_data.get('business_industry'),
            user.company_name,
            user.tax_id,
            user.business_type,
            user.business_industry
        ])

        account_type = 'business' if has_business_info else 'personal'

        # Update organization account type if not already set or different
        if not org_info.account_type or org_info.account_type != account_type:
            org_info.account_type = account_type

    def _get_organization_role_id(self, role_key: str, organization_id: Optional[int] = None) -> Optional[int]:
        """Get organization role ID from role key (admin, data_input, etc.)"""
        if not role_key:
            return None

        # Import here to avoid circular imports
        from ....models.subscriptions.subscription_models import OrganizationRole

        # If organization_id is provided, scope to that organization
        query = self.db.query(OrganizationRole).filter(
            OrganizationRole.key == role_key,
            OrganizationRole.is_active == True
        )

        if organization_id:
            query = query.filter(OrganizationRole.organization_id == organization_id)

        role = query.first()
        return role.id if role else None

    def _get_organization_id_for_user(self, user_data: Dict[str, Any], created_by_id: Optional[str] = None) -> Optional[str]:
        """
        Determine the organization_id for a new user.
        Sub-users must inherit the creator's organization_id.
        """
        # If organization_id is explicitly provided, use it (service layer has already validated it)
        if user_data.get('organization_id'):
            return user_data.get('organization_id')

        # If user has a parent_user_id, inherit that user's organization
        if user_data.get('parent_user_id'):
            parent_user = self.get_user_by_id(user_data['parent_user_id'])
            if parent_user and parent_user.organization_id:
                return parent_user.organization_id

        # If user is being created by someone (sub-user), inherit creator's organization
        if created_by_id:
            creator = self.get_user_by_id(created_by_id)
            if creator and creator.organization_id:
                return creator.organization_id

        # No organization_id could be determined
        return None

    def get_user_locations(self, organization_id: Optional[int] = None, location_ids: Optional[List[int]] = None) -> List[UserLocation]:
        """
        Get user locations (is_location = True) for an organization

        Args:
            organization_id: Filter by organization ID
            location_ids: If provided, only return locations with these IDs
        """
        query = self.db.query(UserLocation).filter(
            and_(
                UserLocation.is_location == True,
                UserLocation.is_active == True
            )
        )

        # Filter by organization if provided
        if organization_id:
            query = query.filter(UserLocation.organization_id == organization_id)

        # Filter by specific location IDs if provided
        if location_ids:
            query = query.filter(UserLocation.id.in_(location_ids))

        # Order by created_date descending
        query = query.order_by(desc(UserLocation.created_date))

        return query.all()

    def get_locations_by_member(
        self,
        member_user_id: int,
        role: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> List[UserLocation]:
        """
        Get locations where the given user is present in members JSONB array.

        Uses JSONB containment (@>) to match elements. Handles user_id stored as number or string.
        """
        query = self.db.query(UserLocation).filter(
            and_(
                UserLocation.is_location == True,
                UserLocation.is_active == True
            )
        )

        # Scope to organization if provided
        if organization_id:
            query = query.filter(UserLocation.organization_id == organization_id)

        # Ensure members is not null
        query = query.filter(UserLocation.members.isnot(None))

        # Build JSONB patterns using positional key/value pairs
        # Numeric user_id variant
        if role:
            pattern_num = func.jsonb_build_array(
                func.jsonb_build_object('user_id', int(member_user_id), 'role', role)
            )
            pattern_str = func.jsonb_build_array(
                func.jsonb_build_object('user_id', str(member_user_id), 'role', role)
            )
        else:
            pattern_num = func.jsonb_build_array(
                func.jsonb_build_object('user_id', int(member_user_id))
            )
            pattern_str = func.jsonb_build_array(
                func.jsonb_build_object('user_id', str(member_user_id))
            )

        cond_num = UserLocation.members.op('@>')(pattern_num)
        cond_str = UserLocation.members.op('@>')(pattern_str)
        query = query.filter(or_(cond_num, cond_str))

        # Order by newest first for consistency
        query = query.order_by(desc(UserLocation.created_date))
        return query.all()