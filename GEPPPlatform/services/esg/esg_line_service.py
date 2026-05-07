"""
ESG LINE Service — 1:1 Private Chat: Quick Capture & Notification
Features: Smart OCR, Flex Messages, Confirm/Edit postbacks, tCO2e calculation
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import hashlib
import hmac
import base64
import json
import logging
import os
from datetime import datetime, timezone

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.line_messages import EsgLineMessage
from ...models.esg.records import EsgRecord
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from ...models.esg.esg_users import EsgUser
from .esg_document_service import EsgDocumentService
from .esg_carbon_service import EsgCarbonService

logger = logging.getLogger(__name__)

LIFF_BASE_URL = os.environ.get('LIFF_BASE_URL', 'https://esg.gepp.me')

# Fallback LINE channel access token for the ESG Messaging API channel.
# Per-org tokens stored in esg_organization_settings.line_channel_token
# take precedence; this env is the fallback. ESG-prefixed so it doesn't
# collide with the Reward LINE channel's env vars.
# Backward compat: also accept the unprefixed LINE_CHANNEL_ACCESS_TOKEN.
LINE_FALLBACK_TOKEN = (
    os.environ.get('ESG_LINE_CHANNEL_ACCESS_TOKEN')
    or os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
)
if not LINE_FALLBACK_TOKEN:
    logger.warning(
        'ESG_LINE_CHANNEL_ACCESS_TOKEN env var is not set. LINE webhook '
        'replies will fail unless every org has its own '
        'line_channel_token configured in esg_organization_settings.'
    )

# Fallback LINE channel secret for the ESG channel — used to verify
# webhook X-Line-Signature (HMAC-SHA256) when an org has no per-row
# secret in esg_organization_settings.line_channel_secret. ESG-prefixed
# so it doesn't collide with the Reward channel.
# Backward compat: also accept LINE_SECRET.
LINE_FALLBACK_SECRET = (
    os.environ.get('ESG_LINE_SECRET')
    or os.environ.get('LINE_SECRET', '')
)
if not LINE_FALLBACK_SECRET:
    logger.warning(
        'ESG_LINE_SECRET env var is not set. Webhook signature verification '
        'will be skipped for orgs that have no line_channel_secret '
        'configured — replies will work but webhook source is not verified.'
    )


class EsgLineService:
    """LINE webhook handler for 1:1 private chat — Quick Capture & Notification"""

    def __init__(self, db: Session):
        self.db = db
        self.carbon = EsgCarbonService(db)

    # ==========================================
    # WEBHOOK ENTRY POINT
    # ==========================================

    def handle_webhook(self, body: str, signature: str, simulator_opts: Dict = None) -> Dict[str, Any]:
        self._simulator_opts = simulator_opts or {}
        logger.info(f"[WEBHOOK] Received body length={len(body or '')}, signature={signature[:20] if signature else 'none'}...")
        if self._simulator_opts:
            logger.info(f"[WEBHOOK] SIMULATOR: org_id={self._simulator_opts.get('org_id')}")
        try:
            payload = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            logger.error(f"[WEBHOOK] Invalid JSON: {body[:200] if body else 'empty'}")
            return {'success': False, 'message': 'Invalid JSON payload'}

        events = payload.get('events', [])
        destination = payload.get('destination', '')
        logger.info(f"[WEBHOOK] destination={destination}, events={len(events)}")

        if not events:
            return {'success': True, 'message': 'No events'}

        results = []
        for i, event in enumerate(events):
            event_type = event.get('type', '?')
            source = event.get('source', {})
            logger.info(f"[WEBHOOK] Event[{i}]: type={event_type}, source_type={source.get('type')}, userId={source.get('userId', '?')[:12]}")
            result = self._process_event(event, body, signature, destination)
            logger.info(f"[WEBHOOK] Event[{i}] result: {result}")
            results.append(result)

        return {'success': True, 'message': f'Processed {len(results)} events', 'results': results}

    def _process_event(self, event: Dict, raw_body: str, signature: str, destination: str) -> Dict:
        source_type = event.get('source', {}).get('type', '')
        if source_type in ('group', 'room'):
            logger.info(f"[WEBHOOK] Skipping group/room event")
            return {'status': 'skipped', 'reason': 'Group/room not supported'}

        event_type = event.get('type')
        if event_type == 'follow':
            return self._handle_follow(event, raw_body, signature, destination)
        if event_type == 'postback':
            return self._handle_postback(event, raw_body, signature, destination)
        if event_type == 'message':
            return self._handle_message(event, raw_body, signature, destination)
        logger.info(f"[WEBHOOK] Unhandled event type: {event_type}")
        return {'status': 'skipped'}

    # ==========================================
    # FOLLOW EVENT
    # ==========================================

    def _handle_follow(self, event: Dict, raw_body: str, signature: str, destination: str) -> Dict:
        org = self._find_org(destination)
        channel_token = getattr(org, 'line_channel_token', None) or LINE_FALLBACK_TOKEN
        logger.info(f"[FOLLOW] userId={event.get('source', {}).get('userId', '?')[:12]}, org={org is not None}")

        liff_url = LIFF_BASE_URL

        welcome = {
            'type': 'flex',
            'altText': 'ยินดีต้อนรับสู่ GEPP ESG!',
            'contents': {
                'type': 'bubble',
                'body': {
                    'type': 'box', 'layout': 'vertical',
                    'contents': [
                        {'type': 'text', 'text': 'GEPP ESG', 'weight': 'bold', 'size': 'xl', 'color': '#2d6a4f'},
                        {'type': 'text', 'text': 'ยินดีต้อนรับ! เริ่มต้นใช้งานโดยขอ invitation code จากผู้ดูแลองค์กร แล้วกดปุ่มด้านล่างเพื่อเข้าร่วม', 'wrap': True, 'size': 'sm', 'margin': 'lg', 'color': '#666666'},
                        {'type': 'separator', 'margin': 'lg'},
                        {'type': 'text', 'text': 'หลังเข้าร่วมแล้ว คุณสามารถ:', 'size': 'xs', 'color': '#999999', 'margin': 'lg'},
                        {'type': 'text', 'text': '📸 ส่งรูปบิล → AI คำนวณ tCO₂e\n📝 พิมพ์ข้อมูล → คำนวณอัตโนมัติ\n📊 ดู Dashboard ภาพรวม', 'size': 'xs', 'color': '#999999', 'margin': 'sm', 'wrap': True},
                    ],
                },
                'footer': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                    'contents': [
                        {'type': 'button', 'action': {'type': 'uri', 'label': 'เข้าร่วมองค์กร', 'uri': f'{liff_url}/liff'}, 'style': 'primary', 'color': '#2d6a4f'},
                    ],
                },
            },
        }
        self._send_reply_raw(channel_token, event.get('replyToken', ''), [welcome])
        return {'status': 'success', 'type': 'follow'}

    # ==========================================
    # POSTBACK (Rich Menu + Confirm/Edit buttons)
    # ==========================================

    def _handle_postback(self, event: Dict, raw_body: str, signature: str, destination: str) -> Dict:
        org = self._find_org(destination)
        channel_token = getattr(org, 'line_channel_token', None) or LINE_FALLBACK_TOKEN

        postback_data = event.get('postback', {}).get('data', '')
        reply_token = event.get('replyToken', '')
        params = dict(p.split('=', 1) for p in postback_data.split('&') if '=' in p)
        action = params.get('action', '')
        logger.info(f"[POSTBACK] action={action}, params={params}")

        if action == 'confirm' and params.get('entry_id'):
            return self._confirm_entry(int(params['entry_id']), org, reply_token)

        if action == 'confirm_all' and params.get('extraction_id'):
            return self._confirm_all_entries(int(params['extraction_id']), channel_token, reply_token)

        if action == 'edit' and params.get('entry_id'):
            edit_url = f'{LIFF_BASE_URL}/liff/app/entry?edit={params["entry_id"]}'
            self._send_text_reply(channel_token, reply_token, f'แก้ไขข้อมูล:\n{edit_url}')
            return {'status': 'success', 'type': 'edit_redirect'}

        uri_actions = {
            'data_entry': f'{LIFF_BASE_URL}/data-entry',
            'history': f'{LIFF_BASE_URL}/history',
            'export': f'{LIFF_BASE_URL}/history',
            'dashboard': f'{LIFF_BASE_URL}/dashboard',
        }
        if action in uri_actions:
            self._send_text_reply(org.line_channel_token, reply_token, f'เปิดหน้า:\n{uri_actions[action]}')
            return {'status': 'success', 'type': f'postback_{action}'}

        if action == 'help':
            self._send_text_reply(org.line_channel_token, reply_token, self._help_text())
            return {'status': 'success', 'type': 'help'}

        return {'status': 'skipped'}

    def _confirm_entry(self, entry_id: int, org, reply_token: str) -> Dict:
        entry = self.db.query(EsgRecord).filter(
            EsgRecord.id == entry_id, EsgRecord.is_active == True,
        ).first()
        if not entry:
            self._send_text_reply(org.line_channel_token, reply_token, 'ไม่พบข้อมูลนี้')
            return {'status': 'error', 'reason': 'Entry not found'}

        entry.status = 'VERIFIED'
        self.db.commit()
        token = getattr(org, 'line_channel_token', None) or LINE_FALLBACK_TOKEN
        self._send_text_reply(token, reply_token, f'ยืนยันแล้ว! {entry.category} {entry.value} {entry.unit} = {entry.calculated_tco2e or "-"} tCO2e')
        return {'status': 'success', 'type': 'confirmed', 'entry_id': entry_id}

    def _confirm_all_entries(self, extraction_id: int, token: str, reply_token: str) -> Dict:
        """Confirm all entries from an extraction at once."""
        extraction = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.id == extraction_id,
        ).first()
        if not extraction:
            self._send_text_reply(token, reply_token, 'ไม่พบข้อมูลนี้')
            return {'status': 'error'}

        entry_ids = (extraction.extractions or {}).get('entry_ids', [])
        if not entry_ids:
            self._send_text_reply(token, reply_token, 'ไม่พบรายการที่จะยืนยัน')
            return {'status': 'error'}

        count = self.db.query(EsgRecord).filter(
            EsgRecord.id.in_(entry_ids),
            EsgRecord.is_active == True,
        ).update({EsgRecord.status: 'VERIFIED'}, synchronize_session='fetch')
        self.db.commit()

        self._send_text_reply(token, reply_token, f'✅ ยืนยันแล้ว {count} รายการ')
        return {'status': 'success', 'type': 'confirm_all', 'count': count}

    # ==========================================
    # MESSAGE HANDLING
    # ==========================================

    def _handle_message(self, event: Dict, raw_body: str, signature: str, destination: str) -> Dict:
        org = self._find_org(destination)
        logger.info(f"[MSG] org found={org is not None}, org_id={getattr(org, 'organization_id', '?')}")

        message = event.get('message', {})
        msg_type = message.get('type', '')
        reply_token = event.get('replyToken', '')
        user_id = event.get('source', {}).get('userId', '')
        logger.info(f"[MSG] type={msg_type}, userId={user_id[:12] if user_id else '?'}, text={message.get('text', '')[:50] if msg_type == 'text' else '-'}")

        # Determine reply token — use org settings or fallback
        channel_token = getattr(org, 'line_channel_token', None) or LINE_FALLBACK_TOKEN

        # Signature verification (HMAC-SHA256 of raw body using channel secret).
        # Per-org secret takes precedence; falls back to ESG_LINE_SECRET env
        # var so we still verify webhooks even when an org row has no secret
        # yet. Only when neither is available do we skip (and log loudly).
        secret_for_verify = (org.line_channel_secret if org and org.line_channel_secret
                             else LINE_FALLBACK_SECRET)
        if secret_for_verify:
            if not self._verify_sig(raw_body, signature, secret_for_verify):
                logger.warning(f"[MSG] Signature verification failed (secret source={'org' if org and org.line_channel_secret else 'env'})")
                return {'status': 'error', 'reason': 'signature failed'}
        else:
            logger.warning(f"[MSG] No org channel secret AND ESG_LINE_SECRET env not set — skipping signature verification")

        # Check if this LINE user is linked to an org via esg_users
        esg_user = self.db.query(EsgUser).filter(
            EsgUser.platform == 'line',
            EsgUser.platform_user_id == user_id,
            EsgUser.organization_id.isnot(None),
            EsgUser.is_active == True,
        ).first()

        # Simulator bypass: auto-create a temporary user link if --org-id was provided
        sim_org_id = getattr(self, '_simulator_opts', {}).get('org_id')
        if not esg_user and sim_org_id:
            logger.info(f"[MSG] SIMULATOR: Auto-linking user {user_id[:12]} to org {sim_org_id}")
            esg_user = EsgUser(
                organization_id=sim_org_id,
                platform='line',
                platform_user_id=user_id,
                display_name=f'Simulator ({user_id[:12]})',
            )
            self.db.add(esg_user)
            self.db.flush()

        if not esg_user:
            # User not linked — reply with instruction to join org first
            liff_url = LIFF_BASE_URL
            self._send_reply_raw(channel_token, reply_token, [{
                'type': 'flex',
                'altText': 'กรุณาเข้าร่วมองค์กรก่อนใช้งาน',
                'contents': {
                    'type': 'bubble',
                    'body': {
                        'type': 'box', 'layout': 'vertical', 'spacing': 'md',
                        'contents': [
                            {'type': 'text', 'text': 'GEPP ESG', 'weight': 'bold', 'size': 'lg', 'color': '#2d6a4f'},
                            {'type': 'text', 'text': 'คุณยังไม่ได้เชื่อมต่อกับองค์กร', 'size': 'sm', 'color': '#666666', 'margin': 'md', 'wrap': True},
                            {'type': 'text', 'text': 'กรุณาขอ invitation code จากผู้ดูแลองค์กร แล้วกดปุ่มด้านล่างเพื่อเข้าร่วม', 'size': 'xs', 'color': '#999999', 'margin': 'sm', 'wrap': True},
                        ],
                    },
                    'footer': {
                        'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                        'contents': [
                            {'type': 'button', 'action': {'type': 'uri', 'label': 'เข้าร่วมองค์กร', 'uri': f'{liff_url}/liff'}, 'style': 'primary', 'color': '#2d6a4f'},
                        ],
                    },
                },
            }])
            return {'status': 'needs_org', 'line_user_id': user_id}

        line_msg = EsgLineMessage(
            organization_id=esg_user.organization_id,
            line_message_id=message.get('id', ''),
            line_user_id=user_id,
            line_reply_token=reply_token,
            message_type=msg_type,
            processing_status='received',
        )
        self.db.add(line_msg)
        self.db.flush()

        # Use esg_user.organization_id (safe even if org settings is None)
        org_id = esg_user.organization_id

        # Simulator support: forward base64 image data from event._simulator
        simulator = event.get('_simulator', {})
        if simulator.get('image_base64'):
            message['_simulator_image_base64'] = simulator['image_base64']
            logger.info(f"[MSG] Simulator image attached ({len(simulator['image_base64'])} chars)")

        if msg_type == 'text':
            return self._process_text(line_msg, event, org_id, channel_token)
        elif msg_type == 'image':
            return self._process_image(line_msg, message, org_id, channel_token)
        elif msg_type == 'file':
            return self._process_file(line_msg, message, org_id, channel_token)
        else:
            self._send_text_reply(channel_token, reply_token, 'ส่งรูปบิล, ไฟล์ PDF หรือพิมพ์ข้อมูลได้เลยครับ')
            return {'status': 'skipped'}

    # ---- TEXT: AI Intent Extraction → tCO2e ----

    def _process_text(self, line_msg, event: Dict, org_id: int, token: str) -> Dict:
        text = event.get('message', {}).get('text', '').strip()
        text_lower = text.lower()

        if text_lower in ('help', 'ช่วย', 'วิธีใช้', '?'):
            self._send_text_reply(token, line_msg.line_reply_token, self._help_text())
            line_msg.processing_status = 'completed'
            self.db.flush()
            return {'status': 'success', 'type': 'help'}

        if text_lower in ('status', 'สถานะ', 'สรุป', 'summary'):
            self._send_text_reply(token, line_msg.line_reply_token,
                                  f'ดูสรุปภาพรวม:\n{LIFF_BASE_URL}/liff/app/esg')
            line_msg.processing_status = 'completed'
            self.db.flush()
            return {'status': 'success', 'type': 'status'}

        # ── 1. Reserve doc number FIRST so the immediate ack can quote it
        extraction = EsgOrganizationDataExtraction(
            organization_id=org_id,
            channel='line', type='text',
            source_user_id=line_msg.line_user_id,
            source_message_id=line_msg.line_message_id,
            raw_content=text, processing_status='pending',
        )
        self.db.add(extraction)
        self.db.flush()
        doc_no = extraction.id

        # ── 2. Immediate PUSH "received" card (does NOT consume reply_token)
        try:
            if line_msg.line_user_id:
                self._send_push_message(
                    token, line_msg.line_user_id,
                    [self._build_received_flex(doc_no)],
                )
        except Exception as e:
            logger.warning(f"[TEXT] Failed to push received card: {e}")

        # ── 3. Run LLM cascade extraction (synchronous)
        try:
            from .esg_extraction_service import EsgExtractionService
            svc = EsgExtractionService(self.db)
            svc.process_extraction(extraction.id)
            self.db.refresh(extraction)
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")

        entry = self._create_entry_from_extraction(extraction, org_id, line_msg.line_user_id)

        # ── 4. + 5. Per-category PUSH + final REPLY
        if entry:
            self._dispatch_extraction_messages(
                token=token,
                line_user_id=line_msg.line_user_id,
                reply_token=line_msg.line_reply_token,
                doc_id=doc_no,
                entries=[entry],
                organization_id=org_id,
                refs={'document_date': str(entry.get('entry_date') or '')},
            )
        else:
            err_card = self._build_error_flex(
                doc_no,
                'ได้รับข้อความแล้ว แต่ไม่สามารถสกัดตัวเลขได้ กรุณากรอกผ่าน LIFF',
            )
            self._send_reply_raw(token, line_msg.line_reply_token, [err_card])

        line_msg.processing_status = extraction.processing_status
        self.db.flush()
        return {'status': 'success', 'type': 'text_extraction', 'entry_id': entry['id'] if entry else None}

    # ---- IMAGE: OCR → tCO2e → Flex Message ----

    def _process_image(self, line_msg, message: Dict, org_id: int, token: str) -> Dict:
        """
        Image processing flow (push-as-progress-bar pattern):

          1. Reserve a doc number by creating the extraction record up-front.
          2. PUSH "ได้รับเอกสาร #1232 — กำลังประมวลผล" immediately.
             (We deliberately don't burn the reply_token on this ack so we
             can use it for the final completion card.)
          3. Run the slow LLM extraction synchronously.
          4. Group results by Scope 3 category and PUSH one card per cat.
          5. Final summary uses REPLY (the saved reply_token) so it lands
             as a "real" reply to the user's original image. If the token
             has already expired (LINE 60s TTL), fall back to PUSH.
        """
        try:
            message_id = message.get('id')
            logger.info(f"----------- IMAGE PROCESSING START -----------")
            logger.info(f"[IMG] msg_id={message_id}, org_id={org_id}, user={line_msg.line_user_id[:12] if line_msg.line_user_id else '?'}")

            simulator_data = message.get('_simulator_image_base64')
            if simulator_data:
                import base64 as b64mod
                logger.info(f"[IMG] Using simulator image data ({len(simulator_data)} chars base64)")
                image_data = b64mod.b64decode(simulator_data)
            else:
                image_data = self._download_content(message_id, token)
            if not image_data:
                logger.error(f"[IMG] Failed to download image from LINE")
                self._send_text_reply(token, line_msg.line_reply_token, 'ดาวน์โหลดรูปไม่สำเร็จ ลองใหม่อีกครั้ง')
                return {'status': 'error'}
            logger.info(f"[IMG] Downloaded {len(image_data)} bytes")

            s3_url = self._upload_s3(image_data, org_id, message_id, 'image/jpeg',
                                     line_user_id=line_msg.line_user_id)
            logger.info(f"[IMG] Uploaded to S3: {s3_url[:80]}")

            # ── 1. Reserve a doc number FIRST so the immediate ack can
            # quote it. Same record is reused by extract_from_image below
            # (avoids duplicate rows).
            extraction = EsgOrganizationDataExtraction(
                organization_id=org_id,
                channel='line',
                type='image',
                source_user_id=line_msg.line_user_id,
                source_message_id=line_msg.line_message_id,
                raw_content=s3_url,
                processing_status='pending',
            )
            self.db.add(extraction)
            self.db.flush()
            doc_no = extraction.id
            logger.info(f"[IMG] Doc #{doc_no} reserved")

            # ── 2. Immediate PUSH "received" card (does NOT consume reply_token)
            try:
                if line_msg.line_user_id:
                    received_card = self._build_received_flex(doc_no)
                    self._send_push_message(token, line_msg.line_user_id, [received_card])
                    logger.info(f"[IMG] Push #1: received card sent")
            except Exception as e:
                logger.warning(f"[IMG] Failed to push received card: {e}")

            # ── 3. Run extraction (synchronous, can take 10-30s)
            logger.info(f"[IMG] Starting Gemini extraction...")
            from .esg_image_extraction_service import EsgImageExtractionService
            extraction_svc = EsgImageExtractionService(self.db)
            result = extraction_svc.extract_from_image(
                s3_url=s3_url,
                org_id=org_id,
                line_user_id=line_msg.line_user_id,
                message_id=line_msg.line_message_id,
                existing_extraction=extraction,
            )
            logger.info(f"[IMG] Extraction result: success={result.get('success')}, entries={len(result.get('entries', []))}")

            # ── 4. + 5. Build per-category PUSHes + final REPLY
            if result.get('success') and result.get('entries'):
                self._dispatch_extraction_messages(
                    token=token,
                    line_user_id=line_msg.line_user_id,
                    reply_token=line_msg.line_reply_token,
                    doc_id=doc_no,
                    entries=result['entries'],
                    organization_id=org_id,
                    refs=result.get('refs', {}),
                )
            else:
                err_msg = result.get('message', 'อ่านข้อมูลจากรูปไม่ออก กรุณาถ่ายใหม่ให้ชัดขึ้น')
                logger.info(f"[IMG] No entries, sending error: {err_msg}")
                err_card = self._build_error_flex(doc_no, err_msg)
                # Use reply_token for the error too (final response)
                self._send_reply_raw(token, line_msg.line_reply_token, [err_card])

            # Simulator dry-run: rollback DB changes, return full extraction data
            sim_dry = getattr(self, '_simulator_opts', {}).get('dry_run', False)
            if sim_dry:
                logger.info(f"[IMG] SIMULATOR DRY-RUN: rolling back DB changes")
                self.db.rollback()
            else:
                line_msg.processing_status = 'completed'
                self.db.flush()

            logger.info(f"----------- IMAGE PROCESSING DONE -----------")

            # Build detailed response for simulator
            is_simulator = bool(getattr(self, '_simulator_opts', {}))
            response = {
                'status': 'success', 'type': 'image',
                'extraction_id': result.get('extraction_id'),
                'entry_count': result.get('match_count', 0),
                'dry_run': sim_dry,
            }
            if is_simulator:
                response['debug'] = {
                    'document_summary': result.get('document_summary', ''),
                    'refs': result.get('refs', {}),
                    'llm_model': result.get('model', ''),
                    'llm_tokens': result.get('usage', {}),
                    'records': [],
                    'entries': [],
                }
                # Include full record data
                for rec in (result.get('records') or []):
                    debug_rec = {
                        'record_label': rec.get('record_label', ''),
                        'category_id': rec.get('category_id'),
                        'category_name': rec.get('category_name', ''),
                        'subcategory_id': rec.get('subcategory_id'),
                        'subcategory_name': rec.get('subcategory_name', ''),
                        'fields': [],
                    }
                    for f in (rec.get('fields') or []):
                        debug_rec['fields'].append({
                            'datapoint_id': f.get('datapoint_id'),
                            'datapoint_name': f.get('datapoint_name', ''),
                            'value': f.get('value'),
                            'unit': f.get('unit', ''),
                            'confidence': f.get('confidence'),
                            'tags': f.get('tags', []),
                        })
                    response['debug']['records'].append(debug_rec)
                # Include entry summaries
                for entry in (result.get('entries') or []):
                    e = entry if isinstance(entry, dict) else {}
                    response['debug']['entries'].append({
                        'id': e.get('id'),
                        'category': e.get('category', ''),
                        'category_id': e.get('category_id'),
                        'subcategory_id': e.get('subcategory_id'),
                        'datapoint_id': e.get('datapoint_id'),
                        'value': float(e.get('value', 0)) if e.get('value') is not None else None,
                        'unit': e.get('unit', ''),
                        'calculated_tco2e': float(e.get('calculated_tco2e', 0)) if e.get('calculated_tco2e') is not None else None,
                        'scope_tag': e.get('scope_tag', ''),
                        'currency': e.get('currency', ''),
                        'confidence': (e.get('extra_data') or {}).get('confidence'),
                        'record_label': (e.get('extra_data') or {}).get('record_label', ''),
                    })

            return response

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"----------- IMAGE PROCESSING ERROR -----------")
            logger.error(f"[IMG] Exception: {type(e).__name__}: {e}")
            logger.error(f"[IMG] Traceback:\n{tb}")
            logger.error(f"-----------------------------------------------")
            try:
                self._send_text_reply(token, line_msg.line_reply_token,
                                      'เกิดข้อผิดพลาดในการประมวลผลรูป กรุณาลองใหม่')
            except Exception:
                pass
            line_msg.processing_status = 'failed'
            self.db.flush()
            return {'status': 'error', 'reason': str(e)}

    # ---- FILE: PDF/Excel → classify → tCO2e ----

    def _process_file(self, line_msg, message: Dict, org_id: int, token: str) -> Dict:
        file_size = message.get('fileSize', 0)
        if file_size > 5 * 1024 * 1024:
            self._send_text_reply(token, line_msg.line_reply_token, 'ไฟล์ใหญ่เกิน 5MB กรุณาลดขนาดไฟล์')
            return {'status': 'error', 'reason': 'File too large'}

        try:
            message_id = message.get('id')
            file_name = message.get('fileName', f'line_{message_id}')
            content_type = self._guess_type(file_name)
            file_data = self._download_content(message_id, token)
            if not file_data:
                return {'status': 'error'}

            s3_url = self._upload_s3(file_data, org_id, message_id, content_type,
                                     line_user_id=line_msg.line_user_id)

            doc_svc = EsgDocumentService(self.db)
            result = doc_svc.upload_and_classify(
                organization_id=org_id,
                file_data={'file_name': file_name, 'file_url': s3_url, 'file_type': content_type, 'source': 'line'},
            )

            doc = result.get('document', {}) if result.get('success') else {}
            self._send_text_reply(token, line_msg.line_reply_token,
                                  f'ได้รับเอกสาร: {file_name}\nหมวด: {doc.get("esg_category", "processing")}\nดูรายละเอียดใน LIFF')

            line_msg.processing_status = 'completed'
            line_msg.document_id = doc.get('id')
            self.db.flush()
            return {'status': 'success', 'type': 'file'}

        except Exception as e:
            logger.error(f"File processing error: {e}")
            return {'status': 'error'}

    # ==========================================
    # FLEX MESSAGE BUILDER
    # ==========================================

    def _build_result_flex(self, entry: dict) -> dict:
        """
        Build Flex Message that explicitly tells the user:
          - which Scope 3 category we assigned (1..15) + the canonical name
          - what data we extracted (value + unit)
          - the calculated tCO2e (or "needs more data" when NULL)
          - which fields are still missing for an accurate calculation
          - confirm / edit-in-LIFF buttons
        """
        from .scope3_assignment import (
            assign_scope3_category,
            missing_fields_for,
            SCOPE3_LABELS,
        )

        tco2e = entry.get('calculated_tco2e')
        category = entry.get('category', 'Unknown')
        value = entry.get('value', 0)
        unit = entry.get('unit', '')
        entry_id = entry.get('id', 0)

        scope3_id, name_en, name_th, source = assign_scope3_category(
            self.db,
            category_name=category,
            category_id=entry.get('category_id'),
            unit=unit,
            raw_input=entry.get('notes') or entry.get('raw_content'),
        )
        cat_label = name_th or name_en or 'Scope 3'
        cat_chip = f'หมวด {scope3_id} · {cat_label}' if scope3_id else 'Scope 3'

        tco2e_text = (
            f'{float(tco2e):.4f} tCO₂e'
            if tco2e is not None
            else 'ต้องการข้อมูลเพิ่มเพื่อคำนวณ'
        )

        present = []
        if value is not None:
            present.append('amount' if (unit or '').lower() in ('thb', 'usd', 'baht') else 'value')
        if unit:
            present.append(unit.lower())
        missing = missing_fields_for(scope3_id, present, lang='th') if scope3_id else []

        body_contents = [
            # Top: assigned category chip
            {
                'type': 'box', 'layout': 'vertical', 'cornerRadius': '8px',
                'backgroundColor': '#ECFDF5', 'paddingAll': '8px',
                'contents': [
                    {'type': 'text', 'text': cat_chip,
                     'size': 'sm', 'weight': 'bold', 'color': '#047857', 'wrap': True},
                ],
            },
            # Extracted value
            {'type': 'box', 'layout': 'horizontal', 'margin': 'md', 'contents': [
                {'type': 'text', 'text': 'ค่าที่อ่านได้', 'size': 'sm', 'color': '#888', 'flex': 2},
                {'type': 'text', 'text': f'{value} {unit}'.strip(),
                 'size': 'sm', 'weight': 'bold', 'flex': 3, 'wrap': True},
            ]},
            # Original LLM category text (for transparency)
            {'type': 'box', 'layout': 'horizontal', 'contents': [
                {'type': 'text', 'text': 'อ่านได้เป็น', 'size': 'xs', 'color': '#888', 'flex': 2},
                {'type': 'text', 'text': str(category)[:40],
                 'size': 'xs', 'color': '#666', 'flex': 3, 'wrap': True},
            ]},
            {'type': 'separator', 'margin': 'md'},
            # tCO2e
            {'type': 'box', 'layout': 'horizontal', 'margin': 'md', 'contents': [
                {'type': 'text', 'text': 'คาร์บอน', 'size': 'md',
                 'color': '#10b981', 'weight': 'bold', 'flex': 2},
                {'type': 'text', 'text': tco2e_text, 'size': 'md',
                 'weight': 'bold', 'flex': 3, 'wrap': True},
            ]},
        ]

        # Missing-fields hint
        if missing:
            body_contents.append({'type': 'separator', 'margin': 'md'})
            body_contents.append({
                'type': 'text', 'text': '🟠 ต้องการข้อมูลเพิ่ม:',
                'size': 'xs', 'color': '#b45309', 'weight': 'bold', 'margin': 'md',
            })
            for m in missing[:4]:
                body_contents.append({
                    'type': 'text', 'text': f'  • {m}',
                    'size': 'xs', 'color': '#92400e', 'wrap': True, 'margin': 'xs',
                })

        return {
            'type': 'flex',
            'altText': f'{cat_chip} — {value} {unit} → {tco2e_text}',
            'contents': {
                'type': 'bubble',
                'header': {
                    'type': 'box', 'layout': 'vertical',
                    'backgroundColor': '#0b1120', 'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': 'Carbon Scope 3',
                         'color': '#a7f3d0', 'size': 'xs', 'weight': 'bold'},
                        {'type': 'text', 'text': 'ได้รับข้อมูลแล้ว ✓',
                         'color': '#FFFFFF', 'weight': 'bold', 'size': 'lg', 'margin': 'sm'},
                    ],
                },
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                    'contents': body_contents,
                },
                'footer': {
                    'type': 'box', 'layout': 'horizontal', 'spacing': 'sm',
                    'contents': [
                        {'type': 'button',
                         'action': {'type': 'postback', 'label': 'ยืนยัน',
                                    'data': f'action=confirm&entry_id={entry_id}'},
                         'style': 'primary', 'color': '#0b1120'},
                        {'type': 'button',
                         'action': {'type': 'postback', 'label': 'แก้ไขใน LIFF',
                                    'data': f'action=edit&entry_id={entry_id}'},
                         'style': 'secondary'},
                    ],
                },
            },
        }

    # ==========================================
    # HELPERS
    # ==========================================

    def _create_entry_from_extraction(self, extraction, org_id: int, line_user_id: str) -> dict | None:
        matches = extraction.datapoint_matches or []
        extr = extraction.extractions or {}
        if not matches:
            return None

        first = matches[0]
        value = first.get('value')
        unit = first.get('unit', '')
        if not value:
            return None

        cat_match = extr.get('category_match') or {}
        cat_name = cat_match.get('name') or cat_match.get('category_name') or ''
        # The LLM cascade returns category_id (the DB row id). Persist it so
        # the dashboard JOIN to esg_data_category works and the LIFF per-user
        # filter (EsgRecord.user_id = current LIFF user) returns rows.
        cat_id = cat_match.get('category_id') or cat_match.get('id')

        # Force the category to one of the 15 specific Scope 3 rows. The
        # LLM sometimes returns the legacy generic 'Carbon Emissions Scope 3'
        # row, which has no scope3_category_id and prevents the dashboard
        # JOIN + fallback EF from working. Resolve the proper Scope 3
        # category here using a deterministic post-processor.
        from .scope3_assignment import assign_scope3_category
        scope3_id, name_en, _name_th, _src = assign_scope3_category(
            self.db,
            category_name=cat_name,
            category_id=cat_id,
            unit=unit,
            raw_input=extraction.raw_content if hasattr(extraction, 'raw_content') else None,
        )
        if scope3_id:
            try:
                from ...models.esg.data_hierarchy import EsgDataCategory
                row = (
                    self.db.query(EsgDataCategory)
                    .filter(
                        EsgDataCategory.is_scope3 == True,
                        EsgDataCategory.scope3_category_id == int(scope3_id),
                        EsgDataCategory.deleted_date.is_(None),
                    )
                    .first()
                )
                if row:
                    cat_id = int(row.id)
                    cat_name = row.name or name_en or cat_name
            except Exception:
                logger.exception('scope3 category remap failed')

        sub_match = extr.get('subcategory_match') or {}
        sub_id = sub_match.get('subcategory_id') or sub_match.get('id')
        dp_id = first.get('datapoint_id') or first.get('id')

        # Resolve EsgUser.id from line_user_id so this entry attaches to the
        # right LIFF user — without this, user_id=0 means the LIFF dashboard
        # can never see entries created via the LINE webhook.
        liff_user_id = self._resolve_liff_user_id(line_user_id, org_id)

        tco2e = (
            self.carbon.calculate_tco2e(
                category=cat_name or 'unknown',
                amount=float(value),
                unit=unit,
                category_id=cat_id,
            )
            if value and unit
            else None
        )
        scope = self.carbon.get_scope_for_category(cat_name) if cat_name else None

        entry = EsgRecord(
            organization_id=org_id,
            user_id=liff_user_id or 0,
            line_user_id=line_user_id,
            category_id=cat_id,
            subcategory_id=sub_id,
            datapoint_id=dp_id,
            category=cat_name,
            value=value,
            unit=unit,
            calculated_tco2e=tco2e,
            scope_tag=scope,
            entry_source='LINE_CHAT',
            status='PENDING_VERIFY',
            entry_date=datetime.utcnow().date(),
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry.to_dict()

    def _resolve_liff_user_id(self, line_user_id: str, org_id: int) -> int | None:
        """
        Look up EsgUser.id for the LINE user_id. Returns None when not
        found (the user follows the OA but hasn't completed invitation yet).
        """
        if not line_user_id:
            return None
        try:
            from ...models.esg.esg_users import EsgUser
            row = (
                self.db.query(EsgUser)
                .filter(
                    EsgUser.platform == 'line',
                    EsgUser.platform_user_id == line_user_id,
                    EsgUser.organization_id == org_id,
                    EsgUser.is_active == True,
                )
                .first()
            )
            return int(row.id) if row else None
        except Exception:
            return None

    def _help_text(self) -> str:
        return (
            'GEPP ESG - วิธีใช้\n\n'
            '1. ถ่ายรูปบิล/ใบเสร็จ → AI อ่านค่าและคำนวณ tCO2e\n'
            '2. พิมพ์ข้อความ เช่น "ค่าไฟ 5000 kWh" → คำนวณอัตโนมัติ\n'
            '3. ส่งไฟล์ PDF/Excel → ระบบจัดหมวดหมู่ให้\n\n'
            'คำสั่ง: "help", "status", "สรุป"'
        )

    def _find_org(self, destination: str):
        s = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.line_channel_id == destination,
            EsgOrganizationSettings.is_active == True,
        ).first()
        if not s:
            s = self.db.query(EsgOrganizationSettings).filter(
                EsgOrganizationSettings.line_channel_id.isnot(None),
                EsgOrganizationSettings.is_active == True,
            ).first()
        return s

    def _verify_sig(self, body: str, signature: str, secret: str) -> bool:
        if not secret or not signature:
            return False
        try:
            b = body.encode('utf-8') if isinstance(body, str) else body
            h = hmac.new(secret.encode('utf-8'), b, hashlib.sha256).digest()
            return hmac.compare_digest(base64.b64encode(h).decode('utf-8'), signature)
        except Exception:
            return False

    def _download_content(self, msg_id: str, token: str):
        try:
            import urllib.request
            req = urllib.request.Request(
                f'https://api-data.line.me/v2/bot/message/{msg_id}/content',
                headers={'Authorization': f'Bearer {token}'},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def _upload_s3(self, data: bytes, org_id: int, msg_id: str, ct: str = 'image/jpeg',
                   line_user_id: str = None) -> str:
        import boto3
        import uuid
        s3 = boto3.client('s3')
        bucket = os.environ.get('S3_BUCKET_NAME', 'prod-gepp-platform-assets')
        ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf',
               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
               'application/vnd.ms-excel': 'xls', 'text/csv': 'csv'}.get(ct, 'bin')
        date_str = datetime.utcnow().strftime('%Y%m%d')
        hash_id = uuid.uuid4().hex[:12]
        line_id = line_user_id or 'unknown'
        key = f'esg/org/{org_id}/LINE/{line_id}/{date_str}_{hash_id}.{ext}'
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=ct)
        return f's3://{bucket}/{key}'

    def _guess_type(self, name: str) -> str:
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        return {'pdf': 'application/pdf', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'xls': 'application/vnd.ms-excel', 'csv': 'text/csv', 'jpg': 'image/jpeg', 'png': 'image/png'}.get(ext, 'application/octet-stream')

    def _send_text_reply(self, token: str, reply_token: str, text: str):
        self._send_reply_raw(token, reply_token, [{'type': 'text', 'text': text[:5000]}])

    # ─── Flex builders for the multi-step push flow ────────────────────
    # Each builder returns a LINE Flex message dict ready for `messages: [..]`.
    # Design language: dark ink (#0b1120) for primary actions, emerald
    # (#10b981) for success / carbon, amber (#f59e0b) for warnings.

    def _doc_no(self, doc_id) -> str:
        try:
            return f"#{int(doc_id):04d}"
        except (TypeError, ValueError):
            return f"#{doc_id}"

    def _build_received_flex(self, doc_id) -> dict:
        """Sent immediately when an image arrives — confirms receipt + doc no."""
        doc = self._doc_no(doc_id)
        return {
            'type': 'flex',
            'altText': f'ได้รับเอกสาร {doc} แล้ว — กำลังประมวลผล',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'header': {
                    'type': 'box', 'layout': 'vertical',
                    'backgroundColor': '#0b1120',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': 'กำลังประมวลผล',
                         'color': '#a7f3d0', 'size': 'xs',
                         'weight': 'bold'},
                        {'type': 'text', 'text': f'เอกสาร {doc}',
                         'color': '#ffffff', 'size': 'xl',
                         'weight': 'bold', 'margin': 'sm'},
                    ],
                },
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'md',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': 'ได้รับเอกสารเรียบร้อยแล้ว',
                         'size': 'sm', 'color': '#0b1120', 'weight': 'bold'},
                        {'type': 'text', 'text': 'AI กำลังอ่านและจัดหมวดหมู่ Scope 3...',
                         'size': 'xs', 'color': '#64748b', 'wrap': True},
                        {'type': 'separator', 'margin': 'md'},
                        # Step list
                        {'type': 'box', 'layout': 'vertical', 'spacing': 'xs', 'margin': 'md',
                         'contents': [
                             self._step_row('✓', 'รับเอกสาร', '#10b981', done=True),
                             self._step_row('●', 'สกัดข้อมูลด้วย AI', '#0b1120', done=False, active=True),
                             self._step_row('○', 'จัดหมวดหมู่ Scope 3', '#cbd5e1', done=False),
                         ]},
                    ],
                },
            },
        }

    def _step_row(self, icon: str, text: str, color: str, done: bool = False, active: bool = False) -> dict:
        weight = 'bold' if (done or active) else 'regular'
        text_color = '#0b1120' if (done or active) else '#94a3b8'
        return {
            'type': 'box', 'layout': 'horizontal', 'spacing': 'sm',
            'contents': [
                {'type': 'text', 'text': icon, 'flex': 0,
                 'size': 'sm', 'color': color, 'weight': 'bold'},
                {'type': 'text', 'text': text, 'flex': 1,
                 'size': 'xs', 'color': text_color, 'weight': weight},
            ],
        }

    # ── Thai-Buddhist date formatting ──────────────────────────────────
    _THAI_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

    def _fmt_thai_date(self, date_input) -> str:
        """Format a date as '27 มี.ค. 2569' (Thai short, Buddhist year)."""
        if not date_input:
            return ''
        try:
            from datetime import datetime, date
            if isinstance(date_input, str):
                # Try common formats
                for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y'):
                    try:
                        d = datetime.strptime(date_input.split('T')[0], fmt.split('T')[0])
                        return f"{d.day} {self._THAI_MONTHS[d.month - 1]} {d.year + 543}"
                    except (ValueError, IndexError):
                        continue
                return str(date_input)
            if isinstance(date_input, (datetime, date)):
                return f"{date_input.day} {self._THAI_MONTHS[date_input.month - 1]} {date_input.year + 543}"
        except Exception:
            pass
        return str(date_input)

    def _build_analysis_flex(self, doc_id, scope3_id: int, refs: dict,
                             entries: list, total_kg: float = 0) -> dict:
        """
        Message 1 of the per-category pair.
        White card with a green divider showing the EXTRACTED RAW FIELDS:
        document type, vendor, line item count, total amount, date.

        When `total_kg` is 0/None (i.e. CO₂e couldn't be computed), append
        a "⚠️ ขาดข้อมูล" section explaining which inputs are missing and
        why the calculation can't proceed.
        """
        doc = self._doc_no(doc_id)
        refs = refs if isinstance(refs, dict) else {}

        rows = []

        # ── ประเภทเอกสาร (document_type) — NOT the vendor name ──
        doc_type = refs.get('document_type') or refs.get('type')
        if doc_type:
            rows.append(self._kv_row('📄', 'ประเภท', str(doc_type)))

        # ── ผู้ขาย / บริษัท (vendor) ──
        vendor = refs.get('vendor')
        if vendor:
            rows.append(self._kv_row('🏢', 'ผู้ขาย', str(vendor)))

        # ── ราคารวม (total_amount) — entire document, not 1 SKU ──
        total_amount = refs.get('total_amount')
        currency = (refs.get('currency') or '').upper() or 'THB'
        if total_amount is not None:
            try:
                amt_text = f'{float(total_amount):,.2f} {currency}'
            except (TypeError, ValueError):
                amt_text = f'{total_amount} {currency}'
            rows.append(self._kv_row('💰', 'ราคารวม', amt_text))

        # ── จำนวนรายการ (line_item_count) ──
        line_count = refs.get('line_item_count')
        if line_count:
            rows.append(self._kv_row('🔢', 'จำนวนรายการ', f'{int(line_count)} รายการ'))

        # ── วันที่ (Buddhist year) ──
        doc_date = refs.get('document_date')
        if doc_date:
            rows.append(self._kv_row('📅', 'วันที่', self._fmt_thai_date(doc_date)))

        # ── เลขที่เอกสาร ──
        ref_no = refs.get('reference_number')
        if ref_no:
            rows.append(self._kv_row('🧾', 'เลขที่', str(ref_no)))

        if not rows:
            rows.append({
                'type': 'text',
                'text': 'ไม่พบข้อมูลที่ extract ได้จากเอกสารนี้',
                'size': 'sm', 'color': '#64748b', 'wrap': True,
            })

        # ── Diagnostic: why couldn't we compute CO₂e? ──
        diagnostic_box = None
        if not total_kg or total_kg <= 0:
            diagnostic_box = self._build_co2_diagnostic_box(scope3_id, refs, entries)

        body_contents = [
            {'type': 'text', 'text': 'ผลการวิเคราะห์เอกสาร',
             'size': 'md', 'weight': 'bold', 'color': '#0b1120'},
            # green divider line under header
            {'type': 'box', 'layout': 'vertical',
             'height': '3px', 'width': '64px',
             'backgroundColor': '#10b981',
             'cornerRadius': '2px', 'margin': 'sm',
             'contents': []},
            {'type': 'box', 'layout': 'vertical',
             'spacing': 'md', 'margin': 'lg',
             'contents': rows},
        ]
        if diagnostic_box is not None:
            body_contents.append(diagnostic_box)

        return {
            'type': 'flex',
            'altText': f'{doc} — ผลการวิเคราะห์เอกสาร',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'body': {
                    'type': 'box', 'layout': 'vertical',
                    'paddingAll': '20px', 'spacing': 'sm',
                    'contents': body_contents,
                },
            },
        }

    def _build_co2_diagnostic_box(self, scope3_id: int, refs: dict, entries: list) -> dict:
        """
        Amber diagnostic block explaining why kgCO₂e couldn't be computed
        for this document yet — lists the missing fields per the Scope 3
        category's expected inputs and gives a one-line reason.
        """
        from .scope3_assignment import EXPECTED_FIELDS, missing_fields_for, SCOPE3_LABELS

        # Collect what we DID get. Push BOTH Thai and English tokens so
        # the matcher (which checks Thai EXPECTED_FIELDS by substring)
        # can find evidence regardless of which language the field name
        # was extracted in.
        present_fields: list[str] = []
        for e in entries:
            label = (e.get('field') or e.get('datapoint_name') or '').strip()
            if label:
                present_fields.append(label.lower())
            unit = (e.get('unit') or '').strip().lower()
            if unit:
                present_fields.append(unit)
        if refs.get('total_amount'):
            # Match Thai expected tokens like "ยอดเงิน (บาท)" / "ค่าใช้จ่าย" /
            # "มูลค่าลงทุน" — all share the substring "เงิน" or "บาท"/"มูลค่า".
            present_fields.extend(['amount', 'ยอดเงิน', 'มูลค่า', 'ราคา', 'บาท'])
        if refs.get('vendor'):
            present_fields.extend(['vendor', 'ผู้ขาย', 'บริษัท'])
        if refs.get('document_type'):
            present_fields.extend(['document_type', 'ประเภท'])
        if refs.get('document_date'):
            present_fields.extend(['date', 'วันที่'])
        if refs.get('line_item_count'):
            present_fields.extend(['count', 'จำนวน', 'รายการ'])
        if refs.get('reference_number'):
            present_fields.extend(['ref', 'เลขที่'])

        missing = missing_fields_for(scope3_id, present_fields, lang='th')
        if not missing:
            # Spend-only docs (e.g. cat 1 receipts) usually have everything
            # the heuristic looks for — but the *real* blocker is missing
            # an emission factor. Make that explicit.
            missing = ['ค่า EF (emission factor) ที่จับคู่กับสินค้านี้']

        cat_th = SCOPE3_LABELS.get(int(scope3_id), {}).get('th', f'หมวด {scope3_id}')

        # Pick a reason. Rules of thumb:
        #   - cat 1/2/15: spend-based but no item description/quantity → can't classify EF
        #   - cat 4/9: missing distance / mode / weight
        #   - cat 5/12: missing weight / waste stream
        #   - cat 6/7: missing distance / mode / class
        #   - cat 11: missing energy/lifetime/units
        reason_map = {
            1:  'มีเฉพาะมูลค่าเงิน แต่ขาดประเภทสินค้าหรือ EF ที่ตรงหมวดนี้ ทำให้คำนวณ kgCO₂e ตามมูลค่าได้ไม่แม่นยำ',
            2:  'ขาดข้อมูลประเภทสินทรัพย์ทุน หรือ EPD/LCA จากผู้ผลิต',
            3:  'ขาดค่า EF แบบ well-to-tank หรือสัดส่วนสูญเสียในระบบส่งจ่าย',
            4:  'ขาดน้ำหนัก × ระยะทาง × รูปแบบขนส่ง — ต้องการอย่างน้อย 2 ใน 3 อย่าง',
            5:  'ขาดน้ำหนักและประเภทของเสีย/วิธีกำจัด',
            6:  'ขาดเส้นทางการเดินทางหรือชั้นโดยสาร / ระยะทาง',
            7:  'ขาดรูปแบบการเดินทาง × ระยะทาง × จำนวนวัน',
            8:  'ขาดข้อมูลพื้นที่หรือการใช้พลังงานของพื้นที่เช่า',
            9:  'ขาดน้ำหนัก × ระยะทาง × รูปแบบขนส่ง — ต้องการอย่างน้อย 2 ใน 3 อย่าง',
            10: 'ขาดข้อมูลพลังงานในขั้นตอนแปรรูปต่อ',
            11: 'ขาดกำลังไฟฟ้าหรือพลังงานที่ใช้ตลอดอายุการใช้งานของสินค้า',
            12: 'ขาดน้ำหนัก/วัสดุของสินค้าและช่องทางกำจัด',
            13: 'ขาดข้อมูลการใช้พลังงานของผู้เช่า',
            14: 'ขาดจำนวนแฟรนไชส์หรือพลังงานเฉลี่ยต่อสาขา',
            15: 'ขาดข้อมูลผู้รับการลงทุนหรือ % การถือหุ้น',
        }
        reason = reason_map.get(int(scope3_id),
                                'ข้อมูลที่สกัดได้ยังไม่เพียงพอสำหรับคำนวณ kgCO₂e ตามมาตรฐาน GHG Protocol')

        missing_rows = []
        for m in missing[:4]:
            missing_rows.append({
                'type': 'box', 'layout': 'baseline', 'spacing': 'sm',
                'contents': [
                    {'type': 'text', 'text': '•', 'flex': 0,
                     'size': 'sm', 'color': '#b45309', 'weight': 'bold'},
                    {'type': 'text', 'text': str(m),
                     'size': 'xs', 'color': '#92400e',
                     'wrap': True, 'flex': 1},
                ],
            })

        return {
            'type': 'box', 'layout': 'vertical',
            'backgroundColor': '#fffbeb',
            'cornerRadius': '10px',
            'paddingAll': '12px', 'spacing': 'xs',
            'margin': 'lg',
            'contents': [
                {'type': 'box', 'layout': 'baseline', 'spacing': 'sm',
                 'contents': [
                     {'type': 'text', 'text': '⚠️', 'flex': 0, 'size': 'sm'},
                     {'type': 'text', 'text': 'ยังคำนวณ kgCO₂e ไม่ได้',
                      'size': 'sm', 'weight': 'bold',
                      'color': '#b45309', 'flex': 1},
                 ]},
                {'type': 'text',
                 'text': f'เพราะ: {reason}',
                 'size': 'xxs', 'color': '#78350f',
                 'wrap': True, 'margin': 'sm'},
                {'type': 'text', 'text': f'ต้องการข้อมูลเพิ่มสำหรับ{cat_th}:',
                 'size': 'xxs', 'color': '#92400e',
                 'weight': 'bold', 'margin': 'md'},
                {'type': 'box', 'layout': 'vertical',
                 'spacing': 'xs', 'margin': 'xs',
                 'contents': missing_rows},
            ],
        }

    def _kv_row(self, icon: str, label: str, value: str) -> dict:
        return {
            'type': 'box', 'layout': 'baseline', 'spacing': 'sm',
            'contents': [
                {'type': 'text', 'text': icon, 'flex': 0, 'size': 'sm'},
                {'type': 'text', 'text': f'{label}:', 'flex': 0,
                 'size': 'sm', 'weight': 'bold', 'color': '#0b1120'},
                {'type': 'text', 'text': value, 'flex': 1,
                 'size': 'sm', 'color': '#0b1120', 'wrap': True},
            ],
        }

    @staticmethod
    def _field_icon(label: str, unit: str, scope3_id: int) -> str:
        """Pick an emoji that fits the field label / unit / category."""
        lab = (label or '').lower()
        u = (unit or '').lower()
        if any(k in lab for k in ('ระยะทาง', 'distance', 'km')) or 'km' in u:
            return '🚗' if scope3_id in (4, 6, 7, 9) else '📏'
        if any(k in lab for k in ('น้ำหนัก', 'weight', 'kg', 'ตัน', 'tonne')) or u in ('kg', 'tonne'):
            return '⚖️'
        if any(k in lab for k in ('ราคา', 'cost', 'amount', 'thb', 'บาท', 'price')) or u in ('thb', 'baht', 'usd'):
            return '💰'
        if 'kwh' in u or any(k in lab for k in ('พลังงาน', 'energy', 'electric')):
            return '⚡'
        if any(k in lab for k in ('volume', 'litre', 'liter', 'l')) or u in ('l', 'litre'):
            return '🧴'
        return '🔹'

    # Maps the EntrySource enum stored on each EsgRecord to a Thai label
    # the success card surfaces under "ที่มาของข้อมูล:". Keep keys in sync
    # with EntrySource in models/esg/records.py.
    _SOURCE_TYPE_LABELS_TH = {
        'LINE_CHAT': 'รูปภาพเอกสาร',
        'LIFF_MANUAL': 'บันทึกด้วยตนเอง',
        'IMAGE': 'รูปภาพเอกสาร',
        'DOCUMENT': 'เอกสารของเสียจากระบบ',
        'SYSTEM': 'เอกสารของเสียจากระบบ',
    }

    @classmethod
    def _resolve_source_type_label(cls, entries: list) -> str:
        """
        Pick the Thai source-type label most representative of these entries.
        Falls back to "—" when nothing identifies the source.
        """
        if not entries:
            return '—'
        from collections import Counter
        votes: Counter = Counter()
        for e in entries:
            src = (e.get('entry_source') or '').upper()
            if not src:
                continue
            label = cls._SOURCE_TYPE_LABELS_TH.get(src)
            if label:
                votes[label] += 1
        if votes:
            return votes.most_common(1)[0][0]
        # Heuristic fallback: image evidence implies document image
        for e in entries:
            if e.get('evidence_image_url') or e.get('file_key'):
                return 'รูปภาพเอกสาร'
        return '—'

    @staticmethod
    def _format_record_id_list(record_ids: list, max_show: int = 8) -> str:
        # Dedupe while preserving first-seen order. With the new
        # esg_records storage one record = one row, but the synthesised
        # entry-dict list still carries one tuple per datapoint within
        # the same record — so the same id appears N times.
        seen: set = set()
        ids: list = []
        for rid in (record_ids or []):
            if rid is None or rid in seen:
                continue
            seen.add(rid)
            ids.append(rid)
        if not ids:
            return '—'
        formatted = [f'#{rid}' for rid in ids[:max_show]]
        if len(ids) > max_show:
            formatted.append(f'+{len(ids) - max_show}')
        return ', '.join(formatted)

    def _build_saved_flex(self, doc_id, scope3_id: int, name_th: str, name_en: str,
                         source_text: str, total_kg: float,
                         doc_total_amount: float, doc_currency: str,
                         period_total_kg: float,
                         record_count: int = 0,
                         record_ids: list = None) -> dict:
        """
        Message 2 of the per-category pair — save confirmation card.
        Header: ✓ บันทึกลงระบบสำเร็จ + Audit-Ready pill
        Body: หมวดหมู่ + Cat number, source TYPE, record count + IDs,
              doc total amount, doc CO₂e
        Footer: ดู Executive Dashboard / ดาวน์โหลด Excel / สร้างภาพ Social Report
        """
        doc = self._doc_no(doc_id)
        cat_label = f'Cat {scope3_id}: {name_en or name_th or "Scope 3"}'
        currency = (doc_currency or 'THB').upper()
        amt_text = (
            f'{float(doc_total_amount):,.0f} {currency}'
            if doc_total_amount and doc_total_amount > 0
            else '—'
        )
        # Show this document's CO2e (total_kg). Period aggregate is appended
        # in the body as a small subtitle so the user knows their running
        # total too.
        kg_text = (
            f'{total_kg:,.2f} kg'
            if total_kg and total_kg > 0 else '—'
        )
        period_subtitle = (
            f'รวมเดือนนี้: {period_total_kg:,.1f} kg'
            if period_total_kg and period_total_kg > 0 else ''
        )
        record_count_text = f'{record_count:,} รายการ' if record_count else '—'
        record_ids_text = self._format_record_id_list(record_ids)
        excel_url = f'{LIFF_BASE_URL}/liff/app/excel-download?cat={scope3_id}'
        social_url = f'{LIFF_BASE_URL}/liff/app/social-report?cat={scope3_id}'
        dashboard_url = f'{LIFF_BASE_URL}/liff/app/esg'

        return {
            'type': 'flex',
            'altText': f'{doc} — บันทึกลงระบบสำเร็จ ({cat_label})',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'body': {
                    'type': 'box', 'layout': 'vertical',
                    'paddingAll': '0px', 'spacing': 'none',
                    'contents': [
                        # ── Header bar (dark ink) ──
                        {'type': 'box', 'layout': 'horizontal',
                         'backgroundColor': '#0b1120',
                         'paddingAll': '14px', 'spacing': 'sm',
                         'alignItems': 'center',
                         'contents': [
                             {'type': 'text', 'text': '✓', 'flex': 0,
                              'size': 'lg', 'color': '#10b981', 'weight': 'bold'},
                             {'type': 'text', 'text': 'บันทึกลงระบบสำเร็จ',
                              'size': 'sm', 'color': '#ffffff',
                              'weight': 'bold', 'flex': 1},
                             # Audit-Ready pill
                             {'type': 'box', 'layout': 'vertical',
                              'backgroundColor': '#10b981',
                              'cornerRadius': '999px',
                              'paddingTop': '4px', 'paddingBottom': '4px',
                              'paddingStart': '10px', 'paddingEnd': '10px',
                              'flex': 0,
                              'contents': [
                                  {'type': 'text', 'text': 'Audit-Ready',
                                   'size': 'xxs', 'color': '#ffffff',
                                   'weight': 'bold'},
                              ]},
                         ]},
                        # ── Content ──
                        {'type': 'box', 'layout': 'vertical',
                         'paddingAll': '16px', 'spacing': 'sm',
                         'contents': [
                             {'type': 'text', 'text': 'หมวดหมู่',
                              'size': 'xs', 'color': '#64748b'},
                             {'type': 'text', 'text': cat_label,
                              'size': 'lg', 'color': '#0b1120',
                              'weight': 'bold', 'wrap': True},

                             # Source TYPE row (light-emerald background) — shows
                             # how the data was captured (image / manual / system).
                             {'type': 'box', 'layout': 'baseline',
                              'backgroundColor': '#ecfdf5',
                              'cornerRadius': '8px',
                              'paddingAll': '12px',
                              'margin': 'md', 'spacing': 'sm',
                              'contents': [
                                  {'type': 'text', 'text': 'ที่มาของข้อมูล:',
                                   'size': 'xs', 'color': '#475569', 'flex': 0},
                                  {'type': 'text', 'text': source_text or '—',
                                   'size': 'sm', 'color': '#047857',
                                   'weight': 'bold', 'flex': 1, 'align': 'end'},
                              ]},

                             # Record count row
                             {'type': 'box', 'layout': 'baseline',
                              'backgroundColor': '#f8fafc',
                              'cornerRadius': '8px',
                              'paddingAll': '12px',
                              'margin': 'sm', 'spacing': 'sm',
                              'contents': [
                                  {'type': 'text', 'text': 'จำนวนรายการ:',
                                   'size': 'xs', 'color': '#475569', 'flex': 0},
                                  {'type': 'text', 'text': record_count_text,
                                   'size': 'sm', 'color': '#0b1120',
                                   'weight': 'bold', 'flex': 1, 'align': 'end'},
                              ]},

                             # Saved record IDs row
                             {'type': 'box', 'layout': 'vertical',
                              'backgroundColor': '#f8fafc',
                              'cornerRadius': '8px',
                              'paddingAll': '12px',
                              'margin': 'sm', 'spacing': 'xs',
                              'contents': [
                                  {'type': 'text', 'text': 'บันทึก Records:',
                                   'size': 'xs', 'color': '#475569'},
                                  {'type': 'text', 'text': record_ids_text,
                                   'size': 'sm', 'color': '#0b1120',
                                   'weight': 'bold', 'wrap': True},
                              ]},

                             # Two-up: doc total amount | total kg
                             {'type': 'box', 'layout': 'horizontal',
                              'spacing': 'sm', 'margin': 'md',
                              'contents': [
                                  {'type': 'box', 'layout': 'vertical',
                                   'backgroundColor': '#f8fafc',
                                   'cornerRadius': '12px',
                                   'paddingAll': '14px', 'flex': 1,
                                   'alignItems': 'center', 'spacing': 'xs',
                                   'contents': [
                                       {'type': 'text', 'text': amt_text,
                                        'size': 'lg', 'color': '#0b1120',
                                        'weight': 'bold', 'align': 'center',
                                        'wrap': True},
                                       {'type': 'text', 'text': 'ราคารวม',
                                        'size': 'xs', 'color': '#64748b',
                                        'align': 'center'},
                                   ]},
                                  {'type': 'box', 'layout': 'vertical',
                                   'backgroundColor': '#ecfdf5',
                                   'cornerRadius': '12px',
                                   'paddingAll': '14px', 'flex': 1,
                                   'alignItems': 'center', 'spacing': 'xs',
                                   'contents': [
                                       {'type': 'text', 'text': kg_text,
                                        'size': 'xxl', 'color': '#10b981',
                                        'weight': 'bold', 'align': 'center'},
                                       {'type': 'text', 'text': 'รวม CO₂e',
                                        'size': 'xs', 'color': '#047857',
                                        'align': 'center'},
                                   ]},
                              ]},
                         ]},
                    ],
                },
                'footer': {
                    'type': 'box', 'layout': 'vertical',
                    'paddingAll': '16px', 'spacing': 'sm',
                    'contents': [
                        {'type': 'button', 'style': 'primary',
                         'color': '#0b1120', 'height': 'sm',
                         'action': {'type': 'uri',
                                    'label': 'ดู Executive Dashboard',
                                    'uri': dashboard_url}},
                        {'type': 'button', 'style': 'secondary',
                         'height': 'sm',
                         'action': {'type': 'uri',
                                    'label': 'ดาวน์โหลด Excel',
                                    'uri': excel_url}},
                        {'type': 'button', 'style': 'secondary',
                         'height': 'sm',
                         'action': {'type': 'uri',
                                    'label': 'สร้างภาพ Social Report',
                                    'uri': social_url}},
                    ],
                },
            },
        }

    def _build_category_flex(self, doc_id, scope3_id: int, name_th: str, name_en: str,
                             entries: list, total_tco2e: float) -> dict:
        """
        One card per matched Scope 3 category. Shows the cat number badge,
        the data fields extracted for this category, and the per-category
        tCO2e total. Designed to be skimmable in 3 seconds.
        """
        doc = self._doc_no(doc_id)

        # Build field rows from entries
        field_rows = []
        seen = set()
        for e in entries[:6]:  # cap at 6 fields per card
            label = e.get('field') or e.get('datapoint_name') or e.get('category', '')
            value = e.get('value', '')
            unit = e.get('unit', '')
            key = f"{label}|{value}|{unit}"
            if not label or key in seen:
                continue
            seen.add(key)
            try:
                value_text = f'{float(value):,.2f} {unit}'.strip()
            except (TypeError, ValueError):
                value_text = f'{value} {unit}'.strip() if value else '-'
            field_rows.append({
                'type': 'box', 'layout': 'horizontal', 'margin': 'xs',
                'contents': [
                    {'type': 'text', 'text': str(label)[:24],
                     'size': 'xs', 'color': '#64748b', 'flex': 4, 'wrap': True},
                    {'type': 'text', 'text': value_text[:20],
                     'size': 'xs', 'color': '#0b1120',
                     'weight': 'bold', 'flex': 4, 'align': 'end', 'wrap': True},
                ],
            })

        if not field_rows:
            field_rows = [{
                'type': 'text', 'text': 'อ่านได้บางส่วน — เปิด LIFF เพื่อกรอกเพิ่มเติม',
                'size': 'xs', 'color': '#64748b', 'wrap': True,
            }]

        tco2e_text = (
            f'{total_tco2e:.4f} tCO₂e' if total_tco2e and total_tco2e > 0
            else 'รอข้อมูลเพิ่ม'
        )

        return {
            'type': 'flex',
            'altText': f'{doc} — หมวด {scope3_id} {name_th or name_en}',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                    'paddingAll': '14px',
                    'contents': [
                        # Cat badge + name
                        {'type': 'box', 'layout': 'horizontal', 'spacing': 'md',
                         'contents': [
                             {'type': 'box', 'layout': 'vertical',
                              'backgroundColor': '#0b1120', 'cornerRadius': '8px',
                              'width': '40px', 'height': '40px',
                              'justifyContent': 'center',
                              'contents': [
                                  {'type': 'text', 'text': str(scope3_id),
                                   'color': '#a7f3d0', 'size': 'xl',
                                   'weight': 'bold', 'align': 'center'},
                              ]},
                             {'type': 'box', 'layout': 'vertical', 'flex': 1,
                              'contents': [
                                  {'type': 'text',
                                   'text': name_th or name_en or f'หมวด {scope3_id}',
                                   'size': 'sm', 'weight': 'bold',
                                   'color': '#0b1120', 'wrap': True},
                                  {'type': 'text', 'text': name_en or '',
                                   'size': 'xxs', 'color': '#94a3b8',
                                   'wrap': True, 'margin': 'xs'},
                              ]},
                         ]},
                        {'type': 'separator', 'margin': 'md'},
                        # Field rows
                        {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                         'margin': 'sm', 'contents': field_rows},
                        {'type': 'separator', 'margin': 'md'},
                        # tCO2e row
                        {'type': 'box', 'layout': 'horizontal', 'margin': 'sm',
                         'contents': [
                             {'type': 'text', 'text': 'คาร์บอน', 'size': 'sm',
                              'color': '#047857', 'weight': 'bold', 'flex': 2},
                             {'type': 'text', 'text': tco2e_text, 'size': 'sm',
                              'color': '#10b981', 'weight': 'bold',
                              'flex': 3, 'align': 'end'},
                         ]},
                    ],
                },
                'footer': {
                    'type': 'box', 'layout': 'vertical',
                    'paddingAll': '8px', 'paddingStart': '14px', 'paddingEnd': '14px',
                    'contents': [
                        {'type': 'text', 'text': f'จากเอกสาร {doc}',
                         'size': 'xxs', 'color': '#94a3b8', 'align': 'center'},
                    ],
                },
            },
        }

    def _build_completion_flex(self, doc_id, cat_groups: dict, total_tco2e: float) -> dict:
        """
        Final completion summary — emerald success header, list of matched
        cats, big total tCO2e, "View in LIFF" CTA.
        """
        doc = self._doc_no(doc_id)

        # Bullet list of matched categories
        from .scope3_assignment import SCOPE3_LABELS
        cat_lines = []
        for cid in sorted(cat_groups.keys()):
            lbl = SCOPE3_LABELS.get(int(cid), {})
            name = lbl.get('th') or lbl.get('en') or f'หมวด {cid}'
            cat_lines.append({
                'type': 'box', 'layout': 'horizontal', 'spacing': 'sm',
                'contents': [
                    {'type': 'text', 'text': '▸', 'flex': 0,
                     'size': 'sm', 'color': '#10b981', 'weight': 'bold'},
                    {'type': 'text', 'text': f'หมวด {cid} — {name}',
                     'size': 'xs', 'color': '#0b1120', 'flex': 1, 'wrap': True},
                ],
            })

        if not cat_lines:
            cat_lines = [{
                'type': 'text',
                'text': 'ไม่พบข้อมูล Scope 3 ในเอกสารนี้',
                'size': 'xs', 'color': '#64748b', 'wrap': True,
            }]

        liff_url = f'{LIFF_BASE_URL}/liff/app/history'
        total_text = f'{total_tco2e:.4f}' if total_tco2e and total_tco2e > 0 else '0.0000'

        return {
            'type': 'flex',
            'altText': f'เอกสาร {doc} ประมวลผลเสร็จสิ้น — รวม {total_text} tCO₂e',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'header': {
                    'type': 'box', 'layout': 'vertical',
                    'backgroundColor': '#10b981',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': '✓ ประมวลผลเสร็จสิ้น',
                         'color': '#ffffff', 'size': 'sm',
                         'weight': 'bold'},
                        {'type': 'text', 'text': f'เอกสาร {doc}',
                         'color': '#ffffff', 'size': 'xl',
                         'weight': 'bold', 'margin': 'sm'},
                    ],
                },
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text',
                         'text': f'พบข้อมูล {len(cat_groups)} หมวด:'
                                 if cat_groups else 'ผลการประมวลผล',
                         'size': 'sm', 'weight': 'bold', 'color': '#0b1120'},
                        {'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                         'margin': 'sm', 'contents': cat_lines},
                        {'type': 'separator', 'margin': 'lg'},
                        {'type': 'text', 'text': 'รวมทั้งสิ้น',
                         'size': 'xs', 'color': '#64748b', 'margin': 'md'},
                        {'type': 'box', 'layout': 'baseline', 'spacing': 'xs',
                         'contents': [
                             {'type': 'text', 'text': total_text,
                              'size': 'xxl', 'color': '#10b981', 'weight': 'bold'},
                             {'type': 'text', 'text': 'tCO₂e',
                              'size': 'sm', 'color': '#10b981', 'weight': 'bold'},
                         ]},
                    ],
                },
                'footer': {
                    'type': 'box', 'layout': 'vertical',
                    'paddingAll': '14px', 'spacing': 'sm',
                    'contents': [
                        {'type': 'button',
                         'action': {'type': 'uri', 'label': 'ดูทั้งหมดใน LIFF',
                                    'uri': liff_url},
                         'style': 'primary', 'color': '#0b1120', 'height': 'sm'},
                    ],
                },
            },
        }

    def _build_error_flex(self, doc_id, error_message: str) -> dict:
        doc = self._doc_no(doc_id)
        return {
            'type': 'flex',
            'altText': f'เอกสาร {doc} ประมวลผลไม่สำเร็จ',
            'contents': {
                'type': 'bubble', 'size': 'kilo',
                'header': {
                    'type': 'box', 'layout': 'vertical',
                    'backgroundColor': '#f59e0b',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': '⚠ ไม่สามารถประมวลผลได้',
                         'color': '#ffffff', 'size': 'sm', 'weight': 'bold'},
                        {'type': 'text', 'text': f'เอกสาร {doc}',
                         'color': '#ffffff', 'size': 'lg',
                         'weight': 'bold', 'margin': 'sm'},
                    ],
                },
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'sm',
                    'paddingAll': '16px',
                    'contents': [
                        {'type': 'text', 'text': str(error_message)[:200],
                         'size': 'sm', 'color': '#0b1120', 'wrap': True},
                        {'type': 'text',
                         'text': 'กรุณาถ่ายให้ชัดขึ้นแล้วลองส่งใหม่อีกครั้ง',
                         'size': 'xs', 'color': '#64748b',
                         'wrap': True, 'margin': 'md'},
                    ],
                },
            },
        }

    def _group_entries_by_scope3(self, entries: list) -> dict:
        """
        Group entries by their Scope 3 category id (1..15). Falls back to
        the assign_scope3_category heuristic when an entry has no
        category_id (e.g. legacy or fallback path).
        """
        from .scope3_assignment import assign_scope3_category
        groups: dict[int, list] = {}
        for e in entries:
            cid = e.get('scope3_category_id')
            if not cid:
                # Resolve from DB / category name / unit
                cat_id_db = e.get('category_id') or e.get('id')
                resolved, _, _, _ = assign_scope3_category(
                    self.db,
                    category_name=e.get('category') or e.get('category_name'),
                    category_id=cat_id_db,
                    unit=e.get('unit'),
                    raw_input=None,
                )
                cid = resolved
            if not cid:
                continue
            try:
                key = int(cid)
            except (TypeError, ValueError):
                continue
            # Stamp the resolved id back onto the entry so downstream
            # reuse doesn't re-resolve.
            e['scope3_category_id'] = key
            groups.setdefault(key, []).append(e)
        return groups

    def _get_category_period_aggregate(self, organization_id: int, scope3_cat_id: int,
                                       year: int, month: int) -> tuple[int, float]:
        """
        Returns (doc_count, total_kg) for entries in the given org +
        scope3 category, for the given calendar month. Used by the
        save-confirmation card to show "15 เอกสารที่พบ / 342.5 kg".
        """
        try:
            from sqlalchemy import func, extract
            from ...models.esg.data_hierarchy import EsgDataCategory
            row = (
                self.db.query(
                    func.count(EsgRecord.id).label('cnt'),
                    func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0).label('tco2e'),
                )
                .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id)
                .filter(
                    EsgRecord.organization_id == organization_id,
                    EsgRecord.is_active == True,
                    EsgDataCategory.is_scope3 == True,
                    EsgDataCategory.scope3_category_id == int(scope3_cat_id),
                    extract('year', EsgRecord.entry_date) == year,
                    extract('month', EsgRecord.entry_date) == month,
                )
                .one()
            )
            cnt = int(row.cnt or 0)
            kg = float(row.tco2e or 0) * 1000.0  # tCO2e → kgCO2e
            return cnt, kg
        except Exception:
            logger.exception('[LINE] failed to compute period aggregate')
            return 0, 0.0

    @staticmethod
    def _summarize_source(entries: list) -> str:
        """Build a short '15.2 km (Taxi)' style source string from entries."""
        # Pick the most informative numeric field
        for e in entries:
            v = e.get('value')
            u = (e.get('unit', '') or '').strip()
            label = (e.get('field') or e.get('datapoint_name') or '').strip()
            if v is None or u == '':
                continue
            try:
                num = f'{float(v):,.1f}'
            except (TypeError, ValueError):
                num = str(v)
            if label:
                return f'{num} {u} ({label})'
            return f'{num} {u}'
        return '—'

    def _dispatch_extraction_messages(self, token: str, line_user_id: str,
                                      reply_token: str, doc_id, entries: list,
                                      organization_id: int = None,
                                      refs: dict = None):
        """
        Per-category fan-out:
          For each Scope 3 cat detected →
            PUSH 1) "ผลการวิเคราะห์เอกสาร"  (raw extracted fields)
            PUSH 2) "บันทึกลงระบบสำเร็จ"   (status + dashboard buttons)
          Then REPLY (or PUSH fallback) the grand-total completion card.
        """
        from datetime import datetime, timezone
        from .scope3_assignment import SCOPE3_LABELS

        groups = self._group_entries_by_scope3(entries)
        cat_totals: dict[int, float] = {}
        grand_total = 0.0

        now = datetime.now(timezone.utc)
        year, month = now.year, now.month

        for cid in sorted(groups.keys()):
            cat_entries = groups[cid]
            tco2e_total = 0.0
            for e in cat_entries:
                v = e.get('calculated_tco2e') or 0
                try:
                    tco2e_total += float(v or 0)
                except (TypeError, ValueError):
                    pass
            cat_totals[cid] = tco2e_total
            grand_total += tco2e_total

            lbl = SCOPE3_LABELS.get(cid, {})
            kg_total_for_cat = tco2e_total * 1000.0  # tCO2e → kgCO2e

            # ── Message 1: analysis result (raw extracted fields + diagnostics) ──
            analysis_card = self._build_analysis_flex(
                doc_id=doc_id,
                scope3_id=cid,
                refs=refs or {},
                entries=cat_entries,
                total_kg=kg_total_for_cat,
            )
            if line_user_id:
                self._send_push_message(token, line_user_id, [analysis_card])

            # ── Message 2: save confirmation + dashboard CTAs ──
            _doc_count, period_kg = (0, 0.0)
            if organization_id:
                _doc_count, period_kg = self._get_category_period_aggregate(
                    organization_id, cid, year, month
                )
            doc_total_amount = (refs or {}).get('total_amount')
            doc_currency = (refs or {}).get('currency') or 'THB'
            # Collect record IDs that actually persisted for this
            # category. With the new esg_records storage, one record =
            # one row but the synthesised entry-dict list carries one
            # tuple per datapoint within that record, so we dedupe
            # before counting + listing.
            cat_record_ids: list = []
            _seen_ids: set = set()
            for e in cat_entries:
                rid = e.get('id')
                if rid is None or rid in _seen_ids:
                    continue
                _seen_ids.add(rid)
                cat_record_ids.append(rid)
            saved_card = self._build_saved_flex(
                doc_id=doc_id,
                scope3_id=cid,
                name_th=lbl.get('th', ''),
                name_en=lbl.get('en', ''),
                source_text=self._resolve_source_type_label(cat_entries),
                total_kg=kg_total_for_cat,
                doc_total_amount=doc_total_amount,
                doc_currency=doc_currency,
                period_total_kg=period_kg,
                record_count=len(cat_record_ids),
                record_ids=cat_record_ids,
            )
            if line_user_id:
                self._send_push_message(token, line_user_id, [saved_card])
                logger.info(f"[LINE] Pushed cat {cid} pair (analysis + saved) — {len(cat_entries)} fields")

        # Final completion card via REPLY (fallback to PUSH if expired)
        completion = self._build_completion_flex(doc_id, cat_totals, grand_total)
        replied = self._send_reply_raw(token, reply_token, [completion])
        if replied:
            logger.info(f"[LINE] completion via reply (doc #{doc_id}, total={grand_total:.4f} tCO2e)")
        else:
            logger.warning(f"[LINE] reply failed for completion — falling back to push")
            if line_user_id:
                pushed = self._send_push_message(token, line_user_id, [completion])
                if pushed:
                    logger.info(f"[LINE] completion via push fallback (doc #{doc_id})")
                else:
                    logger.error(f"[LINE] completion FAILED (both reply and push failed) — doc #{doc_id}")

    def _send_reply_raw(self, token: str, reply_token: str, messages: list) -> bool:
        """Send reply messages. Returns True on success, False on any failure
        so the caller can decide whether to fall back to push."""
        if not token:
            logger.warning("[LINE] _send_reply_raw: missing token")
            return False
        if not reply_token:
            logger.warning("[LINE] _send_reply_raw: missing reply_token")
            return False
        # Simulator mode: log the reply instead of sending to LINE
        if reply_token == '00000000000000000000000000000000' or reply_token.startswith('simulator'):
            logger.info(f"[SIMULATOR] Would reply with {len(messages)} message(s)")
            for i, msg in enumerate(messages):
                msg_type = msg.get('type', '?')
                if msg_type == 'text':
                    logger.info(f"[SIMULATOR] Reply[{i}]: TEXT = {msg.get('text', '')[:200]}")
                elif msg_type == 'flex':
                    logger.info(f"[SIMULATOR] Reply[{i}]: FLEX alt={msg.get('altText', '')[:100]}")
                else:
                    logger.info(f"[SIMULATOR] Reply[{i}]: {msg_type}")
            return True
        try:
            import urllib.request
            data = json.dumps({'replyToken': reply_token, 'messages': messages}).encode('utf-8')
            req = urllib.request.Request('https://api.line.me/v2/bot/message/reply', data=data,
                                        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status if hasattr(resp, 'status') else resp.getcode()
                logger.info(f"[LINE] reply OK status={status} count={len(messages)}")
                return True
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                body = ''
            logger.error(f"[LINE] reply HTTP {e.code} {e.reason} body={body}")
            return False
        except Exception as e:
            logger.error(f"[LINE] reply failed: {e}")
            return False

    def _send_push_message(self, token: str, to_user_id: str, messages: list) -> bool:
        """Push messages to a LINE user. Returns True on success."""
        if not token:
            logger.warning("[LINE] _send_push_message: missing token (set ESG_LINE_CHANNEL_ACCESS_TOKEN)")
            return False
        if not to_user_id:
            logger.warning("[LINE] _send_push_message: missing to_user_id")
            return False
        if not messages:
            return False
        # Simulator mode
        if to_user_id.startswith('simulator') or to_user_id == 'U' + '0' * 32:
            logger.info(f"[SIMULATOR] Would push {len(messages)} message(s) to {to_user_id[:12]}")
            for i, msg in enumerate(messages):
                msg_type = msg.get('type', '?')
                if msg_type == 'flex':
                    logger.info(f"[SIMULATOR] Push[{i}]: FLEX alt={msg.get('altText', '')[:100]}")
                else:
                    logger.info(f"[SIMULATOR] Push[{i}]: {msg_type}")
            return True
        try:
            import urllib.request
            data = json.dumps({'to': to_user_id, 'messages': messages}).encode('utf-8')
            req = urllib.request.Request(
                'https://api.line.me/v2/bot/message/push',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}',
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status if hasattr(resp, 'status') else resp.getcode()
                logger.info(f"[LINE] push OK status={status} to={to_user_id[:12]} count={len(messages)}")
                return True
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                body = ''
            logger.error(f"[LINE] push HTTP {e.code} {e.reason} to={to_user_id[:12]} body={body}")
            return False
        except Exception as e:
            logger.error(f"[LINE] push failed: {e}")
            return False
