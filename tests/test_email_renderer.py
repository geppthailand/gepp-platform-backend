"""
Unit tests for GEPPPlatform/services/admin/crm/email_renderer.py

Run from v3/backend/:
    python -m pytest tests/test_email_renderer.py -v

Or standalone:
    python -m unittest tests.test_email_renderer
"""

import sys
import os
import unittest

# Ensure the package root is on the path regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm.email_renderer import render, _substitute, _build_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _template(subject="Hello {{user.name}}", body_html="<p>Hi {{user.name}}</p>", body_plain="Hi {{user.name}}"):
    return {"subject": subject, "body_html": body_html, "body_plain": body_plain}


def _user(firstname="Alice", lastname="Smith", email="alice@example.com", **kw):
    u = {"firstname": firstname, "lastname": lastname, "email": email}
    u.update(kw)
    return u


def _org(name="Acme Corp"):
    return {"name": name}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicSubstitution(unittest.TestCase):
    """Case 1: Basic variable substitution in all three output strings."""

    def test_user_name_in_subject_html_plain(self):
        subject, html, plain = render(
            _template(),
            _user(),
            _org(),
        )
        self.assertEqual(subject, "Hello Alice Smith")
        # Sprint 2-4: renderer now auto-appends an unsubscribe footer.
        # Use startsWith / contains rather than full equality.
        self.assertTrue(html.startswith("<p>Hi Alice Smith</p>"), html)
        self.assertTrue(plain.startswith("Hi Alice Smith"), plain)

    def test_org_name(self):
        tmpl = _template(
            subject="News from {{org.name}}",
            body_html="<p>{{org.name}} newsletter</p>",
            body_plain="{{org.name}} newsletter",
        )
        subject, html, plain = render(tmpl, None, _org("GEPP Platform"))
        self.assertEqual(subject, "News from GEPP Platform")
        self.assertIn("GEPP Platform", html)
        self.assertIn("GEPP Platform", plain)


class TestHTMLEscaping(unittest.TestCase):
    """Case 2: HTML-dangerous characters in user data are escaped in body_html but NOT body_plain."""

    def test_xss_attempt_in_name_escaped_in_html(self):
        user = _user(firstname='<script>alert("xss")</script>', lastname="")
        tmpl = _template(
            subject="Hi {{user.first_name}}",
            body_html="<p>Hi {{user.first_name}}</p>",
            body_plain="Hi {{user.first_name}}",
        )
        subject, html, plain = render(tmpl, user, None)

        # Subject and plain must NOT escape
        self.assertIn('<script>', subject)
        self.assertIn('<script>', plain)

        # HTML body MUST escape
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_ampersand_escaped_in_html(self):
        user = _user(firstname="Tom & Jerry", lastname="")
        tmpl = _template(
            body_html="<p>{{user.first_name}}</p>",
            body_plain="{{user.first_name}}",
        )
        _, html, plain = render(tmpl, user, None)
        self.assertIn("&amp;", html)
        self.assertIn("Tom & Jerry", plain)


class TestMissingVariable(unittest.TestCase):
    """Case 3: Missing / unknown variables are replaced with empty string (no crash)."""

    def test_unknown_var_replaced_with_empty(self):
        tmpl = _template(
            subject="Points: {{reward_points}}",
            body_html="<p>Points: {{reward_points}}</p>",
            body_plain="Points: {{reward_points}}",
        )
        # user dict has no reward_points key
        subject, html, plain = render(tmpl, _user(), None)
        self.assertEqual(subject, "Points: ")
        # plain may have an unsubscribe footer appended; subject does not.
        self.assertTrue(plain.startswith("Points: "), plain)

    def test_completely_unknown_variable(self):
        tmpl = _template(
            subject="{{totally_unknown}}",
            body_html="{{totally_unknown}}",
            body_plain="{{totally_unknown}}",
        )
        subject, html, plain = render(tmpl, _user(), None)
        self.assertEqual(subject, "")
        # body has unknown var (replaced empty) PLUS auto-appended footer.
        # The footer is non-empty, so html/plain are non-empty post-Sprint-2.
        # Assert the original body resolved to empty before footer was appended.
        self.assertNotIn("totally_unknown", html)
        self.assertNotIn("totally_unknown", plain)


