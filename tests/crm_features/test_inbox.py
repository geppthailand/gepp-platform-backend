"""
Unit tests for Sprint 10 P1 Conversation Inbox.

Coverage:
  - inbox_service.generate_thread_token format + uniqueness
  - inbox_service.reply_to_for() builds reply+<token>@<domain>
  - inbox_service.ensure_conversation_for_delivery() inserts row + seed message
  - inbox_service.send_reply()
      • happy path: invokes Mandrill, inserts outbound message, bumps timestamps
      • blocked when status='closed'
      • uses last inbound from_email as recipient when available
  - inbox_service.insert_inbound_message()
      • inserts row when token matches; bumps unread_count; reopens closed convs
      • returns None when token does not match any conversation
  - mailchimp_inbound_handler._extract_thread_token() pulls reply+<tok>@gepp.me
      from msg.email / msg.to / msg.cc
  - mailchimp_inbound_handler.handle_mailchimp_inbound_webhook()
      • rejects bad signature (401)
      • processes events and returns 200 with counters

Run:
    python -m pytest tests/crm_features/test_inbox.py -v
"""

import sys
import os
import json
import hmac
import base64
import hashlib
import unittest
from unittest.mock import MagicMock, patch

_OWNS_EXCEPTION_BINDING = True  # opt out of conftest exception rebinding

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # v3/backend/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Mock db helper (mirrors fetchone/scalar/rowcount semantics) ─────────────

class _FakeResult:
    def __init__(self, *, rows=None, scalar=None, rowcount=0):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class _ScriptedDB:
    """A test double for SQLAlchemy Session.

    Drive db.execute() side-effects via a sequence of _FakeResult objects, or
    via a callable mapping sql_text -> _FakeResult.
    """

    def __init__(self, responder):
        self.responder = responder
        self.executed = []  # list of (sql_text, params) tuples
        self.committed = 0

    def execute(self, stmt, params=None):
        sql_text = str(stmt)
        self.executed.append((sql_text, params))
        return self.responder(sql_text, params or {})

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass


# ── Tests ────────────────────────────────────────────────────────────────────

