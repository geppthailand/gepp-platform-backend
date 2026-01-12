"""
Input Channel Service for managing QR code-based transaction input channels
"""

import uuid
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from GEPPPlatform.models.users.user_related import UserInputChannel
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.exceptions import NotFoundException, BadRequestException


class InputChannelService:
    """Service for managing user input channels (QR code-based input)"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def _generate_hash(self) -> str:
        """Generate a unique hash for the input channel"""
        return secrets.token_urlsafe(32)

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

        # Get user location for display name
        user_location = self.db.query(UserLocation).filter(
            UserLocation.id == channel.user_location_id
        ).first()

        result = self._serialize_channel(channel)

        # Add user display name
        if user_location:
            result['userDisplayName'] = user_location.display_name
            result['userId'] = str(user_location.id)

        # Validate subuser if provided
        if subuser:
            subuser_names = channel.subuser_names or []
            is_valid = subuser in subuser_names
            result['subUser'] = {
                'isValid': is_valid,
                'name': subuser if is_valid else None
            }

            # Get materials with details if valid subuser
            if is_valid:
                result['materials'] = self._get_materials_with_details(channel)
                result['locations'] = self._get_user_locations(channel)

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
        """Get accessible locations for the user"""
        user_location = self.db.query(UserLocation).filter(
            UserLocation.id == channel.user_location_id
        ).first()

        if not user_location:
            return []

        # Get all locations in the same organization that are actual locations
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

        # Validate sub-user
        subuser = data.get('subUser')
        subuser_names = channel.subuser_names or []
        if subuser not in subuser_names:
            return {'status': 'error', 'message': 'Invalid sub-user'}

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

            transaction = Transaction(
                transaction_method='qr_input',
                status=TransactionStatus.pending,
                organization_id=channel.organization_id,
                origin_id=int(data.get('origin')) if data.get('origin') else None,
                destination_ids=[r['destination_id'] for r in transaction_records_data if r.get('destination_id')],
                transaction_date=transaction_date,
                notes=f"QR Input by {subuser}. Tags: {data.get('tags', 'N/A')}",
                weight_kg=total_weight,
                total_amount=Decimal('0'),
                created_by_id=channel.user_location_id,
                is_active=True,
            )

            self.db.add(transaction)
            self.db.flush()

            # Create transaction records
            for record_data in transaction_records_data:
                record = TransactionRecord(
                    created_transaction_id=transaction.id,
                    material_id=record_data['material_id'],
                    destination_id=record_data.get('destination_id'),
                    weight_kg=record_data['weight_kg'],
                    quantity=record_data['quantity'],
                    status='pending',
                    is_active=True,
                )
                self.db.add(record)

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

        # Validate subuser
        subuser_names = channel.subuser_names or []
        if subuser not in subuser_names:
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

        # Validate subuser
        subuser_names = channel.subuser_names or []
        if subuser not in subuser_names:
            return {'success': False, 'message': 'Invalid subuser'}

        # Update preferences
        preferences = channel.subuser_material_preferences or {}
        preferences[subuser] = material_ids
        channel.subuser_material_preferences = preferences
        channel.updated_date = datetime.utcnow()

        self.db.commit()

        return {
            'success': True,
            'message': 'Preferences saved successfully',
            'material_ids': material_ids
        }
