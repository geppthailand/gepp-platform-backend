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
from ...models.esg.data_entries import EsgDataEntry, EntrySource, EntryStatus
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
        entry = self.db.query(EsgDataEntry).filter(
            EsgDataEntry.id == entry_id, EsgDataEntry.is_active == True,
        ).first()
        if not entry:
            self._send_text_reply(org.line_channel_token, reply_token, 'ไม่พบข้อมูลนี้')
            return {'status': 'error', 'reason': 'Entry not found'}

        entry.status = EntryStatus.VERIFIED
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

        count = self.db.query(EsgDataEntry).filter(
            EsgDataEntry.id.in_(entry_ids),
            EsgDataEntry.is_active == True,
        ).update({EsgDataEntry.status: EntryStatus.VERIFIED}, synchronize_session='fetch')
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

        # AI text extraction → create entry → tCO2e → Flex reply
        extraction = EsgOrganizationDataExtraction(
            organization_id=org_id,
            channel='line', type='text',
            source_user_id=line_msg.line_user_id,
            source_message_id=line_msg.line_message_id,
            raw_content=text, processing_status='pending',
        )
        self.db.add(extraction)
        self.db.flush()

        try:
            from .esg_extraction_service import EsgExtractionService
            svc = EsgExtractionService(self.db)
            svc.process_extraction(extraction.id)
            self.db.refresh(extraction)
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")

        entry = self._create_entry_from_extraction(extraction, org_id, line_msg.line_user_id)
        if entry:
            flex = self._build_result_flex(entry)
            self._send_reply_raw(token, line_msg.line_reply_token, [flex])
        else:
            self._send_text_reply(token, line_msg.line_reply_token,
                                  'ได้รับข้อมูลแล้ว แต่ไม่สามารถสกัดตัวเลขได้ กรุณากรอกผ่าน LIFF')

        line_msg.processing_status = extraction.processing_status
        self.db.flush()
        return {'status': 'success', 'type': 'text_extraction', 'entry_id': entry['id'] if entry else None}

    # ---- IMAGE: OCR → tCO2e → Flex Message ----

    def _process_image(self, line_msg, message: Dict, org_id: int, token: str) -> Dict:
        try:
            message_id = message.get('id')
            logger.info(f"----------- IMAGE PROCESSING START -----------")
            logger.info(f"[IMG] msg_id={message_id}, org_id={org_id}, user={line_msg.line_user_id[:12] if line_msg.line_user_id else '?'}")

            # Simulator support: use base64 image from _simulator metadata instead of LINE CDN
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

            # Use Gemini vision pipeline for full extraction
            logger.info(f"[IMG] Starting Gemini extraction...")
            from .esg_image_extraction_service import EsgImageExtractionService
            extraction_svc = EsgImageExtractionService(self.db)
            result = extraction_svc.extract_from_image(
                s3_url=s3_url,
                org_id=org_id,
                line_user_id=line_msg.line_user_id,
                message_id=line_msg.line_message_id,
            )
            logger.info(f"[IMG] Extraction result: success={result.get('success')}, matches={result.get('match_count', 0)}, entries={len(result.get('entries', []))}")

            if result.get('success') and result.get('entries'):
                logger.info(f"[IMG] Building Flex card for {len(result['entries'])} entries, {len(result.get('records', []))} records...")
                flex = extraction_svc.build_result_flex_card(
                    entries=result['entries'],
                    refs=result.get('refs', {}),
                    extraction_id=result['extraction_id'],
                    document_summary=result.get('document_summary', ''),
                    records=result.get('records', []),
                )
                logger.info(f"[IMG] Flex card built, sending reply...")
                self._send_reply_raw(token, line_msg.line_reply_token, [flex])
                logger.info(f"[IMG] Reply sent!")
            else:
                err_msg = result.get('message', 'กรุณาถ่ายใหม่ให้ชัดขึ้น')
                logger.info(f"[IMG] No entries, sending error: {err_msg}")
                self._send_text_reply(token, line_msg.line_reply_token,
                                      f"ไม่สามารถอ่านข้อมูลจากรูปได้\n{err_msg}")

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
        # filter (EsgDataEntry.user_id = current LIFF user) returns rows.
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

        entry = EsgDataEntry(
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
            entry_source=EntrySource.LINE_CHAT,
            status=EntryStatus.PENDING_VERIFY,
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

    def _send_reply_raw(self, token: str, reply_token: str, messages: list):
        if not token or not reply_token:
            return
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
            return
        try:
            import urllib.request
            data = json.dumps({'replyToken': reply_token, 'messages': messages}).encode('utf-8')
            req = urllib.request.Request('https://api.line.me/v2/bot/message/reply', data=data,
                                        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.error(f"Reply failed: {e}")