class TestTokenHelpers(unittest.TestCase):
    def test_generate_thread_token_unique_and_safe_chars(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        tok1 = inbox_service.generate_thread_token()
        tok2 = inbox_service.generate_thread_token()
        self.assertNotEqual(tok1, tok2)
        self.assertGreaterEqual(len(tok1), 24)
        # URL-safe: only A-Z, a-z, 0-9, -, _
        for ch in tok1:
            self.assertTrue(ch.isalnum() or ch in ('-', '_'),
                            f"token contains unsafe char: {ch!r}")

    def test_reply_to_uses_env_domain(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        with patch.dict(os.environ, {'CRM_INBOUND_DOMAIN': 'example.test'}, clear=False):
            addr = inbox_service.reply_to_for('abc123')
            self.assertEqual(addr, 'reply+abc123@example.test')

    def test_reply_to_defaults_to_gepp_me(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        prev = os.environ.pop('CRM_INBOUND_DOMAIN', None)
        try:
            addr = inbox_service.reply_to_for('xyz')
            self.assertEqual(addr, 'reply+xyz@gepp.me')
        finally:
            if prev is not None:
                os.environ['CRM_INBOUND_DOMAIN'] = prev


class TestEnsureConversationForDelivery(unittest.TestCase):
    def test_idempotent_returns_existing_thread_token(self):
        """If a delivery_id already has an outbound message → reuse existing conv."""
        from GEPPPlatform.services.admin.crm import inbox_service

        def responder(sql, params):
            if 'FROM crm_conversation_messages m' in sql and 'm.delivery_id = :did' in sql:
                return _FakeResult(rows=[(42, 'EXISTING_TOK')])
            self.fail(f"unexpected SQL: {sql[:80]}")

        db = _ScriptedDB(responder)
        result = inbox_service.ensure_conversation_for_delivery(
            db,
            delivery_id=99,
            organization_id=1,
            user_location_id=2,
            lead_id=None,
            recipient_email='r@example.com',
            subject='Hi',
        )
        self.assertEqual(result['id'], 42)
        self.assertEqual(result['thread_token'], 'EXISTING_TOK')
        self.assertIn('reply+EXISTING_TOK@', result['reply_to'])

    def test_creates_new_conversation_when_none_exists(self):
        from GEPPPlatform.services.admin.crm import inbox_service

        # Order of SQL: SELECT existing → INSERT conv (RETURNING id) → INSERT msg → UPDATE last_message_at
        scripts = iter([
            _FakeResult(rows=[]),                  # no existing
            _FakeResult(scalar=777),               # new conv id
            _FakeResult(rowcount=1),               # insert msg
            _FakeResult(rowcount=1),               # update last_message_at
        ])
        db = _ScriptedDB(lambda sql, params: next(scripts))

        result = inbox_service.ensure_conversation_for_delivery(
            db,
            delivery_id=100,
            organization_id=1,
            user_location_id=2,
            lead_id=None,
            recipient_email='r@example.com',
            subject='Welcome',
        )
        self.assertEqual(result['id'], 777)
        self.assertTrue(result['thread_token'])
        self.assertTrue(result['reply_to'].startswith('reply+'))
        # 4 SQL ops executed
        self.assertEqual(len(db.executed), 4)


class TestSendReply(unittest.TestCase):
    def _setup_db_for_reply(self, *, conv_row, last_inbound=None, seed_outbound=None):
        """Return _ScriptedDB scripted for the read order in send_reply."""
        # send_reply executes:
        #   1. SELECT conv
        #   2. SELECT last_inbound (from_email)
        #   3. (if no inbound) SELECT seed outbound (to_email)
        #   4. INSERT new outbound message
        #   5. UPDATE conversations (last_message_at, updated_date)
        responses = [_FakeResult(rows=[conv_row])]
        if last_inbound is not None:
            responses.append(_FakeResult(rows=[(last_inbound,)]))
        else:
            responses.append(_FakeResult(rows=[]))
            responses.append(_FakeResult(rows=[(seed_outbound,)] if seed_outbound else []))
        responses.append(_FakeResult(rowcount=1))  # INSERT msg
        responses.append(_FakeResult(rowcount=1))  # UPDATE conv
        it = iter(responses)
        return _ScriptedDB(lambda sql, params: next(it))

    def test_send_reply_uses_last_inbound_from_address(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        from GEPPPlatform.exceptions import BadRequestException  # noqa: F401

        conv_row = (1, 'TOK', 'Welcome', 'open', None, None)
        db = self._setup_db_for_reply(conv_row=conv_row, last_inbound='reply-from@external.com')

        with patch.object(inbox_service.crm_service, 'send_via_email_lambda',
                          return_value={'success': True, 'mandrill_message_id': 'mid_123'}) as mock_send:
            res = inbox_service.send_reply(
                db, conv_id=1, org_id=42,
                body_html='<p>thanks</p>',
                from_user={'email': 'admin@gepp.me'},
            )

        self.assertTrue(res['sent'])
        self.assertEqual(res['mandrillMessageId'], 'mid_123')
        self.assertEqual(res['recipient'], 'reply-from@external.com')

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs['to_email'], 'reply-from@external.com')
        self.assertIn('reply+TOK@', kwargs['reply_to'])
        self.assertEqual(kwargs['subject'], 'Re: Welcome')
        # metadata includes conversation_id + thread_token for inbound matching
        self.assertEqual(kwargs['metadata']['conversation_id'], '1')
        self.assertEqual(kwargs['metadata']['thread_token'], 'TOK')

    def test_send_reply_falls_back_to_original_recipient(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        conv_row = (1, 'TOK', 'Welcome', 'open', None, None)
        db = self._setup_db_for_reply(conv_row=conv_row, last_inbound=None,
                                      seed_outbound='lead@example.com')

        with patch.object(inbox_service.crm_service, 'send_via_email_lambda',
                          return_value={'success': True, 'mandrill_message_id': 'mid_456'}):
            res = inbox_service.send_reply(
                db, conv_id=1, org_id=42, body_html='<p>hello</p>')

        self.assertEqual(res['recipient'], 'lead@example.com')

    def test_send_reply_rejects_closed_conversation(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        from GEPPPlatform.exceptions import BadRequestException

        conv_row = (1, 'TOK', 'Welcome', 'closed', None, None)
        responses = iter([_FakeResult(rows=[conv_row])])
        db = _ScriptedDB(lambda sql, params: next(responses))

        with self.assertRaises(BadRequestException):
            inbox_service.send_reply(db, conv_id=1, org_id=42, body_html='<p>nope</p>')

    def test_send_reply_rejects_missing_body(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        from GEPPPlatform.exceptions import BadRequestException
        db = _ScriptedDB(lambda sql, params: _FakeResult())
        with self.assertRaises(BadRequestException):
            inbox_service.send_reply(db, conv_id=1, org_id=42, body_html='')


class TestInsertInboundMessage(unittest.TestCase):
    def test_no_match_returns_none(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        db = _ScriptedDB(lambda sql, params: _FakeResult(rows=[]))
        result = inbox_service.insert_inbound_message(
            db,
            thread_token='UNKNOWN',
            from_email='a@b.com', to_email='x@y.com',
            subject='S', body_html='<p>h</p>', body_plain='h',
            mandrill_message_id='mid',
        )
        self.assertIsNone(result)

    def test_match_inserts_and_bumps_counters(self):
        from GEPPPlatform.services.admin.crm import inbox_service
        responses = iter([
            _FakeResult(rows=[(55, 1, 3, 4)]),  # conversation lookup
            _FakeResult(scalar=999),             # INSERT message → id
            _FakeResult(rowcount=1),             # UPDATE conversation
        ])
        db = _ScriptedDB(lambda sql, params: next(responses))

        with patch.object(inbox_service.crm_service, 'emit_event') as mock_emit:
            msg_id = inbox_service.insert_inbound_message(
                db,
                thread_token='TOK',
                from_email='customer@example.com',
                to_email='reply+TOK@gepp.me',
                subject='Re: Welcome',
                body_html='<p>thanks!</p>',
                body_plain='thanks!',
                mandrill_message_id='mid_in_1',
            )

        self.assertEqual(msg_id, 999)
        # email_reply_received emitted for analytics
        mock_emit.assert_called_once()
        emit_kwargs = mock_emit.call_args.kwargs
        self.assertEqual(emit_kwargs['event_type'], 'email_reply_received')
        self.assertEqual(emit_kwargs['event_category'], 'email')


class TestExtractThreadToken(unittest.TestCase):
    def test_extract_from_envelope_email(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        tok = h._extract_thread_token({'email': 'reply+ABC12345xyz@gepp.me'})
        self.assertEqual(tok, 'ABC12345xyz')

    def test_extract_from_to_list_tuple_form(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        msg = {'to': [['reply+XYZ_456abcd@gepp.me', 'GEPP Inbox']]}
        self.assertEqual(h._extract_thread_token(msg), 'XYZ_456abcd')

    def test_extract_from_to_list_dict_form(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        msg = {'to': [{'email': 'reply+dictform-789012@gepp.me'}]}
        self.assertEqual(h._extract_thread_token(msg), 'dictform-789012')

    def test_returns_none_when_no_reply_plus(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        msg = {'email': 'someone@gepp.me', 'to': [['noreply@gepp.me', 'X']]}
        self.assertIsNone(h._extract_thread_token(msg))

    def test_case_insensitive_match(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        msg = {'email': 'REPLY+UpperCase1234@GEPP.ME'}
        self.assertEqual(h._extract_thread_token(msg), 'UpperCase1234')


class TestInboundWebhookSignature(unittest.TestCase):
    def _make_event(self, body, signature, *, path='/api/webhooks/mailchimp/inbound',
                    domain='api.gepp.me'):
        return {
            'body': body,
            'headers': {'x-mandrill-signature': signature, 'host': domain},
            'rawPath': path,
            'requestContext': {'domainName': domain},
        }

    def _compute_signature(self, key, url, form_dict):
        signed = url
        for k in sorted(form_dict.keys()):
            for v in form_dict[k]:
                signed += k + v
        mac = hmac.new(key.encode('utf-8'), signed.encode('utf-8'), hashlib.sha1)
        return base64.b64encode(mac.digest()).decode('utf-8')

    def test_invalid_signature_returns_401(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        with patch.dict(os.environ, {'MAILCHIMP_WEBHOOK_KEY': 'k1'}, clear=False):
            evt = self._make_event(body='mandrill_events=%5B%5D',
                                   signature='wrong-signature')
            db = MagicMock()
            res = h.handle_mailchimp_inbound_webhook(evt, db)
            self.assertEqual(res['statusCode'], 401)

    def test_valid_signature_processes_events(self):
        from GEPPPlatform.services.webhooks import mailchimp_inbound_handler as h
        key = 'TESTKEY'
        url = 'https://api.gepp.me/api/webhooks/mailchimp/inbound'
        payload = json.dumps([{
            'event': 'inbound',
            'msg': {
                'email': 'reply+VALID_TOK@gepp.me',
                'from_email': 'sender@external.com',
                'subject': 'Re: Hi',
                'html': '<p>thanks</p>',
                'text': 'thanks',
                '_id': 'mid_99',
            }
        }])
        # parse_qs needs proper URL-encoded form
        from urllib.parse import urlencode
        body = urlencode({'mandrill_events': payload})
        form = {'mandrill_events': [payload]}

        sig = self._compute_signature(key, url, form)
        evt = self._make_event(body=body, signature=sig)

        with patch.dict(os.environ, {'MAILCHIMP_WEBHOOK_KEY': key}, clear=False), \
             patch.object(h, '_process_inbound_event', return_value=('inserted', 1)) as mock_proc:
            db = MagicMock()
            res = h.handle_mailchimp_inbound_webhook(evt, db)

        self.assertEqual(res['statusCode'], 200)
        body_json = json.loads(res['body'])
        self.assertEqual(body_json['inserted'], 1)
        self.assertEqual(body_json['errors'], 0)
        mock_proc.assert_called_once()


class TestInboxHandlerDispatch(unittest.TestCase):
    """Verify dispatch_inbox_subroute routes to the right service method."""

    def test_reply_subroute_calls_send_reply(self):
        from GEPPPlatform.services.admin.crm import inbox_handlers
        with patch.object(inbox_handlers.inbox_service, 'send_reply',
                          return_value={'sent': True}) as mock_send:
            inbox_handlers.dispatch_inbox_subroute(
                resource_id=10, sub_path='reply', method='POST',
                db=MagicMock(),
                data={'bodyHtml': '<p>hello</p>', 'subject': 'Re: X'},
                query_params={},
                current_user={'organization_id': 42, 'email': 'admin@gepp.me'},
            )
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs['body_html'], '<p>hello</p>')
        self.assertEqual(kwargs['subject'], 'Re: X')

    def test_mark_read_subroute(self):
        from GEPPPlatform.services.admin.crm import inbox_handlers
        with patch.object(inbox_handlers.inbox_service, 'mark_read',
                          return_value={'id': 10, 'unreadCount': 0}) as mock_mark:
            res = inbox_handlers.dispatch_inbox_subroute(
                resource_id=10, sub_path='mark-read', method='POST',
                db=MagicMock(), data={}, query_params={},
                current_user={'organization_id': 42},
            )
        self.assertEqual(res['unreadCount'], 0)
        mock_mark.assert_called_once_with(unittest.mock.ANY, 10, 42)

    def test_status_subroute_rejects_missing_status(self):
        from GEPPPlatform.services.admin.crm import inbox_handlers
        from GEPPPlatform.exceptions import BadRequestException
        with self.assertRaises(BadRequestException):
            inbox_handlers.dispatch_inbox_subroute(
                resource_id=10, sub_path='status', method='POST',
                db=MagicMock(), data={}, query_params={},
                current_user={'organization_id': 42},
            )

    def test_unknown_subroute_404s(self):
        from GEPPPlatform.services.admin.crm import inbox_handlers
        from GEPPPlatform.exceptions import NotFoundException
        with self.assertRaises(NotFoundException):
            inbox_handlers.dispatch_inbox_subroute(
                resource_id=10, sub_path='unknown', method='POST',
                db=MagicMock(), data={}, query_params={},
                current_user={'organization_id': 42},
            )

    def test_missing_org_id_rejects(self):
        from GEPPPlatform.services.admin.crm import inbox_handlers
        from GEPPPlatform.exceptions import BadRequestException
        with self.assertRaises(BadRequestException):
            inbox_handlers.dispatch_inbox_subroute(
                resource_id=10, sub_path='mark-read', method='POST',
                db=MagicMock(), data={}, query_params={},
                current_user={},  # no organization_id
            )


if __name__ == '__main__':
    unittest.main()
