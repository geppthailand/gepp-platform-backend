"""
ESG LINE Service — LINE webhook handler for group-based ESG data collection
Supports both group messages and 1:1 messages (backward compatible)
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import hashlib
import hmac
import base64
import json
import logging
import os
import secrets
import string
from datetime import datetime

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.line_messages import EsgLineMessage
from ...models.esg.platform_binding import EsgExternalPlatformBinding
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from .esg_document_service import EsgDocumentService

logger = logging.getLogger(__name__)


class EsgLineService:
    """Handles LINE webhook events for ESG data collection from groups and 1:1"""

    def __init__(self, db: Session):
        self.db = db

    def handle_webhook(self, body: str, signature: str) -> Dict[str, Any]:
        """Process LINE webhook events"""
        try:
            payload = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            return {'success': False, 'message': 'Invalid JSON payload'}

        events = payload.get('events', [])
        if not events:
            return {'success': True, 'message': 'No events to process'}

        destination = payload.get('destination', '')

        results = []
        for event in events:
            result = self._process_event(event, body, signature, destination)
            results.append(result)

        return {
            'success': True,
            'message': f'Processed {len(results)} events',
            'results': results
        }

    def _process_event(self, event: Dict[str, Any], raw_body: str, signature: str, destination: str) -> Dict[str, Any]:
        """Process a single LINE event - handles both group and 1:1"""
        event_type = event.get('type')
        source = event.get('source', {})
        source_type = source.get('type', '')

        # Handle bot join event (invited to group)
        if event_type == 'join' and source_type == 'group':
            return self._handle_group_join(event, raw_body, signature, destination)

        # Handle messages
        if event_type != 'message':
            return {'status': 'skipped', 'reason': f'Event type {event_type} not supported'}

        # Route based on source type
        if source_type == 'group':
            return self._process_group_message(event, raw_body, signature, destination)
        else:
            # 1:1 message (backward compatible)
            return self._process_direct_message(event, raw_body, signature, destination)

    # ==========================================
    # GROUP HANDLING
    # ==========================================

    def _handle_group_join(self, event: Dict[str, Any], raw_body: str, signature: str, destination: str) -> Dict[str, Any]:
        """Handle bot being invited to a LINE group"""
        source = event.get('source', {})
        group_id = source.get('groupId', '')
        reply_token = event.get('replyToken', '')

        if not group_id:
            return {'status': 'error', 'reason': 'No group ID in join event'}

        # Find binding by destination (LINE bot user ID / channel)
        binding = self._find_binding_by_destination(destination)
        if not binding:
            logger.warning(f"No binding found for destination: {destination}")
            return {'status': 'error', 'reason': 'No platform binding found'}

        # Verify signature
        channel_secret = (binding.auth_json or {}).get('channel_secret', '')
        if not self._verify_signature(raw_body, signature, channel_secret):
            return {'status': 'error', 'reason': 'Signature verification failed'}

        # Generate pairing code
        pairing_code = self._generate_pairing_code()

        # Get group name from LINE API
        channel_token = (binding.auth_json or {}).get('channel_token', '')
        group_name = self._get_group_name(group_id, channel_token) or f'Group {group_id[:8]}'

        # Store pending group in authorized_groups
        groups = list(binding.authorized_groups or [])

        # Check if already exists
        existing = next((g for g in groups if g.get('group_id') == group_id), None)
        if existing:
            existing['pairing_code'] = pairing_code
            existing['status'] = 'pending'
            existing['group_name'] = group_name
        else:
            groups.append({
                'group_id': group_id,
                'group_name': group_name,
                'pairing_code': pairing_code,
                'status': 'pending',
                'joined_at': datetime.utcnow().isoformat(),
            })

        binding.authorized_groups = groups
        self.db.flush()

        # Send pairing code to group
        reply_msg = (
            f'GEPP ESG Bot\n\n'
            f'Pairing Code: {pairing_code}\n\n'
            f'Please enter this code in GEPP ESG Settings to connect this group to your organization.'
        )
        self._send_reply(channel_token, reply_token, reply_msg)

        return {'status': 'success', 'type': 'group_join', 'group_id': group_id, 'pairing_code': pairing_code}

    def _process_group_message(self, event: Dict[str, Any], raw_body: str, signature: str, destination: str) -> Dict[str, Any]:
        """Process a message from a LINE group"""
        source = event.get('source', {})
        group_id = source.get('groupId', '')
        user_id = source.get('userId', '')
        message = event.get('message', {})
        message_type = message.get('type', '')
        reply_token = event.get('replyToken', '')

        # Find binding with this group paired
        binding = self._find_binding_by_group(group_id)
        if not binding:
            return {'status': 'skipped', 'reason': 'Group not paired'}

        # Verify signature
        channel_secret = (binding.auth_json or {}).get('channel_secret', '')
        if not self._verify_signature(raw_body, signature, channel_secret):
            return {'status': 'error', 'reason': 'Signature verification failed'}

        channel_token = (binding.auth_json or {}).get('channel_token', '')

        # Get group name from binding
        group_name = ''
        for g in (binding.authorized_groups or []):
            if g.get('group_id') == group_id:
                group_name = g.get('group_name', '')
                break

        # Create LINE message record
        line_msg = EsgLineMessage(
            organization_id=binding.organization_id,
            line_message_id=message.get('id', ''),
            line_user_id=user_id,
            line_reply_token=reply_token,
            message_type=message_type,
            processing_status='received',
        )
        self.db.add(line_msg)
        self.db.flush()

        # Determine input type
        input_type = self._map_message_type(message_type)

        # Create extraction record
        extraction = EsgOrganizationDataExtraction(
            organization_id=binding.organization_id,
            channel='line',
            type=input_type,
            source_group_id=group_id,
            source_group_name=group_name,
            source_user_id=user_id,
            source_message_id=message.get('id', ''),
            processing_status='pending',
        )

        if message_type == 'text':
            extraction.raw_content = message.get('text', '')
        elif message_type in ('image', 'file'):
            try:
                file_record = self._download_and_store(message, binding, group_id)
                if file_record:
                    extraction.file_id = file_record.get('id')
            except Exception as e:
                logger.error(f"Failed to download/store file: {e}")
                extraction.processing_status = 'failed'
                extraction.error_message = str(e)

        self.db.add(extraction)
        self.db.flush()

        # Trigger cascade extraction
        if extraction.processing_status != 'failed':
            try:
                from .esg_extraction_service import EsgExtractionService
                extract_svc = EsgExtractionService(self.db)
                extract_svc.process_extraction(extraction.id)
            except Exception as e:
                logger.error(f"Cascade extraction failed: {e}")
                extraction.processing_status = 'failed'
                extraction.error_message = str(e)
                self.db.flush()

        # Only reply if bot is @mentioned
        is_mentioned = self._is_bot_mentioned(event, binding)
        if is_mentioned and extraction.processing_status == 'completed':
            reply = self._format_extraction_reply(extraction)
            self._send_reply(channel_token, reply_token, reply)
            line_msg.reply_sent = True
            line_msg.reply_message = reply

        line_msg.processing_status = extraction.processing_status
        line_msg.document_id = extraction.file_id
        self.db.flush()

        return {'status': 'success', 'extraction_id': extraction.id}

    # ==========================================
    # 1:1 MESSAGE HANDLING (backward compatible)
    # ==========================================

    def _process_direct_message(self, event: Dict[str, Any], raw_body: str, signature: str, destination: str) -> Dict[str, Any]:
        """Handle direct 1:1 messages (backward compatible)"""
        message = event.get('message', {})
        message_type = message.get('type')
        reply_token = event.get('replyToken')
        source = event.get('source', {})
        user_id = source.get('userId', '')

        # Find organization by LINE channel
        org_settings = self._find_org_by_line(destination, user_id)
        if not org_settings:
            logger.warning(f"No organization found for LINE destination: {destination}")
            return {'status': 'error', 'reason': 'Organization not found'}

        # Verify signature
        if not self._verify_signature(raw_body, signature, org_settings.line_channel_secret):
            return {'status': 'error', 'reason': 'Signature verification failed'}

        # Create LINE message record
        line_msg = EsgLineMessage(
            organization_id=org_settings.organization_id,
            line_message_id=message.get('id', ''),
            line_user_id=user_id,
            line_reply_token=reply_token,
            message_type=message_type,
            processing_status='received',
        )
        self.db.add(line_msg)
        self.db.flush()

        if message_type == 'image':
            return self._process_image_message(line_msg, org_settings, message)
        elif message_type == 'text':
            return self._process_text_message(line_msg, event, org_settings)
        else:
            line_msg.processing_status = 'completed'
            self.db.flush()
            return {'status': 'skipped', 'reason': f'Message type {message_type} not supported'}

    def _process_image_message(self, line_msg: EsgLineMessage, org_settings: EsgOrganizationSettings, message: Dict) -> Dict[str, Any]:
        """Download image from LINE, upload to S3, trigger classification"""
        try:
            line_msg.processing_status = 'downloading'
            self.db.flush()

            message_id = message.get('id')
            image_data = self._download_line_content(message_id, org_settings.line_channel_token)

            if not image_data:
                line_msg.processing_status = 'failed'
                line_msg.error_message = 'Failed to download image from LINE'
                self.db.flush()
                return {'status': 'error', 'reason': 'Failed to download image'}

            line_msg.processing_status = 'processing'
            self.db.flush()

            s3_url = self._upload_to_s3(image_data, org_settings.organization_id, message_id)

            doc_service = EsgDocumentService(self.db)
            result = doc_service.upload_and_classify(
                organization_id=org_settings.organization_id,
                file_data={
                    'file_name': f'line_{message_id}.jpg',
                    'file_url': s3_url,
                    'file_type': 'image/jpeg',
                    'source': 'line',
                },
            )

            if result.get('success'):
                doc = result['document']
                line_msg.document_id = doc.get('id')
                line_msg.processing_status = 'completed'

                self._send_reply(
                    org_settings.line_channel_token,
                    line_msg.line_reply_token,
                    self._format_classification_reply(doc)
                )
                line_msg.reply_sent = True
                line_msg.reply_message = 'Classification result sent'
            else:
                line_msg.processing_status = 'failed'
                line_msg.error_message = result.get('message', 'Classification failed')

            self.db.flush()
            return {'status': 'success', 'document_id': line_msg.document_id}

        except Exception as e:
            logger.error(f"Error processing LINE image: {str(e)}")
            line_msg.processing_status = 'failed'
            line_msg.error_message = str(e)
            self.db.flush()
            return {'status': 'error', 'reason': str(e)}

    def _process_text_message(self, line_msg: EsgLineMessage, event: Dict, org_settings: EsgOrganizationSettings) -> Dict[str, Any]:
        """Handle text messages (help, status queries)"""
        text = event.get('message', {}).get('text', '').strip().lower()

        if text in ('help', 'ช่วย', 'วิธีใช้'):
            reply = (
                'GEPP ESG Document Upload\n\n'
                'Send document photos (weighbridge tickets, invoices, reports) to:\n'
                '- AI classifies ESG category\n'
                '- Extract waste data + calculate CO2e\n\n'
                'Supported: Environment, Social, Governance documents'
            )
        else:
            reply = 'Please send ESG document photos for AI classification and data extraction.\nType "help" for instructions.'

        self._send_reply(org_settings.line_channel_token, line_msg.line_reply_token, reply)
        line_msg.processing_status = 'completed'
        line_msg.reply_sent = True
        line_msg.reply_message = reply
        self.db.flush()

        return {'status': 'success', 'type': 'text_reply'}

    # ==========================================
    # LOOKUP METHODS
    # ==========================================

    def _find_binding_by_group(self, group_id: str) -> Optional[EsgExternalPlatformBinding]:
        """Find platform binding that has this group paired in authorized_groups"""
        bindings = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.channel == 'line',
            EsgExternalPlatformBinding.is_active == True
        ).all()

        for binding in bindings:
            groups = binding.authorized_groups or []
            for g in groups:
                if g.get('group_id') == group_id and g.get('status') == 'paired':
                    return binding
        return None

    def _find_binding_by_destination(self, destination: str) -> Optional[EsgExternalPlatformBinding]:
        """Find platform binding by LINE destination (bot user ID or channel_id)"""
        bindings = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.channel == 'line',
            EsgExternalPlatformBinding.is_active == True
        ).all()

        for binding in bindings:
            auth = binding.auth_json or {}
            if auth.get('channel_id') == destination or auth.get('bot_user_id') == destination:
                return binding

        # Fallback: return first active LINE binding
        if bindings:
            return bindings[0]
        return None

    def _find_org_by_line(self, destination: str, user_id: str) -> Optional[EsgOrganizationSettings]:
        """Find organization settings by LINE channel destination (backward compatible)"""
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.line_channel_id == destination,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            settings = self.db.query(EsgOrganizationSettings).filter(
                EsgOrganizationSettings.line_channel_id.isnot(None),
                EsgOrganizationSettings.line_channel_secret.isnot(None),
                EsgOrganizationSettings.is_active == True
            ).first()

        return settings

    # ==========================================
    # PAIRING
    # ==========================================

    def pair_group_by_code(self, organization_id: int, pairing_code: str) -> Dict[str, Any]:
        """Pair a LINE group with an organization using a pairing code"""
        binding = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.channel == 'line',
            EsgExternalPlatformBinding.is_active == True
        ).first()

        if not binding:
            return {'success': False, 'message': 'No LINE platform binding found for this organization'}

        groups = list(binding.authorized_groups or [])
        matched = None
        for g in groups:
            if g.get('pairing_code') == pairing_code and g.get('status') == 'pending':
                matched = g
                break

        if not matched:
            # Search across all bindings (code might be from a different org's binding)
            all_bindings = self.db.query(EsgExternalPlatformBinding).filter(
                EsgExternalPlatformBinding.channel == 'line',
                EsgExternalPlatformBinding.is_active == True
            ).all()

            for b in all_bindings:
                for g in (b.authorized_groups or []):
                    if g.get('pairing_code') == pairing_code and g.get('status') == 'pending':
                        matched = g
                        binding = b
                        groups = list(b.authorized_groups or [])
                        break
                if matched:
                    break

        if not matched:
            return {'success': False, 'message': 'Invalid or expired pairing code'}

        # Update the group to paired status
        matched['status'] = 'paired'
        matched['paired_at'] = datetime.utcnow().isoformat()
        matched.pop('pairing_code', None)

        # If binding belongs to different org, move the group entry
        if binding.organization_id != organization_id:
            # Remove from current binding
            groups = [g for g in groups if g.get('group_id') != matched['group_id']]
            binding.authorized_groups = groups
            self.db.flush()

            # Add to org's binding
            org_binding = self.db.query(EsgExternalPlatformBinding).filter(
                EsgExternalPlatformBinding.organization_id == organization_id,
                EsgExternalPlatformBinding.channel == 'line',
                EsgExternalPlatformBinding.is_active == True
            ).first()

            if not org_binding:
                return {'success': False, 'message': 'No LINE binding for target organization'}

            org_groups = list(org_binding.authorized_groups or [])
            org_groups.append(matched)
            org_binding.authorized_groups = org_groups
        else:
            binding.authorized_groups = groups

        self.db.flush()

        return {
            'success': True,
            'message': f'Group "{matched.get("group_name", "")}" paired successfully',
            'group': matched,
        }

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _generate_pairing_code(self, length: int = 6) -> str:
        """Generate a random alphanumeric pairing code"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    def _map_message_type(self, line_type: str) -> str:
        """Map LINE message type to extraction type"""
        mapping = {
            'text': 'text',
            'image': 'image',
            'file': 'pdf',
            'video': 'none',
            'audio': 'none',
            'sticker': 'none',
            'location': 'none',
        }
        return mapping.get(line_type, 'none')

    def _is_bot_mentioned(self, event: Dict[str, Any], binding: EsgExternalPlatformBinding) -> bool:
        """Check if the bot is @mentioned in the message"""
        message = event.get('message', {})
        mention = message.get('mention', {})
        mentionees = mention.get('mentionees', [])

        bot_user_id = (binding.auth_json or {}).get('bot_user_id', '')

        for m in mentionees:
            if m.get('type') == 'user' and m.get('userId') == bot_user_id:
                return True

        # Also check if text contains @GEPP or similar trigger words
        text = message.get('text', '').lower()
        if any(trigger in text for trigger in ['@gepp', '@esg', 'สรุป', 'summary']):
            return True

        return False

    def _get_group_name(self, group_id: str, channel_token: str) -> Optional[str]:
        """Get LINE group name via API"""
        try:
            import urllib.request
            url = f'https://api.line.me/v2/bot/group/{group_id}/summary'
            req = urllib.request.Request(url, headers={
                'Authorization': f'Bearer {channel_token}'
            })
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('groupName', '')
        except Exception as e:
            logger.error(f"Failed to get group name: {e}")
            return None

    def _download_and_store(self, message: Dict, binding: EsgExternalPlatformBinding, group_id: str) -> Optional[Dict]:
        """Download content from LINE and upload to S3, return file info"""
        message_id = message.get('id', '')
        channel_token = (binding.auth_json or {}).get('channel_token', '')

        content = self._download_line_content(message_id, channel_token)
        if not content:
            return None

        s3_url = self._upload_to_s3(content, binding.organization_id, message_id)

        return {
            'id': None,
            's3_url': s3_url,
            'file_name': f'line_{message_id}.jpg',
        }

    def _format_extraction_reply(self, extraction: EsgOrganizationDataExtraction) -> str:
        """Format extraction result as LINE reply"""
        matches = extraction.datapoint_matches or []
        extractions = extraction.extractions or {}

        category = extractions.get('category_match', {}).get('name', 'Unknown')
        subcategory = extractions.get('subcategory_match', {}).get('name', '')

        lines = [f'ESG Data Extracted\n']
        if category:
            lines.append(f'Category: {category}')
        if subcategory:
            lines.append(f'Subcategory: {subcategory}')

        if matches:
            lines.append(f'\nDatapoints matched: {len(matches)}')
            for m in matches[:5]:
                value = m.get('value', '')
                unit = m.get('unit', '')
                lines.append(f'  - {value} {unit}')

        return '\n'.join(lines)

    def _verify_signature(self, body: str, signature: str, channel_secret: str) -> bool:
        """Verify LINE webhook signature using HMAC-SHA256"""
        if not channel_secret or not signature:
            return False
        try:
            body_bytes = body.encode('utf-8') if isinstance(body, str) else body
            hash_value = hmac.new(
                channel_secret.encode('utf-8'),
                body_bytes,
                hashlib.sha256
            ).digest()
            computed_signature = base64.b64encode(hash_value).decode('utf-8')
            return hmac.compare_digest(computed_signature, signature)
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}")
            return False

    def _download_line_content(self, message_id: str, channel_token: str) -> Optional[bytes]:
        """Download content from LINE Content API"""
        try:
            import urllib.request
            url = f'https://api-data.line.me/v2/bot/message/{message_id}/content'
            req = urllib.request.Request(url, headers={
                'Authorization': f'Bearer {channel_token}'
            })
            with urllib.request.urlopen(req) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Failed to download LINE content: {str(e)}")
            return None

    def _upload_to_s3(self, file_data: bytes, organization_id: int, message_id: str) -> str:
        """Upload file to S3 and return URL"""
        try:
            import boto3

            s3 = boto3.client('s3')
            bucket = os.environ.get('S3_BUCKET', 'gepp-platform-files')
            key = f'esg/documents/{organization_id}/line/{datetime.utcnow().strftime("%Y%m%d")}/{message_id}.jpg'

            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=file_data,
                ContentType='image/jpeg'
            )

            return f's3://{bucket}/{key}'
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}")
            raise

    def _send_reply(self, channel_token: str, reply_token: str, message: str):
        """Send reply message via LINE Messaging API"""
        if not channel_token or not reply_token:
            return
        try:
            import urllib.request
            url = 'https://api.line.me/v2/bot/message/reply'
            data = json.dumps({
                'replyToken': reply_token,
                'messages': [{'type': 'text', 'text': message}]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {channel_token}'
            })
            urllib.request.urlopen(req)
        except Exception as e:
            logger.error(f"Failed to send LINE reply: {str(e)}")

    def _format_classification_reply(self, doc: Dict[str, Any]) -> str:
        """Format AI classification result as LINE reply message"""
        category = doc.get('esg_category', 'unknown')
        subcategory = doc.get('esg_subcategory', '')
        doc_type = doc.get('document_type', '')
        confidence = doc.get('ai_confidence', 0)
        vendor = doc.get('vendor_name', '')
        summary = doc.get('summary', '')

        category_emoji = {'environment': 'E', 'social': 'S', 'governance': 'G'}.get(category, '?')

        lines = [
            f'[{category_emoji}] ESG Document Classified',
            f'',
            f'Category: {category.title()}',
        ]
        if subcategory:
            lines.append(f'Subcategory: {subcategory}')
        if doc_type:
            lines.append(f'Type: {doc_type}')
        if vendor:
            lines.append(f'Vendor: {vendor}')
        if confidence:
            lines.append(f'Confidence: {confidence:.0%}')
        if summary:
            lines.append(f'\n{summary[:100]}')

        return '\n'.join(lines)
