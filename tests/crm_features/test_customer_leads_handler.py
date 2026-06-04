"""
Unit tests for GEPP.me public customer lead intake.

Run:
    python -m pytest tests/crm_features/test_customer_leads_handler.py -v
"""

import importlib.util as _ilu
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_OWNS_EXCEPTION_BINDING = True

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _stub(name, base=None):
    m = base or MagicMock()
    m.__spec__ = None
    sys.modules[name] = m
    return m


for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.services",
    "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
    "GEPPPlatform.services.public",
    "sqlalchemy",
    "sqlalchemy.orm",
]:
    _stub(_pkg)


class _BadRequestException(Exception):
    def __init__(self, msg="bad request", status_code=400, error_code="BAD_REQUEST"):
        self.message = msg
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(msg)


_exc_mod = MagicMock()
_exc_mod.BadRequestException = _BadRequestException
sys.modules["GEPPPlatform.exceptions"] = _exc_mod

_lead_svc_stub = MagicMock()
_crm_svc_stub = MagicMock()
sys.modules["GEPPPlatform.services.admin.crm.lead_service"] = _lead_svc_stub
sys.modules["GEPPPlatform.services.admin.crm.crm_service"] = _crm_svc_stub
_crm_pkg = sys.modules["GEPPPlatform.services.admin.crm"]
_crm_pkg.lead_service = _lead_svc_stub
_crm_pkg.crm_service = _crm_svc_stub

_FULL_NAME = "GEPPPlatform.services.public.customer_leads_handler"
_spec = _ilu.spec_from_file_location(
    _FULL_NAME,
    os.path.join(_ROOT, "GEPPPlatform/services/public/customer_leads_handler.py"),
)
_mod = _ilu.module_from_spec(_spec)
sys.modules[_FULL_NAME] = _mod
_spec.loader.exec_module(_mod)

_mod.BadRequestException = _BadRequestException
_mod._OWNS_EXCEPTION_BINDING = True
handler = _mod


def _good_body():
    return {
        "name": "Jane Doe",
        "email": "Jane.Doe@Example.com",
        "company": "Example Co",
        "type": "new",
        "message": "Please book a demo.",
        "source": "landing-page",
        "metadata": {
            "page_url": "https://gepp.me/contact",
            "referrer": "https://google.com/",
            "utm": {"source": "google"},
        },
    }


class TestOriginAllowlist(unittest.TestCase):
    def test_only_exact_gepp_me_origin_is_allowed(self):
        self.assertTrue(handler.is_origin_allowed("https://gepp.me"))
        self.assertFalse(handler.is_origin_allowed("https://www.gepp.me"))
        self.assertFalse(handler.is_origin_allowed("https://evil.example"))
        self.assertFalse(handler.is_origin_allowed(None))


class TestCustomerLeadCapture(unittest.TestCase):
    def setUp(self):
        sys.modules["GEPPPlatform.services.admin.crm.lead_service"] = _lead_svc_stub
        sys.modules["GEPPPlatform.services.admin.crm.crm_service"] = _crm_svc_stub
        crm_pkg = sys.modules.get("GEPPPlatform.services.admin.crm")
        if crm_pkg is not None:
            crm_pkg.lead_service = _lead_svc_stub
            crm_pkg.crm_service = _crm_svc_stub

        _lead_svc_stub.reset_mock()
        _crm_svc_stub.reset_mock()
        _lead_svc_stub.create_lead.return_value = {"id": 321}
        _lead_svc_stub.add_activity.return_value = 654
        _crm_svc_stub.send_via_email_lambda.return_value = {
            "success": True,
            "mandrill_message_id": "abc123",
        }

    def test_persists_to_crm_leads_with_gepp_me_attribution(self):
        db = MagicMock()
        request_meta = {
            "origin": "https://gepp.me",
            "ip_address": "1.2.3.4",
            "user_agent": "UnitTest",
        }

        with patch.dict(os.environ, {"GEPP_ME_LEAD_NOTIFY_EMAIL": "sales@example.com"}):
            result = handler.handle_customer_lead_capture(_good_body(), db, request_meta)

        self.assertTrue(result["ok"])
        self.assertEqual(result["id"], 321)
        self.assertEqual(result["source"], "web_form")
        self.assertEqual(result["sourceDetail"], "gepp.me/contact")
        self.assertEqual(result["emailNotification"], "sent")

        _lead_svc_stub.create_lead.assert_called_once()
        _, kwargs = _lead_svc_stub.create_lead.call_args
        self.assertIsNone(kwargs["org_id"])
        self.assertEqual(kwargs["source"], "web_form")
        self.assertEqual(kwargs["data"]["email"], "Jane.Doe@Example.com")
        self.assertEqual(kwargs["data"]["first_name"], "Jane")
        self.assertEqual(kwargs["data"]["last_name"], "Doe")
        self.assertIn("gepp_me", kwargs["data"]["tags"])
        self.assertEqual(kwargs["source_metadata"]["source_site"], "gepp.me")
        self.assertEqual(kwargs["source_metadata"]["source_form"], "contact")
        self.assertEqual(kwargs["source_metadata"]["source_label"], "landing-page")
        self.assertEqual(kwargs["source_metadata"]["lead_type"], "new")

        _lead_svc_stub.add_activity.assert_called_once()
        activity_args = _lead_svc_stub.add_activity.call_args.args
        activity_kwargs = _lead_svc_stub.add_activity.call_args.kwargs
        self.assertEqual(activity_args[1], 321)
        self.assertEqual(activity_kwargs["activity_type"], "contact_form_submitted")
        self.assertEqual(activity_kwargs["properties"]["message"], "Please book a demo.")
        db.commit.assert_called_once()

        _crm_svc_stub.send_via_email_lambda.assert_called_once()
        email_kwargs = _crm_svc_stub.send_via_email_lambda.call_args.kwargs
        self.assertEqual(email_kwargs["to_email"], "sales@example.com")
        self.assertIn("gepp-me-contact", email_kwargs["tags"])
        self.assertEqual(email_kwargs["metadata"]["source_site"], "gepp.me")

    def test_invalid_type_raises_bad_request(self):
        body = _good_body()
        body["type"] = "partner"

        with self.assertRaises(_BadRequestException):
            handler.handle_customer_lead_capture(body, MagicMock(), {})

    def test_mailchimp_failure_does_not_drop_the_lead(self):
        _crm_svc_stub.send_via_email_lambda.return_value = {
            "success": False,
            "error": "lambda unavailable",
        }

        result = handler.handle_customer_lead_capture(_good_body(), MagicMock(), {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["id"], 321)
        self.assertEqual(result["emailNotification"], "failed")
        _lead_svc_stub.create_lead.assert_called_once()


if __name__ == "__main__":
    unittest.main()