class TestCustomVariables(unittest.TestCase):
    """Case 4 & 5: {{ custom.<key> }} via extra_vars dict and nested custom dict."""

    def test_custom_key_via_flat_extra_vars(self):
        tmpl = _template(
            subject="{{ custom.promo_code }}",
            body_html="<p>Use {{ custom.promo_code }}</p>",
            body_plain="Use {{ custom.promo_code }}",
        )
        subject, html, plain = render(tmpl, _user(), None, {"custom.promo_code": "SAVE20"})
        self.assertEqual(subject, "SAVE20")
        self.assertIn("SAVE20", html)
        self.assertIn("SAVE20", plain)

    def test_custom_key_via_nested_dict(self):
        tmpl = _template(
            subject="{{ custom.campaign_name }}",
            body_html="{{ custom.campaign_name }}",
            body_plain="{{ custom.campaign_name }}",
        )
        extra = {"custom": {"campaign_name": "Win-back Q2"}}
        subject, _, _ = render(tmpl, _user(), None, extra)
        self.assertEqual(subject, "Win-back Q2")

    def test_custom_key_missing_replaced_empty(self):
        tmpl = _template(subject="{{ custom.missing_key }}")
        subject, _, _ = render(tmpl, _user(), None, {})
        self.assertEqual(subject, "")


class TestUnsubscribeUrl(unittest.TestCase):
    """Case 6: unsubscribe_url injected via extra_vars."""

    def test_unsubscribe_url_in_body(self):
        tmpl = _template(
            body_html='<a href="{{unsubscribe_url}}">Unsubscribe</a>',
            body_plain="Unsubscribe: {{unsubscribe_url}}",
        )
        url = "https://app.gepp.me/unsubscribe/abc123"
        _, html, plain = render(tmpl, _user(), None, {"unsubscribe_url": url})
        self.assertIn(url, html)
        self.assertIn(url, plain)


class TestProfileFields(unittest.TestCase):
    """Case 7: Profile-derived fields (days_since_last_login, etc.) from user dict."""

    def test_days_since_last_login(self):
        user = _user(days_since_last_login=42)
        tmpl = _template(
            subject="You've been away for {{days_since_last_login}} days",
            body_html="<p>{{days_since_last_login}} days inactive</p>",
            body_plain="{{days_since_last_login}} days inactive",
        )
        subject, html, plain = render(tmpl, user, None)
        self.assertIn("42", subject)
        self.assertIn("42", html)
        self.assertIn("42", plain)

    def test_transaction_count_30d(self):
        user = _user(transaction_count_30d=7)
        tmpl = _template(
            body_plain="Transactions this month: {{transaction_count_30d}}",
        )
        _, _, plain = render(tmpl, user, None)
        self.assertIn("7", plain)


class TestExtraVarsOverride(unittest.TestCase):
    """Case 8: extra_vars override values derived from user_location."""

    def test_extra_vars_override_user_email(self):
        tmpl = _template(
            subject="Email on file: {{user.email}}",
        )
        subject, _, _ = render(
            tmpl,
            _user(email="original@example.com"),
            None,
            {"user.email": "override@example.com"},
        )
        self.assertEqual(subject, "Email on file: override@example.com")


class TestNoneInputs(unittest.TestCase):
    """Case 9: render() with user_location=None and org=None does not crash."""

    def test_no_user_no_org(self):
        tmpl = _template(
            subject="Platform update",
            body_html="<p>Hello</p>",
            body_plain="Hello",
        )
        subject, html, plain = render(tmpl, None, None)
        self.assertEqual(subject, "Platform update")
        self.assertTrue(plain.startswith("Hello"), plain)


class TestSpacesAroundVariable(unittest.TestCase):
    """Case 10: Variable syntax with spaces: {{ user.name }} (with spaces)."""

    def test_spaces_inside_braces(self):
        tmpl = _template(
            subject="Hi {{ user.first_name }} !",
            body_plain="{{ user.name }} signed up",
        )
        subject, _, plain = render(tmpl, _user("Bob", "Lee"), None)
        self.assertEqual(subject, "Hi Bob !")
        self.assertIn("Bob Lee", plain)


if __name__ == "__main__":
    unittest.main()
