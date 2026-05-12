"""
Unit tests for public lead capture endpoint (Sprint 9 Phase 2).

Coverage:
  - reCAPTCHA branch: absent secret → dev-mode accepts
  - reCAPTCHA branch: secret set + token missing → 400
  - reCAPTCHA branch: token rejected → 400
  - Rate-limit: first request creates row
  - Rate-limit: limit reached → 429
  - Rate-limit: window expired → resets
  - Unknown public_form_key → 404
  - Happy path → {ok: True, leadId}

Run:
    python -m pytest tests/crm_features/test_public_lead_capture.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

_OWNS_EXCEPTION_BINDING = True  # opt out of conftest exception rebinding (see tests/conftest.py)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─── Stubs ────────────────────────────────────────────────────────────────────

def _stub(name, base=None):
    m = base or MagicMock()
    m.__spec__ = None
    sys.modules[name] = m
    return m


for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.services",
    "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
    "GEPPPlatform.services.public",
    "sqlalchemy",
    "sqlalchemy.orm",
]:
    _stub(_pkg)

_sa_mod = MagicMock()
_sa_mod.text = lambda s: s
sys.modules["sqlalchemy"] = _sa_mod


class _NotFoundException(Exception):
    def __init__(self, msg="not found", status_code=404, error_code="NOT_FOUND"):
        self.message = msg; self.status_code = status_code
        super().__init__(msg)

class _BadRequestException(Exception):
    def __init__(self, msg="bad request", status_code=400, error_code="BAD_REQUEST"):
        self.message = msg; self.status_code = status_code
        super().__init__(msg)

class _APIException(Exception):
    def __init__(self, msg="error", status_code=500, error_code="ERROR"):
        self.message = msg; self.status_code = status_code
        super().__init__(msg)

_exc_mod = MagicMock()
_exc_mod.NotFoundException = _NotFoundException
_exc_mod.BadRequestException = _BadRequestException
_exc_mod.APIException = _APIException
sys.modules["GEPPPlatform.exceptions"] = _exc_mod

# Stub lead_service so we can control it.
_lead_svc_stub = MagicMock()
sys.modules["GEPPPlatform.services.admin.crm.lead_service"] = _lead_svc_stub
# Also wire the relative import path the handler uses.
_crm_pkg = sys.modules["GEPPPlatform.services.admin.crm"]
_crm_pkg.lead_service = _lead_svc_stub

# Load the real module with its full dotted name so relative imports resolve.
_FULL_NAME = "GEPPPlatform.services.public.leads_capture_handler"
_spec = _ilu.spec_from_file_location(
    _FULL_NAME,
    os.path.join(_ROOT, "GEPPPlatform/services/public/leads_capture_handler.py"),
)
_mod = _ilu.module_from_spec(_spec)
sys.modules[_FULL_NAME] = _mod
_spec.loader.exec_module(_mod)

# Wire real exception classes into the loaded module.
_mod.BadRequestException = _BadRequestException
_mod.NotFoundException   = _NotFoundException
# Tell conftest.py NOT to rebind these exception names — we own them.
_mod._OWNS_EXCEPTION_BINDING = True

handler = _mod


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_db(org_row=None, rate_rows=None):
    """Build a mock db session."""
    db = MagicMock()
    call_count = [0]

    def _execute(sql, params=None):
        call_count[0] += 1
        result = MagicMock()
        sql_str = str(sql)

        # Rate limit prune DELETE
        if 'DELETE FROM crm_public_rate_limits' in sql_str:
            result.fetchone.return_value = None
            return result

        # Rate limit SELECT
        if 'SELECT counter' in sql_str and 'crm_public_rate_limits' in sql_str:
            if rate_rows:
                ip = (params or {}).get('ip', '')
                bucket = (params or {}).get('bucket', '')
                for r in rate_rows:
                    if r.get('ip') == ip and r.get('bucket') == bucket:
                        result.fetchone.return_value = (r['counter'], r['window_start'])
                        return result
            result.fetchone.return_value = None  # no existing row
            return result

        # Rate limit INSERT / UPDATE
        if 'INSERT INTO crm_public_rate_limits' in sql_str or \
           ('UPDATE crm_public_rate_limits' in sql_str and 'counter' in sql_str):
            result.fetchone.return_value = None
            return result

        # Org SELECT
        if 'organizations' in sql_str and 'public_form_key' in sql_str:
            result.fetchone.return_value = org_row
            return result

        result.fetchone.return_value = None
        return result

    db.execute.side_effect = _execute
    db.commit = MagicMock()
    return db


def _good_body(org_key='testkey123'):
    return {
        'orgPublicKey':   org_key,
        'email':          'lead@example.com',
        'firstName':      'Test',
        'lastName':       'Lead',
        'recaptchaToken': 'sometoken',
    }


# ─── Tests ────────────────────────────────────────────────────────────────────

class _LeadCaptureBase(unittest.TestCase):
    """Base class: re-pins stubs before every test.

    When both test_lead_service.py and this file run in the same pytest
    session, the former loads the *real* lead_service module into
    sys.modules and overwrites GEPPPlatform.exceptions with its own stubs.
    Re-pinning in setUp() makes ordering irrelevant.
    """
    def setUp(self):
        # Re-pin lead_service stub.
        sys.modules['GEPPPlatform.services.admin.crm.lead_service'] = _lead_svc_stub
        _crm_pkg = sys.modules.get('GEPPPlatform.services.admin.crm')
        if _crm_pkg is not None:
            _crm_pkg.lead_service = _lead_svc_stub

        # Re-pin exceptions so lazy imports inside the handler get OUR classes.
        _exc_mod.NotFoundException   = _NotFoundException
        _exc_mod.BadRequestException = _BadRequestException
        _exc_mod.APIException        = _APIException
        sys.modules['GEPPPlatform.exceptions'] = _exc_mod

        # Re-pin exception classes on the loaded module.
        handler.BadRequestException = _BadRequestException
        handler.NotFoundException   = _NotFoundException

        # Reset call history on the lead_service stub so tests stay independent.
        _lead_svc_stub.reset_mock()


class TestRecaptchaBranches(_LeadCaptureBase):

    def test_no_secret_dev_mode_accepts(self):
        """When RECAPTCHA_SECRET is unset, request is accepted with a warning."""
        db = _make_db(org_row=(1,))
        _lead_svc_stub.create_lead.return_value = {'id': 42, 'email': 'lead@example.com'}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            result = handler.handle_public_lead_capture(_good_body(), db, {})

        self.assertTrue(result['ok'])
        self.assertEqual(result['leadId'], 42)

    def test_secret_set_but_no_token_raises_400(self):
        db = _make_db(org_row=(1,))
        body = _good_body()
        body.pop('recaptchaToken')

        with patch.dict(os.environ, {'RECAPTCHA_SECRET': 'mysecret'}):
            with self.assertRaises(_BadRequestException) as ctx:
                handler.handle_public_lead_capture(body, db, {})
        self.assertIn("recaptchaToken", str(ctx.exception))

    def test_secret_set_token_rejected_raises_400(self):
        db = _make_db(org_row=(1,))

        def _bad_recaptcha(*args, **kwargs):
            raise _BadRequestException("reCAPTCHA verification failed: invalid-input-response")

        with patch.dict(os.environ, {'RECAPTCHA_SECRET': 'mysecret'}):
            with patch.object(handler, '_verify_recaptcha', side_effect=_bad_recaptcha):
                with self.assertRaises(_BadRequestException):
                    handler.handle_public_lead_capture(_good_body(), db, {})

    def test_secret_set_token_valid_accepts(self):
        db = _make_db(org_row=(1,))
        _lead_svc_stub.create_lead.return_value = {'id': 99, 'email': 'lead@example.com'}

        with patch.dict(os.environ, {'RECAPTCHA_SECRET': 'mysecret'}):
            with patch.object(handler, '_verify_recaptcha', return_value=None):
                result = handler.handle_public_lead_capture(_good_body(), db, {})

        self.assertTrue(result['ok'])
        self.assertEqual(result['leadId'], 99)


class TestRateLimiting(_LeadCaptureBase):

    def test_first_request_inserts_row_and_succeeds(self):
        db = _make_db(org_row=(1,))
        _lead_svc_stub.create_lead.return_value = {'id': 1, 'email': 'a@b.com'}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            result = handler.handle_public_lead_capture(
                _good_body(), db, {'ip_address': '1.2.3.4'}
            )
        self.assertTrue(result['ok'])

    def test_rate_limit_exceeded_raises_429(self):
        """When counter >= limit on a live window, raise 429."""
        now = datetime.now(timezone.utc)
        rate_rows = [
            {'ip': '5.6.7.8', 'bucket': 'minute', 'counter': 10, 'window_start': now},
        ]
        db = _make_db(org_row=(1,), rate_rows=rate_rows)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            with self.assertRaises(_APIException) as ctx:
                handler.handle_public_lead_capture(
                    _good_body(), db, {'ip_address': '5.6.7.8'}
                )
        self.assertEqual(ctx.exception.status_code, 429)

    def test_expired_window_resets_counter(self):
        """When window_start is older than the window duration, counter is reset → success."""
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        rate_rows = [
            {'ip': '9.8.7.6', 'bucket': 'minute', 'counter': 10, 'window_start': old_time},
            {'ip': '9.8.7.6', 'bucket': 'day',    'counter': 5,  'window_start': old_time},
        ]
        db = _make_db(org_row=(1,), rate_rows=rate_rows)
        _lead_svc_stub.create_lead.return_value = {'id': 77, 'email': 'x@y.com'}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            result = handler.handle_public_lead_capture(
                _good_body(), db, {'ip_address': '9.8.7.6'}
            )
        self.assertTrue(result['ok'])


class TestOrgResolution(_LeadCaptureBase):

    def test_unknown_public_form_key_raises_404(self):
        db = _make_db(org_row=None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            with self.assertRaises(_NotFoundException):
                handler.handle_public_lead_capture(_good_body(), db, {})

    def test_missing_org_key_raises_400(self):
        db = MagicMock()
        body = {'email': 'a@b.com'}
        with self.assertRaises(_BadRequestException):
            handler.handle_public_lead_capture(body, db, {})

    def test_missing_email_raises_400(self):
        db = MagicMock()
        with self.assertRaises(_BadRequestException):
            handler.handle_public_lead_capture({'orgPublicKey': 'key'}, db, {})


class TestHappyPath(_LeadCaptureBase):

    def test_response_never_echoes_pii(self):
        db = _make_db(org_row=(55,))
        _lead_svc_stub.create_lead.return_value = {
            'id': 123, 'email': 'secret@pii.com', 'first_name': 'Secret'
        }

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            result = handler.handle_public_lead_capture(_good_body(), db, {})

        self.assertIn('ok', result)
        self.assertIn('leadId', result)
        self.assertNotIn('email', result)
        self.assertNotIn('first_name', result)
        self.assertNotIn('last_name', result)

    def test_lead_service_called_with_correct_org(self):
        db = _make_db(org_row=(55,))
        _lead_svc_stub.create_lead.return_value = {'id': 7}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RECAPTCHA_SECRET', None)
            handler.handle_public_lead_capture(_good_body(), db, {})

        _lead_svc_stub.create_lead.assert_called_once()
        _, kwargs = _lead_svc_stub.create_lead.call_args
        self.assertEqual(kwargs['org_id'], 55)
        self.assertEqual(kwargs['source'], 'web_form')


if __name__ == '__main__':
    unittest.main()
