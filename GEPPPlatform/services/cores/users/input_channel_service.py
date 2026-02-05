"""
Input Channel Service for managing QR code-based transaction input channels
Channels are organization-level, subusers are validated against organization members
"""

import uuid
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from GEPPPlatform.models.users.user_related import UserInputChannel
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.subscriptions.subscription_models import OrganizationRole
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class InputChannelService:
    """Service for managing organization-level input channels (QR code-based input)"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def _generate_hash(self) -> str:
        """Generate a unique hash for the input channel"""
        return secrets.token_urlsafe(32)

    def _validate_organization_member(
        self,
        organization_id: int,
        user_identifier: str,
        display_name: Optional[str] = None
    ) -> Optional[UserLocation]:
        """
        Validate if a user identifier belongs to an organization member.
        User identifier can be user_id, username, display_name, or name.
        If display_name is provided, also validates that it matches.
        Returns the UserLocation if valid, None otherwise.
        """
        # Build query conditions
        conditions = [
            UserLocation.organization_id == organization_id,
            UserLocation.is_active == True,
            UserLocation.deleted_date.is_(None),
        ]

        # Try to find user by various identifiers
        id_conditions = [
            UserLocation.username == user_identifier,
            UserLocation.display_name == user_identifier,
            UserLocation.name_en == user_identifier,
            UserLocation.name_th == user_identifier,
        ]

        # Also try numeric ID
        if user_identifier.isdigit():
            id_conditions.append(UserLocation.id == int(user_identifier))

        user = self.db.query(UserLocation).filter(
            and_(*conditions),
            or_(*id_conditions)
        ).first()

        # If display_name is provided, also validate it matches
        if user and display_name:
            user_display_name = user.display_name or ''
            if user_display_name.lower() != display_name.lower():
                return None

        return user

    # ==================== Organization-level Channel Methods ====================

    def get_organization_channels(self, organization_id: int) -> List[Dict[str, Any]]:
        """Get all input channels for an organization"""
        try:
            channels = self.db.query(UserInputChannel).filter(
                and_(
                    UserInputChannel.organization_id == organization_id,
                    UserInputChannel.is_active == True,
                    UserInputChannel.deleted_date.is_(None)
                )
            ).order_by(UserInputChannel.created_date.desc()).all()

            return [self._serialize_channel(ch) for ch in channels]
        except Exception as e:
            # Handle case where channel_name column doesn't exist yet (migration not run)
            error_str = str(e).lower()
            if 'channel_name' in error_str or 'undefined column' in error_str:
                # Rollback failed transaction and try with raw SQL without channel_name
                self.db.rollback()
                from sqlalchemy import text
                result = self.db.execute(text("""
                    SELECT id, user_location_id, organization_id, hash, channel_type,
                           form_type, sub_material_ids, sub_material_destination_ids,
                           subuser_names, enable_upload_image, required_tag, is_drop_off_point,
                           is_active, created_date, updated_date
                    FROM user_input_channels
                    WHERE organization_id = :org_id
                      AND is_active = true
                      AND deleted_date IS NULL
                    ORDER BY created_date DESC
                """), {'org_id': organization_id})

                channels = []
                for row in result:
                    channels.append({
                        'id': row[0],
                        'user_location_id': row[1],
                        'organization_id': row[2],
                        'channel_name': f'Channel #{row[0]}',  # Default name
                        'hash': row[3],
                        'channel_type': row[4],
                        'form_type': row[5],
                        'sub_material_ids': row[6] or [],
                        'sub_material_destination_ids': row[7] or [],
                        'subuser_names': row[8] or [],
                        'enable_upload_image': row[9],
                        'required_tag': row[10],
                        'is_drop_off_point': row[11],
                        'is_active': row[12],
                        'created_date': row[13].isoformat() if row[13] else None,
                        'updated_date': row[14].isoformat() if row[14] else None,
                        # Camel case aliases
                        'channelName': f'Channel #{row[0]}',
                        'formType': row[5],
                        'subMaterialIds': row[6] or [],
                        'subMaterialDestinationIds': row[7] or [],
                        'subUsers': row[8] or [],
                        'enableUploadImage': row[9],
                        'requiredTag': row[10],
                        'isDropOffPoint': row[11],
                    })
                return channels
            raise

    def get_channel_by_id(self, channel_id: int, organization_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific channel by ID"""
        try:
            channel = self.db.query(UserInputChannel).filter(
                and_(
                    UserInputChannel.id == channel_id,
                    UserInputChannel.organization_id == organization_id,
                    UserInputChannel.is_active == True,
                    UserInputChannel.deleted_date.is_(None)
                )
            ).first()

            if not channel:
                return None

            return self._serialize_channel(channel)
        except Exception as e:
            # Handle case where channel_name column doesn't exist yet
            error_str = str(e).lower()
            if 'channel_name' in error_str or 'undefined column' in error_str:
                self.db.rollback()
                from sqlalchemy import text
                result = self.db.execute(text("""
                    SELECT id, user_location_id, organization_id, hash, channel_type,
                           form_type, sub_material_ids, sub_material_destination_ids,
                           subuser_names, enable_upload_image, required_tag, is_drop_off_point,
                           is_active, created_date, updated_date
                    FROM user_input_channels
                    WHERE id = :channel_id
                      AND organization_id = :org_id
                      AND is_active = true
                      AND deleted_date IS NULL
                """), {'channel_id': channel_id, 'org_id': organization_id})

                row = result.fetchone()
                if not row:
                    return None

                return {
                    'id': row[0],
                    'user_location_id': row[1],
                    'organization_id': row[2],
                    'channel_name': f'Channel #{row[0]}',
                    'hash': row[3],
                    'channel_type': row[4],
                    'form_type': row[5],
                    'sub_material_ids': row[6] or [],
                    'sub_material_destination_ids': row[7] or [],
                    'subuser_names': row[8] or [],
                    'enable_upload_image': row[9],
                    'required_tag': row[10],
                    'is_drop_off_point': row[11],
                    'is_active': row[12],
                    'created_date': row[13].isoformat() if row[13] else None,
                    'updated_date': row[14].isoformat() if row[14] else None,
                    # Camel case aliases
                    'channelName': f'Channel #{row[0]}',
                    'formType': row[5],
                    'subMaterialIds': row[6] or [],
                    'subMaterialDestinationIds': row[7] or [],
                    'subUsers': row[8] or [],
                    'enableUploadImage': row[9],
                    'requiredTag': row[10],
                    'isDropOffPoint': row[11],
                }
            raise

    def create_organization_channel(
        self,
        organization_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new input channel for an organization (not tied to specific user)"""
        try:
            channel = UserInputChannel(
                organization_id=organization_id,
                user_location_id=None,  # Organization-level channel
                channel_name=data.get('channel_name', ''),
                hash=self._generate_hash(),
                channel_type='qr',
                form_type=data.get('form_type', 'daily'),
                enable_upload_image=data.get('enable_upload_image', False),
                required_tag=data.get('required_tag', False),
                is_drop_off_point=data.get('is_drop_off_point', False),
                sub_material_ids=[],
                sub_material_destination_ids=[],
                subuser_names=[],
                is_active=True
            )

            self.db.add(channel)
            self.db.commit()
            self.db.refresh(channel)

            return self._serialize_channel(channel)
        except Exception as e:
            # Handle case where channel_name column doesn't exist yet
            error_str = str(e).lower()
            if 'channel_name' in error_str or 'undefined column' in error_str:
                self.db.rollback()
                # Create without channel_name using raw SQL
                from sqlalchemy import text
                new_hash = self._generate_hash()
                result = self.db.execute(text("""
                    INSERT INTO user_input_channels (
                        organization_id, user_location_id, hash, channel_type,
                        form_type, enable_upload_image, required_tag, is_drop_off_point,
                        sub_material_ids, sub_material_destination_ids, subuser_names,
                        is_active, created_date
                    ) VALUES (
                        :org_id, NULL, :hash, 'qr',
                        :form_type, :enable_upload_image, :required_tag, :is_drop_off_point,
                        :sub_material_ids, :sub_material_destination_ids, :subuser_names,
                        true, NOW()
                    ) RETURNING id, created_date
                """), {
                    'org_id': organization_id,
                    'hash': new_hash,
                    'form_type': data.get('form_type', 'daily'),
                    'enable_upload_image': data.get('enable_upload_image', False),
                    'required_tag': data.get('required_tag', False),
                    'is_drop_off_point': data.get('is_drop_off_point', False),
                    'sub_material_ids': [],
                    'sub_material_destination_ids': [],
                    'subuser_names': [],
                })
                row = result.fetchone()
                self.db.commit()

                channel_id = row[0]
                created_date = row[1]
                channel_name = data.get('channel_name', '') or f'Channel #{channel_id}'

                return {
                    'id': channel_id,
                    'user_location_id': None,
                    'organization_id': organization_id,
                    'channel_name': channel_name,
                    'hash': new_hash,
                    'channel_type': 'qr',
                    'form_type': data.get('form_type', 'daily'),
                    'sub_material_ids': [],
                    'sub_material_destination_ids': [],
                    'subuser_names': [],
                    'enable_upload_image': data.get('enable_upload_image', False),
                    'required_tag': data.get('required_tag', False),
                    'is_drop_off_point': data.get('is_drop_off_point', False),
                    'is_active': True,
                    'created_date': created_date.isoformat() if created_date else None,
                    'updated_date': None,
                    # Camel case aliases
                    'channelName': channel_name,
                    'formType': data.get('form_type', 'daily'),
                    'subMaterialIds': [],
                    'subMaterialDestinationIds': [],
                    'subUsers': [],
                    'enableUploadImage': data.get('enable_upload_image', False),
                    'requiredTag': data.get('required_tag', False),
                    'isDropOffPoint': data.get('is_drop_off_point', False),
                }
            raise

    def update_organization_channel(
        self,
        channel_id: int,
        organization_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an organization channel by ID"""
        try:
            channel = self.db.query(UserInputChannel).filter(
                and_(
                    UserInputChannel.id == channel_id,
                    UserInputChannel.organization_id == organization_id,
                    UserInputChannel.is_active == True,
                    UserInputChannel.deleted_date.is_(None)
                )
            ).first()

            if not channel:
                raise NotFoundException('Input channel not found')

            # Update fields
            if 'channel_name' in data:
                channel.channel_name = data['channel_name']
            if 'form_type' in data:
                channel.form_type = data['form_type']
            if 'enable_upload_image' in data:
                channel.enable_upload_image = data['enable_upload_image']
            if 'required_tag' in data:
                channel.required_tag = data['required_tag']
            if 'is_drop_off_point' in data:
                channel.is_drop_off_point = data['is_drop_off_point']

            channel.updated_date = datetime.utcnow()

            self.db.commit()
            self.db.refresh(channel)

            return self._serialize_channel(channel)
        except Exception as e:
            # Handle case where channel_name column doesn't exist yet
            error_str = str(e).lower()
            if 'channel_name' in error_str or 'undefined column' in error_str:
                self.db.rollback()
                # Update without channel_name using raw SQL
                from sqlalchemy import text

                # First check if channel exists
                check_result = self.db.execute(text("""
                    SELECT id, hash, form_type, enable_upload_image, required_tag, is_drop_off_point
                    FROM user_input_channels
                    WHERE id = :channel_id
                      AND organization_id = :org_id
                      AND is_active = true
                      AND deleted_date IS NULL
                """), {'channel_id': channel_id, 'org_id': organization_id})
                existing = check_result.fetchone()

                if not existing:
                    raise NotFoundException('Input channel not found')

                # Build update query (without channel_name)
                update_parts = ["updated_date = NOW()"]
                params = {'channel_id': channel_id}

                if 'form_type' in data:
                    update_parts.append("form_type = :form_type")
                    params['form_type'] = data['form_type']
                if 'enable_upload_image' in data:
                    update_parts.append("enable_upload_image = :enable_upload_image")
                    params['enable_upload_image'] = data['enable_upload_image']
                if 'required_tag' in data:
                    update_parts.append("required_tag = :required_tag")
                    params['required_tag'] = data['required_tag']
                if 'is_drop_off_point' in data:
                    update_parts.append("is_drop_off_point = :is_drop_off_point")
                    params['is_drop_off_point'] = data['is_drop_off_point']

                self.db.execute(text(f"""
                    UPDATE user_input_channels
                    SET {', '.join(update_parts)}
                    WHERE id = :channel_id
                """), params)
                self.db.commit()

                # Fetch updated channel
                result = self.db.execute(text("""
                    SELECT id, user_location_id, organization_id, hash, channel_type,
                           form_type, sub_material_ids, sub_material_destination_ids,
                           subuser_names, enable_upload_image, required_tag, is_drop_off_point,
                           is_active, created_date, updated_date
                    FROM user_input_channels
                    WHERE id = :channel_id
                """), {'channel_id': channel_id})
                row = result.fetchone()

                channel_name = data.get('channel_name', '') or f'Channel #{row[0]}'

                return {
                    'id': row[0],
                    'user_location_id': row[1],
                    'organization_id': row[2],
                    'channel_name': channel_name,
                    'hash': row[3],
                    'channel_type': row[4],
                    'form_type': row[5],
                    'sub_material_ids': row[6] or [],
                    'sub_material_destination_ids': row[7] or [],
                    'subuser_names': row[8] or [],
                    'enable_upload_image': row[9],
                    'required_tag': row[10],
                    'is_drop_off_point': row[11],
                    'is_active': row[12],
                    'created_date': row[13].isoformat() if row[13] else None,
                    'updated_date': row[14].isoformat() if row[14] else None,
                    # Camel case aliases
                    'channelName': channel_name,
                    'formType': row[5],
                    'subMaterialIds': row[6] or [],
                    'subMaterialDestinationIds': row[7] or [],
                    'subUsers': row[8] or [],
                    'enableUploadImage': row[9],
                    'requiredTag': row[10],
                    'isDropOffPoint': row[11],
                }
            raise

    def delete_organization_channel(self, channel_id: int, organization_id: int) -> bool:
        """Soft delete an organization channel by ID"""
        try:
            channel = self.db.query(UserInputChannel).filter(
                and_(
                    UserInputChannel.id == channel_id,
                    UserInputChannel.organization_id == organization_id,
                    UserInputChannel.deleted_date.is_(None)
                )
            ).first()

            if not channel:
                return False

            channel.deleted_date = datetime.utcnow()
            channel.is_active = False

            self.db.commit()
            return True
        except Exception as e:
            # Handle case where channel_name column doesn't exist yet
            error_str = str(e).lower()
            if 'channel_name' in error_str or 'undefined column' in error_str:
                self.db.rollback()
                from sqlalchemy import text

                # Check if exists and delete using raw SQL
                result = self.db.execute(text("""
                    UPDATE user_input_channels
                    SET deleted_date = NOW(), is_active = false
                    WHERE id = :channel_id
                      AND organization_id = :org_id
                      AND deleted_date IS NULL
                    RETURNING id
                """), {'channel_id': channel_id, 'org_id': organization_id})

                row = result.fetchone()
                self.db.commit()
                return row is not None
            raise

    # ==================== Legacy User-based Methods (kept for backward compatibility) ====================

    def get_input_channel(self, user_location_id: int) -> Optional[Dict[str, Any]]:
        """Get input channel for a specific user location"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.user_location_id == user_location_id,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return None

        return self._serialize_channel(channel)

    def get_input_channel_by_hash(
        self,
        hash_value: str,
        subuser: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get input channel by hash (for QR code access)"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.hash == hash_value,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return None

        # Get user location for display name (if channel is tied to a specific user)
        user_location = None
        if channel.user_location_id:
            user_location = self.db.query(UserLocation).filter(
                UserLocation.id == channel.user_location_id
            ).first()

        result = self._serialize_channel(channel)

        # Add user display name if available
        if user_location:
            result['userDisplayName'] = user_location.display_name
            result['userId'] = str(user_location.id)

        # Validate subuser if provided - check organization membership
        if subuser:
            # First check if subuser is in legacy subuser_names list
            subuser_names = channel.subuser_names or []
            is_valid = subuser in subuser_names

            # If not in legacy list, check organization membership with display_name validation
            validated_user = None
            if not is_valid:
                validated_user = self._validate_organization_member(
                    channel.organization_id,
                    subuser,
                    display_name
                )
                is_valid = validated_user is not None
            else:
                # For legacy subusers, still need to find the user to check their role
                validated_user = self._validate_organization_member(
                    channel.organization_id,
                    subuser,
                    display_name
                )

            # Check if user has data_input role (or admin role) - required for access
            has_access_role = False
            if is_valid and validated_user:
                if validated_user.organization_role_id:
                    organization_role = self.db.query(OrganizationRole).filter(
                        OrganizationRole.id == validated_user.organization_role_id
                    ).first()
                    
                    if organization_role:
                        # Check if role key/name matches data_input or admin
                        role_key = (organization_role.key or '').lower()
                        role_name = (organization_role.name or '').lower()
                        has_access_role = (
                            role_key in ('data_input', 'admin') or
                            'data_input' in role_name or
                            'admin' in role_name
                        )
                
                # If user doesn't have required role, return access denied response
                if not has_access_role:
                    return {
                        'accessDenied': True,
                        'message': 'You do not have permission to access this input channel. Data input or admin role is required.',
                        'reason': 'missing_data_input_or_admin_role',
                        'subUser': {
                            'name': subuser,
                            'userId': str(validated_user.id) if validated_user else None,
                            'displayName': validated_user.display_name if validated_user else subuser
                        }
                    }
            elif is_valid and not validated_user:
                # Legacy subuser exists but we couldn't find the user - keep legacy invalid behavior
                is_valid = False

            # Get saved preferences for this subuser
            preferences = channel.subuser_material_preferences or {}
            saved_material_ids = preferences.get(subuser, [])

            result['subUser'] = {
                'isValid': is_valid,
                'name': subuser if is_valid else None,
                'userId': str(validated_user.id) if validated_user else None,
                'displayName': validated_user.display_name if validated_user else subuser,
                'savedMaterialIds': saved_material_ids if is_valid else []
            }

            # Get materials with details and locations if valid subuser
            if is_valid:
                result['materials'] = self._get_materials_with_details(channel)
                result['locations'] = self._get_user_locations(channel, validated_user)
                result['savedMaterialIds'] = saved_material_ids

        return result

    def create_input_channel(
        self,
        user_location_id: int,
        organization_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new input channel for a user"""
        # Check if channel already exists
        existing = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.user_location_id == user_location_id,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if existing:
            # Reactivate and update if exists
            existing.is_active = True
            existing.hash = self._generate_hash()
            existing.form_type = data.get('form_type', 'form')
            existing.sub_material_ids = data.get('sub_material_ids', [])
            existing.sub_material_destination_ids = data.get('sub_material_destination_ids', [])
            existing.subuser_names = data.get('subuser_names', [])
            existing.enable_upload_image = data.get('enable_upload_image', False)
            existing.required_tag = data.get('required_tag', False)
            existing.is_drop_off_point = data.get('is_drop_off_point', False)
            existing.updated_date = datetime.utcnow()

            self.db.commit()
            return self._serialize_channel(existing)

        # Create new channel
        channel = UserInputChannel(
            user_location_id=user_location_id,
            organization_id=organization_id,
            hash=self._generate_hash(),
            channel_type='qr',
            form_type=data.get('form_type', 'form'),
            sub_material_ids=data.get('sub_material_ids', []),
            sub_material_destination_ids=data.get('sub_material_destination_ids', []),
            subuser_names=data.get('subuser_names', []),
            enable_upload_image=data.get('enable_upload_image', False),
            required_tag=data.get('required_tag', False),
            is_drop_off_point=data.get('is_drop_off_point', False),
            is_active=True
        )

        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)

        return self._serialize_channel(channel)

    def update_input_channel(
        self,
        user_location_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing input channel"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.user_location_id == user_location_id,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            raise NotFoundException('Input channel not found')

        # Update fields
        if 'form_type' in data:
            channel.form_type = data['form_type']
        if 'sub_material_ids' in data:
            channel.sub_material_ids = data['sub_material_ids']
        if 'sub_material_destination_ids' in data:
            channel.sub_material_destination_ids = data['sub_material_destination_ids']
        if 'subuser_names' in data:
            channel.subuser_names = data['subuser_names']
        if 'enable_upload_image' in data:
            channel.enable_upload_image = data['enable_upload_image']
        if 'required_tag' in data:
            channel.required_tag = data['required_tag']
        if 'is_drop_off_point' in data:
            channel.is_drop_off_point = data['is_drop_off_point']

        channel.updated_date = datetime.utcnow()

        self.db.commit()
        self.db.refresh(channel)

        return self._serialize_channel(channel)

    def regenerate_hash(self, user_location_id: int) -> Dict[str, Any]:
        """Generate a new hash for an existing input channel"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.user_location_id == user_location_id,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            raise NotFoundException('Input channel not found')

        channel.hash = self._generate_hash()
        channel.updated_date = datetime.utcnow()
        channel.is_active = True

        # Reset configuration on new QR generation
        channel.sub_material_ids = []
        channel.sub_material_destination_ids = []
        channel.subuser_names = []
        channel.form_type = 'form'

        self.db.commit()
        self.db.refresh(channel)

        return self._serialize_channel(channel)

    def delete_input_channel(self, user_location_id: int) -> bool:
        """Soft delete an input channel"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.user_location_id == user_location_id,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return False

        channel.deleted_date = datetime.utcnow()
        channel.is_active = False

        self.db.commit()
        return True

    def _serialize_channel(self, channel: UserInputChannel) -> Dict[str, Any]:
        """Serialize a channel to a dictionary"""
        return {
            'id': channel.id,
            'user_location_id': channel.user_location_id,
            'organization_id': channel.organization_id,
            'channel_name': channel.channel_name or '',
            'hash': channel.hash,
            'channel_type': channel.channel_type,
            'form_type': channel.form_type,
            'sub_material_ids': channel.sub_material_ids or [],
            'sub_material_destination_ids': channel.sub_material_destination_ids or [],
            'subuser_names': channel.subuser_names or [],
            'enable_upload_image': channel.enable_upload_image,
            'required_tag': channel.required_tag,
            'is_drop_off_point': channel.is_drop_off_point,
            'is_active': channel.is_active,
            'created_date': channel.created_date.isoformat() if channel.created_date else None,
            'updated_date': channel.updated_date.isoformat() if channel.updated_date else None,
            # Camel case aliases for frontend compatibility
            'channelName': channel.channel_name or '',
            'formType': channel.form_type,
            'subMaterialIds': channel.sub_material_ids or [],
            'subMaterialDestinationIds': channel.sub_material_destination_ids or [],
            'subUsers': channel.subuser_names or [],
            'enableUploadImage': channel.enable_upload_image,
            'requiredTag': channel.required_tag,
            'isDropOffPoint': channel.is_drop_off_point,
        }

    def _get_materials_with_details(self, channel: UserInputChannel) -> List[Dict[str, Any]]:
        """Get materials with details for the channel"""
        from GEPPPlatform.models.cores.references import Material

        material_ids = channel.sub_material_ids or []
        if not material_ids:
            return []

        materials = self.db.query(Material).filter(
            Material.id.in_(material_ids)
        ).all()

        result = []
        for mat in materials:
            result.append({
                'id': mat.id,
                'name': {
                    'nameTH': mat.name_th if hasattr(mat, 'name_th') else mat.name,
                    'nameEN': mat.name_en if hasattr(mat, 'name_en') else mat.name,
                },
                'unitNameTH': mat.unit if hasattr(mat, 'unit') else 'กก.',
                'images': [{'imageURL': mat.image_url}] if hasattr(mat, 'image_url') and mat.image_url else []
            })

        return result

    def _build_location_paths(
        self,
        organization_id: int,
        location_data: List[Dict[str, Any]],
        org_setup
    ) -> Dict[int, str]:
        """
        Build path traces for all locations from their branch root to the location.
        Returns a dict mapping location_id to path string (e.g., "Branch A, Building 1, Floor 2")

        Uses organization_setup.root_nodes tree structure to trace the hierarchy.
        """
        try:
            if not org_setup or not org_setup.root_nodes:
                return {}

            # Fetch ALL locations in the organization to get their names
            all_locations = self.db.query(UserLocation).filter(
                and_(
                    UserLocation.organization_id == organization_id,
                    UserLocation.is_active == True,
                    UserLocation.deleted_date.is_(None)
                )
            ).all()

            # Create name lookup map
            location_names = {
                loc.id: loc.display_name or loc.name_en or loc.name_th or f"Location {loc.id}"
                for loc in all_locations
            }

            # Build parent map from tree structure
            # key: nodeId, value: parentId
            parent_map: Dict[int, int] = {}

            def build_parent_map(nodes: List[Dict], parent_id: Optional[int] = None):
                """Recursively build parent map from tree structure"""
                for node in nodes:
                    node_id = node.get('nodeId')
                    if node_id is not None:
                        node_id = int(node_id) if isinstance(node_id, str) else node_id
                        if parent_id is not None:
                            parent_map[node_id] = parent_id
                        # Process children
                        children = node.get('children', [])
                        if children:
                            build_parent_map(children, node_id)

            # Build the parent map from root_nodes
            root_nodes = org_setup.root_nodes
            if isinstance(root_nodes, list):
                build_parent_map(root_nodes, None)

            # Build paths for each location
            location_paths = {}

            def get_ancestors(loc_id: int, visited: set = None) -> List[str]:
                """Get list of ancestor names from root to parent (not including current node)"""
                if visited is None:
                    visited = set()

                # Prevent infinite loops
                if loc_id in visited:
                    return []
                visited.add(loc_id)

                parent_id = parent_map.get(loc_id)
                if parent_id is None:
                    # This is a root node, return empty (no ancestors)
                    return []

                # Get parent's ancestors recursively, then add parent
                parent_ancestors = get_ancestors(parent_id, visited)
                parent_name = location_names.get(parent_id, f"Location {parent_id}")
                return parent_ancestors + [parent_name]

            # Build paths only for the locations in location_data
            for loc in location_data:
                loc_id = int(loc['id'])
                ancestors = get_ancestors(loc_id)

                if ancestors:
                    location_paths[loc_id] = ', '.join(ancestors)
                else:
                    # Root node - no ancestors to show
                    location_paths[loc_id] = ''

            return location_paths

        except Exception as e:
            print(f"Error building location paths for organization {organization_id}: {str(e)}")
            return {}

    def _extract_node_ids_from_tree(self, nodes: List[Dict]) -> List[int]:
        """
        Recursively extract all nodeIds from a tree structure.
        The tree has format: [{"nodeId": 123, "children": [{"nodeId": 456, ...}]}]
        """
        node_ids = []
        for node in nodes:
            if 'nodeId' in node:
                node_ids.append(int(node['nodeId']))
            if 'children' in node and isinstance(node['children'], list):
                node_ids.extend(self._extract_node_ids_from_tree(node['children']))
        return node_ids

    def _get_user_locations(
        self,
        channel: UserInputChannel,
        validated_user: Optional[UserLocation] = None
    ) -> List[Dict[str, Any]]:
        """
        Get accessible locations for the channel's organization.
        Only returns locations from root_nodes in organization_setup (not hub_node).
        Also includes tags for each location where the user is a member.
        """
        from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
        from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup

        # Get the latest active organization setup
        org_setup = self.db.query(OrganizationSetup).filter(
            and_(
                OrganizationSetup.organization_id == channel.organization_id,
                OrganizationSetup.is_active == True,
                OrganizationSetup.deleted_date.is_(None)
            )
        ).order_by(OrganizationSetup.created_date.desc()).first()

        if not org_setup or not org_setup.root_nodes:
            # Fallback: no organization setup, return empty list
            return []

        # Extract all nodeIds from root_nodes (recursively including children)
        root_nodes = org_setup.root_nodes
        if not isinstance(root_nodes, list):
            root_nodes = [root_nodes] if root_nodes else []

        location_ids = self._extract_node_ids_from_tree(root_nodes)

        if not location_ids:
            return []

        # Query user_locations for those specific IDs
        locations = self.db.query(UserLocation).filter(
            and_(
                UserLocation.id.in_(location_ids),
                UserLocation.organization_id == channel.organization_id,
                UserLocation.is_location == True,
                UserLocation.is_active == True,
                UserLocation.deleted_date.is_(None)
            )
        ).all()

        # Build a map of location ID -> display_name for path building
        all_location_ids_for_path = self._extract_node_ids_from_tree(root_nodes)
        all_locations_for_path = self.db.query(UserLocation).filter(
            UserLocation.id.in_(all_location_ids_for_path)
        ).all()
        location_name_map = {loc.id: loc.display_name for loc in all_locations_for_path}
        
        # Build a map of nodeId -> path (list of parent node IDs with names)
        # This will help us show the hierarchical path for each location
        path_map = {}
        
        def build_path_map(nodes: List[Dict], parent_path: List[Dict] = None):
            """Recursively build path map for all nodes"""
            if parent_path is None:
                parent_path = []
            for node in nodes:
                node_id = node.get('nodeId')
                if node_id:
                    node_id_int = int(node_id)
                    # Store the path to this node (excluding itself)
                    path_map[node_id_int] = list(parent_path)
                    # Build path for children, including current node info
                    # Use display_name from database, fallback to node.get('name') or node.get('display_name')
                    node_name = location_name_map.get(node_id_int) or node.get('name') or node.get('display_name') or ''
                    child_path = parent_path + [{'nodeId': node_id_int, 'name': node_name, 'type': node.get('type', '')}]
                    if 'children' in node and isinstance(node['children'], list):
                        build_path_map(node['children'], child_path)
        
        build_path_map(root_nodes)

        result = []
        for loc in locations:
            functions = []
            if loc.functions:
                if isinstance(loc.functions, list):
                    functions = loc.functions
                elif isinstance(loc.functions, str):
                    functions = [loc.functions]

            # Get tags for this location using the new many-to-many structure
            # Tags are stored in location.tags JSONB array AND tag.user_locations array
            location_tag_ids = loc.tags or []
            location_tags = []

            if location_tag_ids:
                # Handle both int and string IDs
                tag_ids_int = [int(tid) if isinstance(tid, str) else tid for tid in location_tag_ids]
                tags = self.db.query(UserLocationTag).filter(
                    and_(
                        UserLocationTag.id.in_(tag_ids_int),
                        UserLocationTag.organization_id == channel.organization_id,
                        UserLocationTag.is_active == True,
                        UserLocationTag.deleted_date.is_(None)
                    )
                ).all()

                # Filter tags to only those where the validated_user is a member (if user exists)
                for tag in tags:
                    # If user validation is required, check if user is in tag members
                    if validated_user:
                        tag_members = tag.members or []
                        # Check both integer and string representations since members may be stored as strings
                        user_id_int = validated_user.id
                        user_id_str = str(validated_user.id)
                        if user_id_int in tag_members or user_id_str in tag_members:
                            location_tags.append({
                                'id': str(tag.id),
                                'name': tag.name
                            })
                    else:
                        # If no user validation, include all tags
                        location_tags.append({
                            'id': str(tag.id),
                            'name': tag.name
                        })

            # Get tenants for this location (same pattern as tags)
            location_tenant_ids = loc.tenants or []
            location_tenants = []
            if location_tenant_ids:
                tenant_ids_int = [int(tid) if isinstance(tid, str) else tid for tid in location_tenant_ids]
                tenants = self.db.query(UserTenant).filter(
                    and_(
                        UserTenant.id.in_(tenant_ids_int),
                        UserTenant.organization_id == channel.organization_id,
                        UserTenant.is_active == True,
                        UserTenant.deleted_date.is_(None)
                    )
                ).all()
                for tenant in tenants:
                    if validated_user:
                        tenant_members = tenant.members or []
                        user_id_int = validated_user.id
                        user_id_str = str(validated_user.id)
                        if user_id_int in tenant_members or user_id_str in tenant_members:
                            location_tenants.append({
                                'id': str(tenant.id),
                                'name': tenant.name
                            })
                    else:
                        location_tenants.append({
                            'id': str(tenant.id),
                            'name': tenant.name
                        })

            # Build path string from parent nodes
            loc_path = path_map.get(loc.id, [])
            path_names = [p.get('name', '') for p in loc_path if p.get('name')]
            path_str = ', '.join(path_names) if path_names else ''
            
            # Get location type from the tree node info
            location_type = loc.location_type if hasattr(loc, 'location_type') and loc.location_type else ''

            result.append({
                'id': str(loc.id),
                'name_th': loc.display_name,
                'name_en': loc.display_name,
                'functions': functions,
                'tags': location_tags,
                'tenants': location_tenants,
                'path': path_str,
                'location_type': location_type,
            })

        return result

    def submit_transaction_by_hash(
        self,
        hash_value: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Submit a transaction from QR code input

        Args:
            hash_value: The input channel hash
            data: Transaction data containing:
                - subUser: Sub-user identifier
                - origin: Origin location ID
                - matData: Array of weights matching material order
                - tag_id: Location tag ID (optional)
                - tenant_id: Tenant ID (optional)
                - consent: User consent boolean
                - transactionDate: Transaction date
                - b64image: Array of base64 images (optional)
        """
        from GEPPPlatform.models.transactions.transactions import Transaction, TransactionStatus
        from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
        from decimal import Decimal
        import base64
        import uuid as uuid_module

        # Get channel
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.hash == hash_value,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return {'status': 'error', 'message': 'Input channel not found'}

        # Validate sub-user - check organization membership or legacy subuser_names
        subuser = data.get('subUser')
        subuser_names = channel.subuser_names or []
        validated_user = None

        # First check legacy subuser_names list
        is_valid = subuser in subuser_names

        # If not in legacy list, check organization membership
        if not is_valid:
            validated_user = self._validate_organization_member(channel.organization_id, subuser)
            is_valid = validated_user is not None

        if not is_valid:
            return {'status': 'error', 'message': 'Invalid sub-user. User must be a member of the organization.'}

        # Get the creator user_location_id - use validated user if available
        creator_user_location_id = None
        if validated_user:
            creator_user_location_id = validated_user.id
        elif channel.user_location_id:
            # Fallback for legacy subuser_names - try to find by name
            legacy_user = self._validate_organization_member(channel.organization_id, subuser)
            if legacy_user:
                creator_user_location_id = legacy_user.id
            else:
                creator_user_location_id = channel.user_location_id

        # Validate consent
        if not data.get('consent'):
            return {'status': 'error', 'message': 'User consent required'}

        # Get material and weight data
        mat_data = data.get('matData', [])
        material_ids = [m['id'] for m in mat_data if m.get('id')]
        destination_ids = channel.sub_material_destination_ids or []

        # Filter out zero/empty weights
        transaction_records_data = []
        total_weight = Decimal('0')

        # Fetch materials early to calculate quantity
        from GEPPPlatform.models.cores.references import Material
        materials = (
            self.db.query(Material)
            .filter(Material.id.in_(material_ids))
            .all()
        )
        material_map = {m.id: m for m in materials}

        for i, mat in enumerate(mat_data):
            material_id = mat.get('id')
            if not material_id:
                continue
            
            # Try multiple field names for weight (quantity, weight, weight_kg)
            weight = mat.get('quantity') or mat.get('weight') or mat.get('weight_kg')
            
            # Validate weight exists and is positive
            if weight is None:
                continue
            try:
                weight_float = float(weight)
                if weight_float <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            weight_decimal = Decimal(str(weight))
            total_weight += weight_decimal

            # Get destination for this material (if destinations are configured)
            dest_id = None
            if destination_ids and i < len(destination_ids):
                dest_id = destination_ids[i]

            # Calculate quantity from weight_kg / unit_weight
            material = material_map.get(material_id)
            quantity = Decimal('1')  # Default to 1 if material not found
            if material and material.unit_weight and material.unit_weight > 0:
                quantity = weight_decimal / Decimal(str(material.unit_weight))

            transaction_records_data.append({
                'material_id': material_id,
                'destination_id': dest_id,
                'weight_kg': weight_decimal,
                'quantity': quantity,
            })

        if not transaction_records_data:
            return {'status': 'error', 'message': 'No valid material weights provided'}

        # Fetch material details for all materials in the transaction
        from GEPPPlatform.models.cores.references import Material
        material_ids_list = [r['material_id'] for r in transaction_records_data]
        materials = self.db.query(Material).filter(Material.id.in_(material_ids_list)).all()
        material_map = {m.id: m for m in materials}

        # Create transaction
        try:
            # Parse transaction date
            transaction_date = datetime.utcnow()
            if data.get('transactionDate'):
                try:
                    date_str = data['transactionDate']
                    if isinstance(date_str, str):
                        if 'Z' in date_str:
                            date_str = date_str.replace('Z', '+00:00')
                        transaction_date = datetime.fromisoformat(date_str)
                except Exception:
                    pass

            # Build notes with subuser info
            subuser_display = subuser
            if validated_user and validated_user.display_name:
                subuser_display = f"{validated_user.display_name} ({subuser})"

            # Parse location_tag_id from tag_id or legacy tags field
            location_tag_id = None
            tag_id_value = data.get('tag_id') or data.get('tags')
            if tag_id_value is not None and tag_id_value != '':
                try:
                    location_tag_id = int(tag_id_value)
                except (ValueError, TypeError):
                    pass

            # Parse tenant_id from request body
            tenant_id = None
            tenant_id_value = data.get('tenant_id')
            if tenant_id_value is not None and tenant_id_value != '':
                try:
                    tenant_id = int(tenant_id_value)
                except (ValueError, TypeError):
                    pass

            transaction = Transaction(
                transaction_method='qr_input',
                status=TransactionStatus.pending,
                organization_id=channel.organization_id,
                origin_id=int(data.get('origin')) if data.get('origin') else None,
                destination_ids=[],  # No destination for QR input transactions
                transaction_date=transaction_date,
                notes=f"QR Input by {subuser_display}. Location Tag: {data.get('tag_id') or data.get('tags') or 'N/A'}. Tenant: {data.get('tenant_id') or 'N/A'}",
                weight_kg=total_weight,
                total_amount=Decimal('0'),
                created_by_id=creator_user_location_id,
                location_tag_id=location_tag_id,
                tenant_id=tenant_id,
                is_active=True,
            )

            self.db.add(transaction)
            self.db.flush()

            # Create transaction records (no destination for QR input)
            transaction_record_ids = []
            for record_data in transaction_records_data:
                material_id = record_data['material_id']
                material = material_map.get(material_id)

                # Get material details or use defaults
                main_material_id = material.main_material_id if material and material.main_material_id else 1
                category_id = material.category_id if material and material.category_id else 1
                unit = material.unit_name_en if material and material.unit_name_en else 'kg'

                record = TransactionRecord(
                    created_transaction_id=transaction.id,
                    transaction_type='manual_input',  # QR input is treated as manual input
                    material_id=material_id,
                    main_material_id=main_material_id,
                    category_id=category_id,
                    unit=unit,
                    origin_weight_kg=record_data['weight_kg'],
                    origin_quantity=record_data['quantity'],
                    origin_price_per_unit=Decimal('0'),
                    total_amount=Decimal('0'),
                    traceability=[],
                    tags=[],
                    status='pending',
                    is_active=True,
                    created_by_id=creator_user_location_id,  # Use validated subuser's user_location_id
                    transaction_date=transaction_date,
                )
                self.db.add(record)
                self.db.flush()
                transaction_record_ids.append(record.id)

            # Update transaction with record IDs
            transaction.transaction_records = transaction_record_ids

            # Handle image uploads
            images = data.get('b64image', [])
            if images and channel.enable_upload_image:
                try:
                    from GEPPPlatform.services.file_upload_service import S3FileUploadService
                    s3_service = S3FileUploadService()
                    uploaded_urls = []

                    for i, b64_image in enumerate(images):
                        if b64_image:
                            # Remove data URL prefix if present
                            if ',' in b64_image:
                                b64_image = b64_image.split(',')[1]

                            # Decode and upload
                            image_data = base64.b64decode(b64_image)
                            file_name = f"qr_input_{transaction.id}_{i}_{uuid_module.uuid4().hex[:8]}.jpg"

                            url = s3_service.upload_base64_image(
                                image_data=image_data,
                                file_name=file_name,
                                folder='qr-transactions'
                            )
                            if url:
                                uploaded_urls.append(url)

                    if uploaded_urls:
                        transaction.images = uploaded_urls

                except Exception as e:
                    # Log but don't fail transaction
                    import logging
                    logging.error(f"Failed to upload images: {str(e)}")

            self.db.commit()

            return {
                'status': 'success',
                'message': 'Transaction created successfully',
                'transaction_id': transaction.id,
            }

        except Exception as e:
            self.db.rollback()
            import traceback
            return {
                'status': 'error',
                'message': f'Failed to create transaction: {str(e)}',
                'traceback': traceback.format_exc()
            }

    def get_subuser_preferences(
        self,
        hash_value: str,
        subuser: str
    ) -> Dict[str, Any]:
        """Get material preferences for a specific subuser"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.hash == hash_value,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return {'material_ids': []}

        # Validate subuser - check organization membership or legacy list
        subuser_names = channel.subuser_names or []
        is_valid = subuser in subuser_names
        if not is_valid:
            validated_user = self._validate_organization_member(channel.organization_id, subuser)
            is_valid = validated_user is not None

        if not is_valid:
            return {'material_ids': []}

        # Get preferences from the JSON field
        preferences = channel.subuser_material_preferences or {}
        material_ids = preferences.get(subuser, [])

        return {'material_ids': material_ids}

    def save_subuser_preferences(
        self,
        hash_value: str,
        subuser: str,
        material_ids: List[int]
    ) -> Dict[str, Any]:
        """Save material preferences for a specific subuser"""
        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.hash == hash_value,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return {'success': False, 'message': 'Input channel not found'}

        # Validate subuser - check organization membership or legacy list
        subuser_names = channel.subuser_names or []
        is_valid = subuser in subuser_names
        if not is_valid:
            validated_user = self._validate_organization_member(channel.organization_id, subuser)
            is_valid = validated_user is not None

        if not is_valid:
            return {'success': False, 'message': 'Invalid subuser. User must be a member of the organization.'}

        # Update preferences
        # Need to use flag_modified for SQLAlchemy to detect JSON column changes
        from sqlalchemy.orm.attributes import flag_modified

        preferences = dict(channel.subuser_material_preferences or {})  # Create a new dict copy
        preferences[subuser] = material_ids
        channel.subuser_material_preferences = preferences
        channel.updated_date = datetime.utcnow()

        # Explicitly mark the JSON column as modified
        flag_modified(channel, 'subuser_material_preferences')

        self.db.commit()

        return {
            'success': True,
            'message': 'Preferences saved successfully',
            'material_ids': material_ids
        }

    def get_all_materials_for_picker(
        self,
        hash_value: str,
        subuser: str
    ) -> Dict[str, Any]:
        """
        Get all materials, categories, and main_materials for the material picker.
        This returns materials in the format expected by the frontend picker component.
        """
        from GEPPPlatform.models.cores.references import Material, MaterialCategory, MainMaterial

        channel = self.db.query(UserInputChannel).filter(
            and_(
                UserInputChannel.hash == hash_value,
                UserInputChannel.is_active == True,
                UserInputChannel.deleted_date.is_(None)
            )
        ).first()

        if not channel:
            return {'success': False, 'message': 'Input channel not found', 'materials': [], 'categories': [], 'main_materials': []}

        # Validate subuser
        subuser_names = channel.subuser_names or []
        is_valid = subuser in subuser_names
        if not is_valid:
            validated_user = self._validate_organization_member(channel.organization_id, subuser)
            is_valid = validated_user is not None

        if not is_valid:
            return {'success': False, 'message': 'Invalid subuser', 'materials': [], 'categories': [], 'main_materials': []}

        # Get all active materials (global + organization-specific)
        materials = self.db.query(Material).filter(
            and_(
                Material.is_active == True,
                Material.deleted_date.is_(None),
                or_(
                    Material.is_global == True,
                    Material.organization_id == channel.organization_id
                )
            )
        ).all()

        # Get all active categories
        categories = self.db.query(MaterialCategory).filter(
            and_(
                MaterialCategory.is_active == True,
                MaterialCategory.deleted_date.is_(None)
            )
        ).order_by(MaterialCategory.name_th).all()

        # Get all active main materials
        main_materials = self.db.query(MainMaterial).filter(
            and_(
                MainMaterial.is_active == True,
                MainMaterial.deleted_date.is_(None)
            )
        ).order_by(MainMaterial.display_order).all()

        # Serialize materials
        materials_data = []
        for mat in materials:
            materials_data.append({
                'id': mat.id,
                'name_th': mat.name_th,
                'name_en': mat.name_en,
                'unit_name_th': mat.unit_name_th,
                'unit_name_en': mat.unit_name_en,
                'color': mat.color,
                'category_id': mat.category_id,
                'main_material_id': mat.main_material_id,
            })

        # Serialize categories
        categories_data = []
        for cat in categories:
            categories_data.append({
                'id': cat.id,
                'name_th': cat.name_th,
                'name_en': cat.name_en,
                'color': cat.color,
            })

        # Serialize main materials
        main_materials_data = []
        for mm in main_materials:
            main_materials_data.append({
                'id': mm.id,
                'name_th': mm.name_th,
                'name_en': mm.name_en,
                'color': mm.color,
            })

        return {
            'success': True,
            'materials': materials_data,
            'categories': categories_data,
            'main_materials': main_materials_data
        }
