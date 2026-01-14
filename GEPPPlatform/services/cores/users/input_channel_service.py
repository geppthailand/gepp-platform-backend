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
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class InputChannelService:
    """Service for managing organization-level input channels (QR code-based input)"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def _generate_hash(self) -> str:
        """Generate a unique hash for the input channel"""
        return secrets.token_urlsafe(32)

    def _validate_organization_member(self, organization_id: int, user_identifier: str) -> Optional[UserLocation]:
        """
        Validate if a user identifier belongs to an organization member.
        User identifier can be user_id, username, display_name, or name.
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

    def get_input_channel_by_hash(self, hash_value: str, subuser: Optional[str] = None) -> Optional[Dict[str, Any]]:
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

            # If not in legacy list, check organization membership
            validated_user = None
            if not is_valid:
                validated_user = self._validate_organization_member(channel.organization_id, subuser)
                is_valid = validated_user is not None

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
                result['locations'] = self._get_user_locations(channel)
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

    def _get_user_locations(self, channel: UserInputChannel) -> List[Dict[str, Any]]:
        """Get accessible locations for the channel's organization"""
        # Get all locations in the organization that are actual locations
        # For organization-level channels, we don't need user_location_id
        locations = self.db.query(UserLocation).filter(
            and_(
                UserLocation.organization_id == channel.organization_id,
                UserLocation.is_location == True,
                UserLocation.is_active == True,
                UserLocation.deleted_date.is_(None)
            )
        ).all()

        result = []
        for loc in locations:
            functions = []
            if loc.functions:
                if isinstance(loc.functions, list):
                    functions = loc.functions
                elif isinstance(loc.functions, str):
                    functions = [loc.functions]

            result.append({
                'id': str(loc.id),
                'name_th': loc.display_name,
                'name_en': loc.display_name,
                'functions': functions,
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
                - tags: Optional location tag ID
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
        destination_ids = channel.sub_material_destination_ids or []

        # Filter out zero/empty weights
        transaction_records_data = []
        total_weight = Decimal('0')

        # Handle both new format (array of {id, weight} objects) and legacy format (array of weights)
        if mat_data and isinstance(mat_data[0], dict):
            # New format: array of {id, weight} objects from dynamic material selection
            for item in mat_data:
                material_id = item.get('id')
                weight = item.get('weight', 0)
                if material_id and weight and float(weight) > 0:
                    weight_decimal = Decimal(str(weight))
                    total_weight += weight_decimal

                    transaction_records_data.append({
                        'material_id': material_id,
                        'destination_id': None,  # Dynamic selection doesn't have preset destinations
                        'weight_kg': weight_decimal,
                        'quantity': 1,
                    })
        else:
            # Legacy format: array of weights matching channel.sub_material_ids order
            material_ids = channel.sub_material_ids or []
            if len(mat_data) != len(material_ids):
                return {'status': 'error', 'message': 'Material data mismatch'}

            for i, weight in enumerate(mat_data):
                if weight and float(weight) > 0:
                    weight_decimal = Decimal(str(weight))
                    total_weight += weight_decimal

                    # Get destination for this material (if destinations are configured)
                    dest_id = None
                    if destination_ids and i < len(destination_ids):
                        dest_id = destination_ids[i]

                    transaction_records_data.append({
                        'material_id': material_ids[i],
                        'destination_id': dest_id,
                        'weight_kg': weight_decimal,
                        'quantity': 1,
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

            transaction = Transaction(
                transaction_method='qr_input',
                status=TransactionStatus.pending,
                organization_id=channel.organization_id,
                origin_id=int(data.get('origin')) if data.get('origin') else None,
                destination_ids=[],  # No destination for QR input transactions
                transaction_date=transaction_date,
                notes=f"QR Input by {subuser_display}. Location Tag: {data.get('tags', 'N/A')}",
                weight_kg=total_weight,
                total_amount=Decimal('0'),
                created_by_id=creator_user_location_id,  # Use validated subuser's user_location_id
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
