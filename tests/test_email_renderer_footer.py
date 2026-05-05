"""
Unit tests for auto-unsubscribe footer injection in email_renderer.py

Run from v3/backend/:
    python -m pytest tests/test_email_renderer_footer.py -v

Or standalone:
    python -m unittest tests.test_email_renderer_footer
"""

import sys
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Import the module directly to avoid the heavy package __init__ chain
import importlib.util as _ilu

def _load_module(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_renderer = _load_module(
    "GEPPPlatform/services/admin/crm/email_renderer.py",
    "GEPPPlatform.services.admin.crm.email_renderer",
)
render = _renderer.render


def _template(subject="Test", body_html="<p>Hello</p>", body_plain="Hello"):
    return {"subject": subject, "body_html": body_html, "body_plain": body_plain}


def _user(email="user@example.com", firstname="Alice", lastname="Smith"):
    return {"email": email, "firstname": firstname, "lastname": lastname}


def _org():
    return {"name": "Acme"}


class TestAutoUnsubscribeFooter(unittest.TestCase):
    """email_renderer must append an unsubscribe footer when {{unsubscribe_url}} is absent."""

    def test_footer_injected_when_template_lacks_unsubscribe_url(self):
        """
        A template with no reference to unsubscribe_url or the word 'unsubscribe'
        should get the auto-appended HTML footer and plain-text suffix.
        """
        tmpl = _template(body_html="<p>Hello World</p>", body_plain="Hello World")
        _, html, plain = render(
            tmpl, _user(), _org(),
            extra_vars={"unsubscribe_url": "https://example.com/unsub/TOKEN"},
        )

        self.assertIn("unsubscribe", html.lower(), "Footer not found in HTML")
        self.assertIn("https://example.com/unsub/TOKEN", html)
        self.assertIn("Unsubscribe", plain)
        self.assertIn("https://example.com/unsub/TOKEN", plain)

    def test_no_double_footer_when_template_already_has_unsubscribe_url(self):
        """
        A template that already references {{unsubscribe_url}} in its body must NOT
        get a second footer appended.
        """
        tmpl = _template(
            body_html='<p>Click <a href="{{unsubscribe_url}}">unsubscribe</a>.</p>',
            body_plain="To unsubscribe visit: {{unsubscribe_url}}",
        )
        _, html, plain = render(
            tmpl, _user(), _org(),
            extra_vars={"unsubscribe_url": "https://example.com/unsub/TOKEN"},
        )

        # "unsubscribe" appears exactly once in HTML (the template's own link)
        # The footer adds a <p style=...> — check it's absent
        self.assertNotIn('<p style="text-align:center', html)
        # Plain must not have duplicate
        self.assertEqual(plain.lower().count("unsubscribe"), 1)

    def test_footer_uses_auto_generated_url_when_extra_vars_omit_it(self):
        """
        When extra_vars doesn't supply unsubscribe_url, the renderer should call
        make_unsub_url to generate one and still inject a footer.
        """
        from unittest.mock import patch

        # Load unsubscribe_token module the same isolated way to get its reference
        _token_mod = _load_module(
            "GEPPPlatform/services/admin/crm/unsubscribe_token.py",
            "GEPPPlatform.services.admin.crm.unsubscribe_token",
        )

        tmpl = _template()
        # Patch make_unsub_url on the module that email_renderer imports lazily
        with patch.object(_token_mod, "make_unsub_url",
                          return_value="https://api.gepp.me/api/crm/unsubscribe/AUTO_TOKEN"):
            _, html, plain = render(tmpl, _user(), _org())

        self.assertIn("unsubscribe", html.lower())
        self.assertIn("AUTO_TOKEN", html)

    def test_no_footer_when_no_email_and_no_unsub_url(self):
        """
        If user_location has no email and extra_vars has no unsubscribe_url,
        no footer should be injected (nothing to link to).
        """
        tmpl = _template(body_html="<p>Message</p>", body_plain="Message")
        _, html, plain = render(
            tmpl,
            {"firstname": "Alice"},   # no email
            _org(),
            extra_vars={},            # no unsubscribe_url
        )

        # Footer must NOT appear because there's no URL to use
        self.assertNotIn('<p style="text-align:center', html)
        self.assertNotIn("Unsubscribe:", plain)

    def test_html_footer_contains_style_attributes(self):
        """The auto-injected HTML footer must carry the specified inline styles."""
        tmpl = _template(body_html="<p>Hello</p>", body_plain="Hello")
        _, html, _ = render(
            tmpl, _user(), _org(),
            extra_vars={"unsubscribe_url": "https://example.com/unsub/X"},
        )

        self.assertIn("text-align:center", html)
        self.assertIn("font-size:12px", html)
        self.assertIn("color:#888", html)

    def test_plain_footer_ends_with_newline(self):
        """The plain-text footer should end with a newline for clean email clients."""
        tmpl = _template(body_html="<p>Hi</p>", body_plain="Hi")
        _, _, plain = render(
            tmpl, _user(), _org(),
            extra_vars={"unsubscribe_url": "https://example.com/u/Y"},
        )

        self.assertTrue(plain.endswith("\n"), "Plain footer should end with newline")


if __name__ == "__main__":
    unittest.main()
