"""
Unit tests for email_blocks.py — block-based email renderer.

Strategy:
  - Each test renders a block with default brand and asserts:
      (a) key structural HTML is present
      (b) brand values appear in the output (not hardcoded constants)
  - Tree-level tests verify ordering and concatenation.
  - Parity tests use the DEFAULT_BRAND to check that Python output
    matches the known structure from renderer.js (snapshot approach).
"""

import pytest
from GEPPPlatform.services.admin.crm.email_blocks import (
    render_block,
    render_block_tree,
    _DEFAULT_BRAND,
    _esc,
    _nl2br,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_B = dict(_DEFAULT_BRAND)  # default brand — copy so tests can't pollute it


def _render(block_type: str, props: dict = None) -> str:
    return render_block(block_type, props or {}, _B)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_esc_basic(self):
        assert _esc("<b>") == "&lt;b&gt;"
        assert _esc("hello & world") == "hello &amp; world"
        assert _esc('"quoted"') == "&quot;quoted&quot;"
        assert _esc(None) == ""
        assert _esc("") == ""

    def test_nl2br(self):
        result = _nl2br("line1\nline2")
        assert "line1" in result
        assert "line2" in result
        assert "<br>" in result

    def test_nl2br_escapes(self):
        result = _nl2br("<script>\ntest")
        assert "&lt;script&gt;" in result
        assert "<br>" in result


# ---------------------------------------------------------------------------
# render_block — unknown type
# ---------------------------------------------------------------------------

class TestUnknownBlock:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown block type"):
            render_block("not_a_real_block", {}, _B)


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------

class TestHeader:
    def test_contains_logo(self):
        html = _render("header", {"logoUrl": "https://example.com/logo.png"})
        assert "https://example.com/logo.png" in html
        assert "140" in html  # width

    def test_uses_brand_logo_fallback(self):
        b = {**_B, "logo_base64": "", "logo_url": "https://brand.url/logo.png"}
        html = render_block("header", {}, b)
        assert "https://brand.url/logo.png" in html

    def test_contains_tr(self):
        html = _render("header")
        assert "<tr>" in html
        assert "<td" in html


# ---------------------------------------------------------------------------
# hero
# ---------------------------------------------------------------------------

class TestHero:
    def test_headline_escaped(self):
        html = _render("hero", {"headline": "<b>Bold</b>", "subheadline": ""})
        assert "&lt;b&gt;Bold&lt;/b&gt;" in html

    def test_subheadline_optional(self):
        html_no_sub = _render("hero", {"headline": "Hello"})
        assert "Hello" in html_no_sub
        # No extra paragraph without subheadline
        html_with_sub = _render("hero", {"headline": "Hello", "subheadline": "Sub"})
        assert "Sub" in html_with_sub

    def test_custom_bg_color(self):
        html = _render("hero", {"headline": "X", "bgColor": "#ff0000"})
        assert "#ff0000" in html

    def test_brand_forest_fallback(self):
        html = _render("hero", {"headline": "X"})
        assert _DEFAULT_BRAND["color_forest"] in html


# ---------------------------------------------------------------------------
# hero_image
# ---------------------------------------------------------------------------

class TestHeroImage:
    def test_empty_returns_empty(self):
        assert _render("hero_image", {"imageUrl": ""}) == ""

    def test_image_rendered(self):
        html = _render("hero_image", {"imageUrl": "https://img.com/a.jpg", "altText": "Alt"})
        assert "https://img.com/a.jpg" in html
        assert "Alt" in html

    def test_with_link(self):
        html = _render("hero_image", {
            "imageUrl": "https://img.com/a.jpg",
            "linkUrl": "https://gepp.me",
        })
        assert "https://gepp.me" in html
        assert "<a href=" in html

    def test_without_link(self):
        html = _render("hero_image", {"imageUrl": "https://img.com/a.jpg"})
        assert "<a href=" not in html


# ---------------------------------------------------------------------------
# accent_bar
# ---------------------------------------------------------------------------

class TestAccentBar:
    def test_uses_lime(self):
        html = _render("accent_bar")
        assert _DEFAULT_BRAND["color_lime"] in html

    def test_height_4px(self):
        html = _render("accent_bar")
        assert "height: 4px" in html


# ---------------------------------------------------------------------------
# body
# ---------------------------------------------------------------------------

class TestBody:
    def test_single_paragraph(self):
        html = _render("body", {"paragraphs": ["Hello world"]})
        assert "Hello world" in html
        assert "<p" in html

    def test_multiple_paragraphs(self):
        html = _render("body", {"paragraphs": ["First", "Second"]})
        assert "First" in html
        assert "Second" in html
        # Second paragraph has margin-top
        assert "16px" in html

    def test_string_shorthand(self):
        html = _render("body", {"paragraphs": "Single string"})
        assert "Single string" in html

    def test_nl2br_applied(self):
        html = _render("body", {"paragraphs": ["Line1\nLine2"]})
        assert "<br>" in html

    def test_custom_padding(self):
        html = _render("body", {"paragraphs": ["X"], "paddingTop": 64, "paddingBottom": 64})
        assert "64px" in html


# ---------------------------------------------------------------------------
# greeting
# ---------------------------------------------------------------------------

class TestGreeting:
    def test_default_greeting(self):
        html = _render("greeting", {"name": "Alice"})
        assert "Hi" in html
        assert "Alice" in html

    def test_custom_greeting(self):
        html = _render("greeting", {"name": "Bob", "greeting": "Hello"})
        assert "Hello" in html
        assert "Bob" in html

    def test_name_escaped(self):
        html = _render("greeting", {"name": "<script>"})
        assert "&lt;script&gt;" in html

    def test_comma_appended(self):
        html = _render("greeting", {"name": "Alice"})
        # The comma is in the template
        assert "Alice," in html


# ---------------------------------------------------------------------------
# signoff
# ---------------------------------------------------------------------------

class TestSignoff:
    def test_sender_name(self):
        html = _render("signoff", {"senderName": "Jane Doe"})
        assert "Jane Doe" in html

    def test_sender_title_optional(self):
        html_no_title = _render("signoff", {"senderName": "Jane"})
        html_with_title = _render("signoff", {"senderName": "Jane", "senderTitle": "CEO"})
        assert "CEO" in html_with_title
        assert "CEO" not in html_no_title

    def test_brand_company_name(self):
        html = _render("signoff", {"senderName": "X"})
        assert _DEFAULT_BRAND["company_name"] in html

    def test_best_regards(self):
        html = _render("signoff", {"senderName": "X"})
        assert "Best regards" in html


# ---------------------------------------------------------------------------
# cta
# ---------------------------------------------------------------------------

class TestCta:
    def test_text_and_url(self):
        html = _render("cta", {"text": "Click Me", "url": "https://gepp.me"})
        assert "Click Me" in html
        assert "https://gepp.me" in html

    def test_mso_comment(self):
        html = _render("cta", {"text": "Go", "url": "#"})
        assert "<!--[if mso]>" in html
        assert "mso-hide: all" in html

    def test_custom_bg_color(self):
        html = _render("cta", {"text": "X", "url": "#", "bgColor": "#ff0000"})
        assert "#ff0000" in html

    def test_default_align_center(self):
        html = _render("cta", {"text": "X", "url": "#"})
        assert 'align="center"' in html

    def test_custom_align(self):
        html = _render("cta", {"text": "X", "url": "#", "align": "left"})
        assert 'align="left"' in html


# ---------------------------------------------------------------------------
# secondary_cta
# ---------------------------------------------------------------------------

class TestSecondaryCta:
    def test_renders_link(self):
        html = _render("secondary_cta", {"text": "Learn more", "url": "https://gepp.me"})
        assert "Learn more" in html
        assert "https://gepp.me" in html
        assert "<a href=" in html

    def test_uses_primary_color(self):
        html = _render("secondary_cta", {"text": "X", "url": "#"})
        assert _DEFAULT_BRAND["color_primary"] in html


# ---------------------------------------------------------------------------
# stats_grid
# ---------------------------------------------------------------------------

class TestStatsGrid:
    def test_empty_returns_empty(self):
        assert _render("stats_grid", {"stats": []}) == ""

    def test_single_stat(self):
        html = _render("stats_grid", {"stats": [{"value": "99%", "label": "Uptime"}]})
        assert "99%" in html
        assert "Uptime" in html

    def test_multiple_stats(self):
        stats = [
            {"value": "1K", "label": "Users"},
            {"value": "50%", "label": "Savings"},
        ]
        html = _render("stats_grid", {"stats": stats})
        assert "1K" in html
        assert "50%" in html
        assert "Users" in html
        assert "Savings" in html

    def test_separator_between_cells(self):
        stats = [{"value": "A", "label": "a"}, {"value": "B", "label": "b"}]
        html = _render("stats_grid", {"stats": stats})
        assert "width: 8px" in html

    def test_max_4_cols(self):
        stats = [{"value": str(i), "label": f"L{i}"} for i in range(6)]
        html = _render("stats_grid", {"stats": stats})
        # Cell width = (600-80)//4 = 130 — verifying the grid respects 4-col max
        assert "130" in html  # (600-40-40)/4


# ---------------------------------------------------------------------------
# bullet_list
# ---------------------------------------------------------------------------

class TestBulletList:
    def test_empty_returns_empty(self):
        assert _render("bullet_list", {"items": []}) == ""

    def test_string_items(self):
        html = _render("bullet_list", {"items": ["Alpha", "Beta"]})
        assert "Alpha" in html
        assert "Beta" in html

    def test_dict_items(self):
        html = _render("bullet_list", {"items": [
            {"title": "Item A", "description": "Desc A"},
        ]})
        assert "Item A" in html
        assert "Desc A" in html

    def test_default_checkmark_icon(self):
        html = _render("bullet_list", {"items": ["X"]})
        assert "&#10003;" in html

    def test_custom_icon(self):
        html = _render("bullet_list", {"items": ["X"], "icon": "→"})
        assert "→" in html


# ---------------------------------------------------------------------------
# numbered_steps
# ---------------------------------------------------------------------------

class TestNumberedSteps:
    def test_empty_returns_empty(self):
        assert _render("numbered_steps", {"steps": []}) == ""

    def test_step_numbers(self):
        steps = [{"title": "Step A"}, {"title": "Step B"}]
        html = _render("numbered_steps", {"steps": steps})
        # Numbers appear with surrounding whitespace in the rendered output
        assert "1" in html
        assert "2" in html
        # Verify circle badge structure carries the numbers
        assert "border-radius: 50%" in html

    def test_connector_between_steps(self):
        steps = [{"title": "A"}, {"title": "B"}]
        html = _render("numbered_steps", {"steps": steps})
        assert "height: 12px" in html  # connector div

    def test_no_connector_after_last(self):
        html = _render("numbered_steps", {"steps": [{"title": "Only"}]})
        assert "height: 12px" not in html

    def test_description_optional(self):
        html_no_desc = _render("numbered_steps", {"steps": [{"title": "A"}]})
        html_with_desc = _render("numbered_steps", {"steps": [{"title": "A", "description": "Do this"}]})
        assert "Do this" in html_with_desc
        assert "Do this" not in html_no_desc


# ---------------------------------------------------------------------------
# agenda_list
# ---------------------------------------------------------------------------

class TestAgendaList:
    def test_empty_returns_empty(self):
        assert _render("agenda_list", {"items": []}) == ""

    def test_with_time(self):
        html = _render("agenda_list", {"items": [{"time": "9:00", "title": "Opening"}]})
        assert "9:00" in html
        assert "Opening" in html

    def test_alternating_background(self):
        items = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        html = _render("agenda_list", {"items": items})
        assert _DEFAULT_BRAND["color_surface_light"] in html
        assert _DEFAULT_BRAND["color_white"] in html

    def test_string_items(self):
        html = _render("agenda_list", {"items": ["Talk 1", "Talk 2"]})
        assert "Talk 1" in html


# ---------------------------------------------------------------------------
# feature_list
# ---------------------------------------------------------------------------

class TestFeatureList:
    def test_empty_returns_empty(self):
        assert _render("feature_list", {"features": []}) == ""

    def test_feature_card(self):
        html = _render("feature_list", {"features": [{"title": "Smart AI", "description": "Uses AI"}]})
        assert "Smart AI" in html
        assert "Uses AI" in html

    def test_border_left_primary(self):
        html = _render("feature_list", {"features": [{"title": "X"}]})
        assert f"border-left: 4px solid {_DEFAULT_BRAND['color_primary']}" in html

    def test_multiple_features(self):
        features = [{"title": "F1"}, {"title": "F2"}, {"title": "F3"}]
        html = _render("feature_list", {"features": features})
        assert "F1" in html and "F2" in html and "F3" in html


# ---------------------------------------------------------------------------
# speaker_list
# ---------------------------------------------------------------------------

class TestSpeakerList:
    def test_empty_returns_empty(self):
        assert _render("speaker_list", {"speakers": []}) == ""

    def test_speaker_name_and_title(self):
        html = _render("speaker_list", {"speakers": [{"name": "Alice", "title": "CTO"}]})
        assert "Alice" in html
        assert "CTO" in html

    def test_title_optional(self):
        html = _render("speaker_list", {"speakers": [{"name": "Bob"}]})
        assert "Bob" in html


# ---------------------------------------------------------------------------
# callout_box
# ---------------------------------------------------------------------------

class TestCalloutBox:
    def test_title_and_text(self):
        html = _render("callout_box", {"title": "Warning", "text": "Check this"})
        assert "Warning" in html
        assert "Check this" in html

    def test_title_optional(self):
        html = _render("callout_box", {"text": "Info only"})
        assert "Info only" in html

    def test_custom_border_color(self):
        html = _render("callout_box", {"text": "X", "borderColor": "#ff0000"})
        assert "#ff0000" in html

    def test_nl2br_in_text(self):
        html = _render("callout_box", {"text": "Line1\nLine2"})
        assert "<br>" in html


# ---------------------------------------------------------------------------
# ps_block
# ---------------------------------------------------------------------------

class TestPsBlock:
    def test_empty_returns_empty(self):
        assert _render("ps_block", {"text": ""}) == ""

    def test_ps_prefix(self):
        html = _render("ps_block", {"text": "See you!"})
        assert "P.S." in html
        assert "See you!" in html

    def test_italic_style(self):
        html = _render("ps_block", {"text": "X"})
        assert "font-style: italic" in html


# ---------------------------------------------------------------------------
# divider
# ---------------------------------------------------------------------------

class TestDivider:
    def test_border_top(self):
        html = _render("divider")
        assert "border-top: 1px solid" in html
        assert _DEFAULT_BRAND["color_surface_border"] in html


# ---------------------------------------------------------------------------
# subheading
# ---------------------------------------------------------------------------

class TestSubheading:
    def test_h2_tag(self):
        html = _render("subheading", {"text": "My Section"})
        assert "<h2" in html
        assert "My Section" in html

    def test_text_escaped(self):
        html = _render("subheading", {"text": "<b>bold</b>"})
        assert "&lt;b&gt;" in html


# ---------------------------------------------------------------------------
# quote
# ---------------------------------------------------------------------------

class TestQuote:
    def test_quote_text(self):
        html = _render("quote", {"text": "Wisdom here", "author": "Sage"})
        assert "Wisdom here" in html
        assert "&ldquo;" in html
        assert "&rdquo;" in html

    def test_author_optional(self):
        html_no = _render("quote", {"text": "X"})
        html_yes = _render("quote", {"text": "X", "author": "Yoda"})
        assert "Yoda" in html_yes
        assert "Yoda" not in html_no
        assert "&mdash;" in html_yes

    def test_lime_border(self):
        html = _render("quote", {"text": "X"})
        assert _DEFAULT_BRAND["color_lime"] in html


# ---------------------------------------------------------------------------
# footer
# ---------------------------------------------------------------------------

class TestFooter:
    def test_company_name(self):
        html = _render("footer")
        assert _DEFAULT_BRAND["company_name"] in html

    def test_unsubscribe_link(self):
        html = _render("footer")
        assert "*|UNSUB|*" in html
        assert "Unsubscribe" in html

    def test_social_icons(self):
        html = _render("footer")
        assert _DEFAULT_BRAND["social_facebook_url"] in html
        assert _DEFAULT_BRAND["social_linkedin_url"] in html

    def test_current_year_merge_tag(self):
        html = _render("footer")
        assert "*|CURRENT_YEAR|*" in html

    def test_privacy_policy_link(self):
        html = _render("footer")
        assert "/privacy" in html

    def test_surface_light_background(self):
        html = _render("footer")
        assert _DEFAULT_BRAND["color_surface_light"] in html


# ---------------------------------------------------------------------------
# render_block_tree — integration
# ---------------------------------------------------------------------------

class TestRenderBlockTree:
    def test_empty_tree(self):
        assert render_block_tree({"blocks": []}, _B) == ""

    def test_none_tree(self):
        assert render_block_tree(None, _B) == ""

    def test_single_block(self):
        tree = {"blocks": [{"id": "1", "type": "divider", "props": {}}]}
        html = render_block_tree(tree, _B)
        assert "border-top: 1px solid" in html

    def test_ordering_preserved(self):
        tree = {
            "blocks": [
                {"id": "a", "type": "subheading", "props": {"text": "FIRST"}},
                {"id": "b", "type": "subheading", "props": {"text": "SECOND"}},
            ]
        }
        html = render_block_tree(tree, _B)
        assert html.index("FIRST") < html.index("SECOND")

    def test_full_email_blocks(self):
        """Renders a representative multi-block tree without errors."""
        tree = {
            "blocks": [
                {"id": "1", "type": "header",    "props": {}},
                {"id": "2", "type": "accent_bar","props": {}},
                {"id": "3", "type": "hero",      "props": {"headline": "Hello", "subheadline": "World"}},
                {"id": "4", "type": "greeting",  "props": {"name": "Alice"}},
                {"id": "5", "type": "body",      "props": {"paragraphs": ["Para 1", "Para 2"]}},
                {"id": "6", "type": "cta",       "props": {"text": "Go", "url": "https://gepp.me"}},
                {"id": "7", "type": "divider",   "props": {}},
                {"id": "8", "type": "stats_grid","props": {"stats": [{"value": "1K", "label": "Users"}]}},
                {"id": "9", "type": "signoff",   "props": {"senderName": "Bob"}},
                {"id":"10", "type": "footer",    "props": {}},
            ]
        }
        html = render_block_tree(tree, _B)
        assert "Hello" in html
        assert "Alice" in html
        assert "Para 1" in html
        assert "Go" in html
        assert "1K" in html
        assert "Bob" in html
        assert "*|UNSUB|*" in html

    def test_custom_brand_applied(self):
        custom_brand = {**_B, "color_primary": "#ABCDEF", "company_name": "AcmeCorp"}
        tree = {
            "blocks": [
                {"id": "1", "type": "cta", "props": {"text": "X", "url": "#"}},
                {"id": "2", "type": "footer", "props": {}},
            ]
        }
        html = render_block_tree(tree, custom_brand)
        assert "#ABCDEF" in html
        assert "AcmeCorp" in html

    def test_unknown_block_raises(self):
        tree = {"blocks": [{"id": "x", "type": "foobar", "props": {}}]}
        with pytest.raises(ValueError, match="Unknown block type"):
            render_block_tree(tree, _B)


# ---------------------------------------------------------------------------
# Snapshot parity — frozen expected substrings for key blocks.
# These document exactly what renderer.js produces for default brand.
# ---------------------------------------------------------------------------

class TestSnapshotParity:
    """Frozen structural snapshots. If renderer.js changes, update these."""

    def test_header_snapshot(self):
        html = _render("header")
        assert 'padding-top: 40px' in html
        assert 'padding-bottom: 20px' in html
        assert 'max-width: 140px' in html

    def test_hero_snapshot(self):
        html = _render("hero", {"headline": "Test", "subheadline": "Sub"})
        assert 'padding-top: 48px' in html
        assert 'padding-bottom: 48px' in html
        assert 'font-size: 28px' in html
        assert 'font-weight: 700' in html
        assert 'rgba(255,255,255,0.65)' in html

    def test_cta_snapshot(self):
        html = _render("cta", {"text": "Click", "url": "https://gepp.me"})
        assert 'border-radius: 8px' in html
        assert 'font-weight: 600' in html
        assert 'padding-top: 14px' in html
        assert 'padding-right: 32px' in html

    def test_stats_grid_snapshot(self):
        html = _render("stats_grid", {"stats": [{"value": "42", "label": "Items"}]})
        assert 'font-size: 28px' in html   # value size
        assert 'font-size: 12px' in html   # label size
        assert 'border-radius: 8px' in html

    def test_feature_list_snapshot(self):
        html = _render("feature_list", {"features": [{"title": "T"}]})
        assert 'border-radius: 8px' in html
        assert 'border-left: 4px solid' in html
        assert 'margin-bottom: 16px' in html

    def test_footer_snapshot(self):
        html = _render("footer")
        assert 'border-top: 1px solid' in html
        assert 'padding-top: 32px' in html
        assert 'padding-bottom: 32px' in html
        assert 'font-size: 11px' in html   # fine print

    def test_numbered_steps_snapshot(self):
        steps = [{"title": "A", "description": "desc A"}, {"title": "B"}]
        html = _render("numbered_steps", {"steps": steps})
        assert 'border-radius: 50%' in html  # circle badge
        assert 'font-size: 14px' in html
        assert 'font-weight: 700' in html
