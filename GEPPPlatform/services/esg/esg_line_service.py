"""
ESG LINE Service — LINE webhook handler for document submissions
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import hashlib
import hmac
import base64
import json
import logging
import os

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.line_messages import EsgLineMessage
from .esg_document_service import EsgDocumentService

logger = logging.getLogger(__name__)


class EsgLineService:
    """Handles LINE webhook events for ESG document processing"""

    def __init__(self, db: Session):
        self.db = db

    def handle_webhook(self, body: str, signature: str) -> Dict[str, Any]:
        """
        Process LINE webhook event.
        1. Find organization by channel
        2. Verify signature
        3. Process events (image → download → upload S3 → classify)
        """
        try:
            payload = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            return {'success': False, 'message': 'Invalid JSON payload'}

        events = payload.get('events', [])
        if not events:
            return {'success': True, 'message': 'No events to process'}

        results = []
        for event in events:
            result = self._process_event(event, body, signature)
            results.append(result)

        return {
            'success': True,
            'message': f'Processed {len(results)} events',
            'results': results
        }

    def _process_event(self, event: Dict[str, Any], raw_body: str, signature: str) -> Dict[str, Any]:
        """Process a single LINE event"""
        event_type = event.get('type')
        if event_type != 'message':
            return {'status': 'skipped', 'reason': f'Event type {event_type} not supported'}

        message = event.get('message', {})
        message_type = message.get('type')
        reply_token = event.get('replyToken')
        source = event.get('source', {})
        user_id = source.get('userId', '')

        # Find organization by LINE channel (from webhook destination)
        destination = event.get('destination', '')
        org_settings = self._find_org_by_line(destination, user_id)
        if not org_settings:
            logger.warning(f"No organization found for LINE destination: {destination}")
            return {'status': 'error', 'reason': 'Organization not found'}

        # Verify signature
        if not self._verify_signature(raw_body, signature, org_settings.line_channel_secret):
            logger.warning("LINE signature verification failed")
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

            # Download image from LINE Content API
            message_id = message.get('id')
            image_data = self._download_line_content(message_id, org_settings.line_channel_token)

            if not image_data:
                line_msg.processing_status = 'failed'
                line_msg.error_message = 'Failed to download image from LINE'
                self.db.flush()
                return {'status': 'error', 'reason': 'Failed to download image'}

            # Upload to S3
            line_msg.processing_status = 'processing'
            self.db.flush()

            s3_url = self._upload_to_s3(
                image_data,
                org_settings.organization_id,
                message_id
            )

            # Create document and trigger classification
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

                # Reply to user
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
                '🌱 GEPP ESG Document Upload\n\n'
                '📸 ส่งรูปถ่ายเอกสาร (ใบชั่ง, ใบกำกับ, รายงาน) เพื่อ:\n'
                '• AI จำแนกประเภทเอกสาร ESG\n'
                '• สกัดข้อมูลขยะ + คำนวณ CO2e อัตโนมัติ\n\n'
                '💡 รองรับเอกสาร: Environment, Social, Governance'
            )
        else:
            reply = '📸 กรุณาส่งรูปถ่ายเอกสาร ESG เพื่อให้ AI จำแนกและสกัดข้อมูล\nพิมพ์ "help" เพื่อดูวิธีใช้'

        self._send_reply(org_settings.line_channel_token, line_msg.line_reply_token, reply)
        line_msg.processing_status = 'completed'
        line_msg.reply_sent = True
        line_msg.reply_message = reply
        self.db.flush()

        return {'status': 'success', 'type': 'text_reply'}

    def _find_org_by_line(self, destination: str, user_id: str) -> Optional[EsgOrganizationSettings]:
        """Find organization settings by LINE channel destination or user mapping"""
        # Try by channel ID first
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.line_channel_id == destination,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            # Try matching any configured org (for single-org setups)
            settings = self.db.query(EsgOrganizationSettings).filter(
                EsgOrganizationSettings.line_channel_id.isnot(None),
                EsgOrganizationSettings.line_channel_secret.isnot(None),
                EsgOrganizationSettings.is_active == True
            ).first()

        return settings

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
        """Download content (image/file) from LINE Content API"""
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
            from datetime import datetime

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

        category_emoji = {'environment': '🌍', 'social': '👥', 'governance': '🏛️'}.get(category, '📄')

        lines = [
            f'{category_emoji} ESG Document Classified',
            f'',
            f'📋 Category: {category.title()}',
        ]
        if subcategory:
            lines.append(f'📂 Subcategory: {subcategory}')
        if doc_type:
            lines.append(f'📄 Type: {doc_type}')
        if vendor:
            lines.append(f'🏢 Vendor: {vendor}')
        if confidence:
            lines.append(f'🎯 Confidence: {confidence:.0%}')
        if summary:
            lines.append(f'\n💡 {summary[:100]}')

        return '\n'.join(lines)
