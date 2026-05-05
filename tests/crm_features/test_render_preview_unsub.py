"""
Tests for render-preview auto-injected unsubscribe URL — BE Sonnet 2, Sprint 2, Task 4.

Verifies:
  - render-preview (by template ID) with no extraVars.unsubscribe_url
    produces html that contains "Unsubscribe".
  - render-preview (inline template) same behaviour.
  - If caller already supplies unsubscribe_url in extraVars, it is honoured
    and the sentinel URL is NOT injected.

Run from v3/backend/:
    python -m pytest tests/crm/test_render_preview_unsub.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TEMPLATE_ROW = {
    'id': 1,
    'name': 'Test',
    'subject': 'Hello {{user.first_name}}',
    'bodyHtml': '<p>Hello {{user.first_name}}</p>',
    'bodyPlain': 'Hello {{user.first_name}}',
    'previewText': None,
    'variables': [],
    'generatedBy': 'human',
    'aiPrompt': None,
    'version': 1,
    'organizationId': None,
    'createdDate': None,
    'updatedDate': None,
    'isCurrent': True,
    'parentTemplateId': None,
    'aiModel': None,
    'aiTokenUsage': None,
}


class TestRenderPreviewUnsubscribeAutoInject(unittest.TestCase):

    @patch('GEPPPlatform.services.admin.crm.crm_handlers.get_crm_template')
    def test_by_template_id_html_contains_unsubscribe(self, mock_get):
        """render-preview by template ID must inject Unsubscribe link when not in extraVars."""
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        mock_get.return_value = _TEMPLATE_ROW
        db = MagicMock()

        result = _dispatch_templates(
            resource_id=1,
            sub_path='render-preview',
            method='POST',
            db_session=db,
            data={'user': {'first_name': 'Alice'}, 'extraVars': {}},
            query_params={},
            current_user=None,
        )

        self.assertIn('html', result)
        self.assertIn('Unsubscribe', result['html'],
                      "Expected 'Unsubscribe' in rendered HTML when no unsubscribe_url provided")

    @patch('GEPPPlatform.services.admin.crm.crm_handlers.get_crm_template')
    def test_by_template_id_plain_contains_unsubscribe(self, mock_get):
        """Plain text variant must also reference Unsubscribe."""
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        mock_get.return_value = _TEMPLATE_ROW
        db = MagicMock()

        result = _dispatch_templates(
            resource_id=1,
            sub_path='render-preview',
            method='POST',
            db_session=db,
            data={'user': {'first_name': 'Bob'}, 'extraVars': {}},
            query_params={},
            current_user=None,
        )

        self.assertIn('Unsubscribe', result.get('plain', ''),
                      "Expected 'Unsubscribe' in rendered plain text")

    def test_inline_template_html_contains_unsubscribe(self):
        """render-preview with inline template dict must inject Unsubscribe."""
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        db = MagicMock()
        inline_tpl = {
            'subject': 'Hi',
            'bodyHtml': '<p>Body</p>',
            'bodyPlain': 'Body',
        }

        result = _dispatch_templates(
            resource_id=None,
            sub_path='render-preview',
            method='POST',
            db_session=db,
            data={'template': inline_tpl, 'extraVars': {}},
            query_params={},
            current_user=None,
        )

        self.assertIn('Unsubscribe', result['html'])

    @patch('GEPPPlatform.services.admin.crm.crm_handlers.get_crm_template')
    def test_caller_supplied_unsub_url_is_honoured(self, mock_get):
        """When caller provides unsubscribe_url in extraVars, sentinel must NOT replace it."""
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        custom_tpl = dict(_TEMPLATE_ROW)
        custom_tpl['bodyHtml'] = '<p>Body</p><a href="{{unsubscribe_url}}">Unsubscribe</a>'
        mock_get.return_value = custom_tpl

        db = MagicMock()
        caller_url = 'https://custom.example.com/unsub/token123'

        result = _dispatch_templates(
            resource_id=1,
            sub_path='render-preview',
            method='POST',
            db_session=db,
            data={
                'user': {'first_name': 'Alice'},
                'extraVars': {'unsubscribe_url': caller_url},
            },
            query_params={},
            current_user=None,
        )

        self.assertIn(caller_url, result['html'],
                      "Caller-supplied unsubscribe_url must appear in rendered HTML")
        self.assertNotIn('preview@example.com', result['html'],
                         "Sentinel email must NOT appear when caller supplies custom URL")

    @patch('GEPPPlatform.services.admin.crm.crm_handlers.get_crm_template')
    def test_no_extra_vars_key_still_injects(self, mock_get):
        """render-preview with no 'extraVars' key at all must still inject Unsubscribe."""
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        mock_get.return_value = _TEMPLATE_ROW
        db = MagicMock()

        result = _dispatch_templates(
            resource_id=1,
            sub_path='render-preview',
            method='POST',
            db_session=db,
            data={'user': {'first_name': 'Carol'}},   # no 'extraVars' key
            query_params={},
            current_user=None,
        )

        self.assertIn('Unsubscribe', result['html'])


if __name__ == '__main__':
    unittest.main()
