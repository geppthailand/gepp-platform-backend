"""
Email Blocks — Python parity renderer for the block-based email builder.

Ports every render function from gepp-edm-main/js/renderer.js byte-for-byte.
Brand values are always read from the brand dict (never hardcoded).

Public API:
    render_block(block_type, props, brand) -> str
        Render a single block row HTML string.

    render_block_tree(tree, brand) -> str
        Join all blocks in order and return the final body_html.

Brand dict keys (from crm_brand_assets / migration 046):
    color_primary          color_primary_light    color_primary_dark
    color_lime             color_lime_dark         color_forest
    color_dark             color_surface_light     color_surface_white
    color_surface_border   color_text_primary      color_text_secondary
    color_text_muted       color_text_inverse      color_white
    font_stack             font_mono
    email_width            email_padding
    company_name           company_legal_name      company_tagline
    company_email          company_phone           company_full_address
    company_url            company_platform_login
    logo_url               logo_base64
    social_facebook_url    social_linkedin_url     social_youtube_url
    social_instagram_url
    social_facebook_icon   social_linkedin_icon    social_youtube_icon
    social_instagram_icon
    merge_tag_unsubscribe  merge_tag_list_address  merge_tag_current_year

Block types:
    header, hero, hero_image, accent_bar, body, greeting, signoff,
    cta, secondary_cta, stats_grid, bullet_list, numbered_steps,
    agenda_list, feature_list, speaker_list, callout_box, ps_block,
    divider, subheading, quote, footer
"""

from html import escape as _html_escape
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Default brand values — mirrors brand.js exactly.
# Used when a brand key is absent from the DB context.
# ---------------------------------------------------------------------------
_DEFAULT_BRAND: Dict[str, str] = {
    "color_primary":        "#13754A",
    "color_primary_light":  "#1a9960",
    "color_primary_dark":   "#0d5535",
    "color_lime":           "#CEDD42",
    "color_lime_dark":      "#b5c42a",
    "color_forest":         "#0A1F14",
    "color_dark":           "#0D1117",
    "color_surface_light":  "#F7F8F6",
    "color_surface_white":  "#FFFFFF",
    "color_surface_border": "#E2E8F0",
    "color_text_primary":   "#0D1117",
    "color_text_secondary": "#475569",
    "color_text_muted":     "#94A3B8",
    "color_text_inverse":   "#F7F8F6",
    "color_white":          "#FFFFFF",
    "font_stack":           "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    "font_mono":            "'Courier New', Courier, monospace",
    "email_width":          "600",
    "email_padding":        "40",
    "company_name":         "GEPP Intelligence",
    "company_legal_name":   "GEPP Sa-Ard Co., Ltd.",
    "company_tagline":      "Waste Data That Works For You",
    "company_email":        "hello@gepp.me",
    "company_phone":        "06-4043-7166",
    "company_full_address": "559/186 Nonsi Road, Chong Nonsi, Yan Nawa District, Bangkok 10120, Thailand",
    "company_url":          "https://gepp.me",
    "company_platform_login": "https://geppdatasolutions.com/login",
    "logo_url":             "https://gepp.me/images/brand/gepp-logo.png",
    "logo_base64":          "",  # large — loaded from DB
    "social_facebook_url":  "https://facebook.com/geppthailand",
    "social_linkedin_url":  "https://th.linkedin.com/company/geppsaard",
    "social_youtube_url":   "https://youtube.com/channel/UCrweanNIwXkG85H-M2VFd-Q",
    "social_instagram_url": "https://instagram.com/gepp_thailand",
    "social_facebook_label":  "Facebook",
    "social_linkedin_label":  "LinkedIn",
    "social_youtube_label":   "YouTube",
    "social_instagram_label": "Instagram",
    "social_facebook_icon":  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%2313754A'%3E%3Cpath d='M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z'/%3E%3C/svg%3E",
    "social_linkedin_icon":  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%2313754A'%3E%3Cpath d='M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z'/%3E%3C/svg%3E",
    "social_youtube_icon":   "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%2313754A'%3E%3Cpath d='M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z'/%3E%3C/svg%3E",
    "social_instagram_icon": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%2313754A'%3E%3Cpath d='M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z'/%3E%3C/svg%3E",
    "merge_tag_unsubscribe":  "*|UNSUB|*",
    "merge_tag_list_address": "*|LIST:ADDRESS|*",
    "merge_tag_current_year": "*|CURRENT_YEAR|*",
    "merge_tag_subject":      "*|MC:SUBJECT|*",
}


def _brand(brand: Dict[str, str], key: str) -> str:
    """Return brand value, falling back to the static default."""
    return brand.get(key) or _DEFAULT_BRAND.get(key, "")


def _w(brand: Dict[str, str]) -> int:
    try:
        return int(_brand(brand, "email_width"))
    except (TypeError, ValueError):
        return 600


def _p(brand: Dict[str, str]) -> int:
    try:
        return int(_brand(brand, "email_padding"))
    except (TypeError, ValueError):
        return 40


# ---------------------------------------------------------------------------
# HTML helpers — identical to esc() and nl2br() in renderer.js
# ---------------------------------------------------------------------------

def _esc(s: Any) -> str:
    if s is None:
        return ""
    return _html_escape(str(s), quote=True)


def _nl2br(s: Any) -> str:
    if s is None:
        return ""
    return _esc(s).replace("\n", "<br>")


# ---------------------------------------------------------------------------
# Block renderers — ported byte-for-byte from renderer.js
# ---------------------------------------------------------------------------

def render_header(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    logo_src = props.get("logoUrl") or _brand(brand, "logo_base64") or _brand(brand, "logo_url")
    p = _p(brand)
    return f"""
    <tr>
      <td align="center" style="padding-top: {p}px; padding-right: {p}px; padding-bottom: 20px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <img src="{logo_src}" alt="GEPP Intelligence" width="140" height="auto" style="display: block; border: 0; outline: none; max-width: 140px;" />
      </td>
    </tr>"""


def render_hero(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    headline = props.get("headline", "")
    subheadline = props.get("subheadline", "")
    bg = props.get("bgColor") or _brand(brand, "color_forest")
    accent_color = props.get("accentColor") or _brand(brand, "color_lime")
    p = _p(brand)
    sub_html = ""
    if subheadline:
        sub_html = f"""
        <p style="margin: 16px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 16px; line-height: 1.6; color: rgba(255,255,255,0.65); text-align: center;">
          {headline if False else _esc(subheadline)}
        </p>"""
    return f"""
    <tr>
      <td style="padding-top: 48px; padding-right: {p}px; padding-bottom: 48px; padding-left: {p}px; background-color: {bg};">
        <h1 style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 28px; font-weight: 700; line-height: 1.2; color: {_brand(brand, 'color_white')}; text-align: center;">
          {_esc(headline)}
        </h1>
        {sub_html}
      </td>
    </tr>"""


def render_hero_image(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    image_url = props.get("imageUrl", "")
    if not image_url:
        return ""
    alt_text = props.get("altText", "")
    link_url = props.get("linkUrl", "")
    w = _w(brand)
    img_tag = f'<img src="{_esc(image_url)}" alt="{_esc(alt_text)}" width="{w}" style="display: block; width: 100%; max-width: {w}px; height: auto; border: 0; outline: none;" />'
    if link_url:
        wrapped = f'<a href="{_esc(link_url)}" target="_blank" style="text-decoration: none;">{img_tag}</a>'
    else:
        wrapped = img_tag
    return f"""
    <tr>
      <td style="padding: 0; font-size: 0; line-height: 0;">
        {wrapped}
      </td>
    </tr>"""


def render_accent_bar(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    return f"""
    <tr>
      <td style="padding: 0; background-color: {_brand(brand, 'color_lime')}; height: 4px; font-size: 1px; line-height: 1px;">
        &nbsp;
      </td>
    </tr>"""


def render_body(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    paragraphs = props.get("paragraphs", [])
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    padding_top = props.get("paddingTop", 32)
    padding_bottom = props.get("paddingBottom", 32)
    p = _p(brand)
    paras_html = "".join(
        f"""
        <p style="margin: {('16px' if i > 0 else '0')} 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; line-height: 1.7; color: {_brand(brand, 'color_text_secondary')};">
          {_nl2br(para)}
        </p>"""
        for i, para in enumerate(paragraphs)
    )
    return f"""
    <tr>
      <td style="padding-top: {padding_top}px; padding-right: {p}px; padding-bottom: {padding_bottom}px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        {paras_html}
      </td>
    </tr>"""


def render_greeting(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    name = props.get("name", "")
    greeting = props.get("greeting", "Hi")
    p = _p(brand)
    return f"""
    <tr>
      <td style="padding-top: 32px; padding-right: {p}px; padding-bottom: 0; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; line-height: 1.7; color: {_brand(brand, 'color_text_primary')}; font-weight: 600;">
          {_esc(greeting)} {_esc(name)},
        </p>
      </td>
    </tr>"""


def render_signoff(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    sender_name = props.get("senderName", "")
    sender_title = props.get("senderTitle", "")
    p = _p(brand)
    title_html = ""
    if sender_title:
        title_html = f"""
        <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; line-height: 1.5; color: {_brand(brand, 'color_text_muted')};">
          {_esc(sender_title)}
        </p>"""
    return f"""
    <tr>
      <td style="padding-top: 24px; padding-right: {p}px; padding-bottom: 32px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; line-height: 1.7; color: {_brand(brand, 'color_text_secondary')};">
          Best regards,
        </p>
        <p style="margin: 4px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; line-height: 1.7; color: {_brand(brand, 'color_text_primary')}; font-weight: 600;">
          {_esc(sender_name)}
        </p>
        {title_html}
        <p style="margin: 2px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; line-height: 1.5; color: {_brand(brand, 'color_text_muted')};">
          {_brand(brand, 'company_name')}
        </p>
      </td>
    </tr>"""


def render_cta(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    text = props.get("text", "")
    url = props.get("url", "#")
    bg_color = props.get("bgColor") or _brand(brand, "color_primary")
    text_color = props.get("textColor") or _brand(brand, "color_white")
    align = props.get("align", "center")
    p = _p(brand)
    return f"""
    <tr>
      <td align="{align}" style="padding-top: 8px; padding-right: {p}px; padding-bottom: 32px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <!--[if mso]>
        <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="{_esc(url)}" style="height:48px;v-text-anchor:middle;width:220px;" arcsize="15%" strokecolor="{bg_color}" fillcolor="{bg_color}">
        <w:anchorlock/>
        <center style="color:{text_color};font-family:{_brand(brand, 'font_stack')};font-size:15px;font-weight:bold;">{_esc(text)}</center>
        </v:roundrect>
        <![endif]-->
        <!--[if !mso]><!-->
        <a href="{_esc(url)}" target="_blank" style="display: inline-block; padding-top: 14px; padding-right: 32px; padding-bottom: 14px; padding-left: 32px; background-color: {bg_color}; color: {text_color}; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-weight: 600; text-decoration: none; border-radius: 8px; text-align: center; mso-hide: all;">
          {_esc(text)}
        </a>
        <!--<![endif]-->
      </td>
    </tr>"""


def render_secondary_cta(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    text = props.get("text", "")
    url = props.get("url", "#")
    p = _p(brand)
    return f"""
    <tr>
      <td align="center" style="padding-top: 0; padding-right: {p}px; padding-bottom: 32px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <a href="{_esc(url)}" target="_blank" style="font-family: {_brand(brand, 'font_stack')}; font-size: 14px; color: {_brand(brand, 'color_primary')}; text-decoration: underline;">
          {_esc(text)}
        </a>
      </td>
    </tr>"""


def render_stats_grid(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    stats = props.get("stats", [])
    if not stats:
        return ""
    w = _w(brand)
    p = _p(brand)
    content_width = w - (p * 2)
    cols = min(len(stats), 4)
    cell_width = content_width // cols

    cells = []
    for i, s in enumerate(stats):
        cells.append(f"""
            <td width="{cell_width}" align="center" style="padding-top: 16px; padding-right: 8px; padding-bottom: 16px; padding-left: 8px; background-color: {_brand(brand, 'color_surface_light')}; border-radius: 8px;">
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_mono')}; font-size: 28px; font-weight: 700; color: {_brand(brand, 'color_primary')}; line-height: 1.2;">
                {_esc(s.get('value', ''))}
              </p>
              <p style="margin: 6px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 12px; color: {_brand(brand, 'color_text_muted')}; line-height: 1.4;">
                {_esc(s.get('label', ''))}
              </p>
            </td>""")
        if i < len(stats) - 1:
            cells.append(f'\n            <td width="8" style="width: 8px;">&nbsp;</td>')

    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 16px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          <tr>
            {''.join(cells)}
          </tr>
        </table>
      </td>
    </tr>"""


def render_bullet_list(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    items = props.get("items", [])
    if not items:
        return ""
    icon = props.get("icon", "&#10003;")
    icon_color = props.get("iconColor") or _brand(brand, "color_primary")
    p = _p(brand)

    rows = []
    for item in items:
        if isinstance(item, str):
            text = item
            description = ""
        else:
            text = item.get("text") or item.get("title") or ""
            description = item.get("description", "")
        desc_html = f'<br><span style="color: {_brand(brand, "color_text_muted")}; font-size: 13px;">{_esc(description)}</span>' if description else ""
        rows.append(f"""
          <tr>
            <td width="28" valign="top" style="padding-top: 8px; padding-bottom: 8px; font-family: {_brand(brand, 'font_stack')}; font-size: 16px; color: {icon_color}; font-weight: 700;">
              {icon}
            </td>
            <td valign="top" style="padding-top: 8px; padding-bottom: 8px; padding-left: 8px; font-family: {_brand(brand, 'font_stack')}; font-size: 14px; line-height: 1.6; color: {_brand(brand, 'color_text_secondary')};">
              {_esc(text)}{desc_html}
            </td>
          </tr>""")

    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 24px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          {''.join(rows)}
        </table>
      </td>
    </tr>"""


def render_numbered_steps(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    steps = props.get("steps", [])
    if not steps:
        return ""
    p = _p(brand)

    rows = []
    for i, step in enumerate(steps):
        desc_html = ""
        if step.get("description"):
            desc_html = f"""
              <p style="margin: 4px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; color: {_brand(brand, 'color_text_secondary')}; line-height: 1.5;">
                {_esc(step['description'])}
              </p>"""
        rows.append(f"""
          <tr>
            <td width="36" valign="top" style="padding-top: 12px; padding-bottom: 12px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="32" height="32" align="center" valign="middle" style="background-color: {_brand(brand, 'color_primary')}; border-radius: 50%; font-family: {_brand(brand, 'font_stack')}; font-size: 14px; font-weight: 700; color: {_brand(brand, 'color_white')};">
                    {i + 1}
                  </td>
                </tr>
              </table>
            </td>
            <td valign="top" style="padding-top: 12px; padding-bottom: 12px; padding-left: 12px;">
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-weight: 600; color: {_brand(brand, 'color_text_primary')}; line-height: 1.4;">
                {_esc(step.get('title', ''))}
              </p>
              {desc_html}
            </td>
          </tr>""")
        if i < len(steps) - 1:
            rows.append(f"""
          <tr>
            <td width="36" style="padding: 0;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr><td width="32" align="center" style="padding: 0;"><div style="width: 2px; height: 12px; background-color: {_brand(brand, 'color_surface_border')}; margin: 0 auto;"></div></td></tr>
              </table>
            </td>
            <td></td>
          </tr>""")

    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 24px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          {''.join(rows)}
        </table>
      </td>
    </tr>"""


def render_agenda_list(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    items = props.get("items", [])
    if not items:
        return ""
    p = _p(brand)

    rows = []
    for i, item in enumerate(items):
        bg = _brand(brand, "color_surface_light") if i % 2 == 0 else _brand(brand, "color_white")
        if isinstance(item, str):
            title = item
            time_str = ""
            description = ""
        else:
            title = item.get("title") or item.get("text") or str(item)
            time_str = item.get("time", "")
            description = item.get("description", "")
        time_td = f'<td width="80" valign="top" style="font-family: {_brand(brand, "font_mono")}; font-size: 13px; color: {_brand(brand, "color_primary")}; font-weight: 600;">{_esc(time_str)}</td>' if time_str else ""
        desc_html = f'<br><span style="color: {_brand(brand, "color_text_muted")}; font-size: 12px;">{_esc(description)}</span>' if description else ""
        rows.append(f"""
          <tr>
            <td style="padding-top: 12px; padding-right: 16px; padding-bottom: 12px; padding-left: 16px; background-color: {bg}; border-radius: 6px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  {time_td}
                  <td valign="top" style="font-family: {_brand(brand, 'font_stack')}; font-size: 14px; color: {_brand(brand, 'color_text_primary')}; line-height: 1.5;">
                    {_esc(title)}{desc_html}
                  </td>
                </tr>
              </table>
            </td>
          </tr>""")

    return f"""
    <tr>
      <td style="padding-top: 8px; padding-right: {p}px; padding-bottom: 24px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          {''.join(rows)}
        </table>
      </td>
    </tr>"""


def render_feature_list(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    features = props.get("features", [])
    if not features:
        return ""
    p = _p(brand)

    cards = []
    for f in features:
        desc_html = ""
        if f.get("description"):
            desc_html = f"""
              <p style="margin: 6px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; color: {_brand(brand, 'color_text_secondary')}; line-height: 1.5;">
                {_esc(f['description'])}
              </p>"""
        cards.append(f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-bottom: 16px;">
          <tr>
            <td style="padding-top: 16px; padding-right: 20px; padding-bottom: 16px; padding-left: 20px; background-color: {_brand(brand, 'color_surface_light')}; border-radius: 8px; border-left: 4px solid {_brand(brand, 'color_primary')};">
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-weight: 600; color: {_brand(brand, 'color_text_primary')}; line-height: 1.4;">
                {_esc(f.get('title', ''))}
              </p>
              {desc_html}
            </td>
          </tr>
        </table>""")

    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 24px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        {''.join(cards)}
      </td>
    </tr>"""


def render_speaker_list(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    speakers = props.get("speakers", [])
    if not speakers:
        return ""
    p = _p(brand)

    rows = []
    for s in speakers:
        title_html = ""
        if s.get("title"):
            title_html = f"""
              <p style="margin: 2px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; color: {_brand(brand, 'color_text_muted')}; line-height: 1.4;">
                {_esc(s['title'])}
              </p>"""
        rows.append(f"""
          <tr>
            <td style="padding-top: 10px; padding-bottom: 10px; border-bottom: 1px solid {_brand(brand, 'color_surface_border')};">
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-weight: 600; color: {_brand(brand, 'color_text_primary')}; line-height: 1.4;">
                {_esc(s.get('name', ''))}
              </p>
              {title_html}
            </td>
          </tr>""")

    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 24px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          {''.join(rows)}
        </table>
      </td>
    </tr>"""


def render_callout_box(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    title = props.get("title", "")
    text = props.get("text", "")
    bg_color = props.get("bgColor") or _brand(brand, "color_surface_light")
    border_color = props.get("borderColor") or _brand(brand, "color_primary")
    p = _p(brand)
    title_html = ""
    if title:
        title_html = f"""
              <p style="margin: 0 0 8px 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-weight: 700; color: {_brand(brand, 'color_text_primary')}; line-height: 1.4;">
                {_esc(title)}
              </p>"""
    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 16px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          <tr>
            <td style="padding-top: 20px; padding-right: 24px; padding-bottom: 20px; padding-left: 24px; background-color: {bg_color}; border-left: 4px solid {border_color}; border-radius: 8px;">
              {title_html}
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 14px; color: {_brand(brand, 'color_text_secondary')}; line-height: 1.6;">
                {_nl2br(text)}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def render_ps_block(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    text = props.get("text", "")
    if not text:
        return ""
    p = _p(brand)
    return f"""
    <tr>
      <td style="padding-top: 0; padding-right: {p}px; padding-bottom: 32px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; font-style: italic; color: {_brand(brand, 'color_text_muted')}; line-height: 1.6;">
          <strong>P.S.</strong> {_nl2br(text)}
        </p>
      </td>
    </tr>"""


def render_divider(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    p = _p(brand)
    return f"""
    <tr>
      <td style="padding-top: 0; padding-right: {p}px; padding-bottom: 0; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="border-top: 1px solid {_brand(brand, 'color_surface_border')}; font-size: 1px; line-height: 1px; height: 1px;">
              &nbsp;
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def render_subheading(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    text = props.get("text", "")
    p = _p(brand)
    return f"""
    <tr>
      <td style="padding-top: 24px; padding-right: {p}px; padding-bottom: 8px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <h2 style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 20px; font-weight: 700; color: {_brand(brand, 'color_text_primary')}; line-height: 1.3;">
          {_esc(text)}
        </h2>
      </td>
    </tr>"""


def render_quote(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    text = props.get("text", "")
    author = props.get("author", "")
    p = _p(brand)
    author_html = ""
    if author:
        author_html = f"""
              <p style="margin: 10px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; font-weight: 600; color: {_brand(brand, 'color_text_muted')};">
                &mdash; {_esc(author)}
              </p>"""
    return f"""
    <tr>
      <td style="padding-top: 16px; padding-right: {p}px; padding-bottom: 16px; padding-left: {p}px; background-color: {_brand(brand, 'color_white')};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
          <tr>
            <td style="padding-top: 20px; padding-right: 24px; padding-bottom: 20px; padding-left: 24px; border-left: 4px solid {_brand(brand, 'color_lime')}; background-color: {_brand(brand, 'color_surface_light')}; border-radius: 0 8px 8px 0;">
              <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 15px; font-style: italic; color: {_brand(brand, 'color_text_primary')}; line-height: 1.6;">
                &ldquo;{_esc(text)}&rdquo;
              </p>
              {author_html}
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def render_footer(props: Dict[str, Any], brand: Dict[str, str]) -> str:
    p = _p(brand)
    social_entries = [
        ("facebook", _brand(brand, "social_facebook_url"), _brand(brand, "social_facebook_label"), _brand(brand, "social_facebook_icon")),
        ("linkedin", _brand(brand, "social_linkedin_url"), _brand(brand, "social_linkedin_label"), _brand(brand, "social_linkedin_icon")),
        ("youtube",  _brand(brand, "social_youtube_url"),  _brand(brand, "social_youtube_label"),  _brand(brand, "social_youtube_icon")),
        ("instagram",_brand(brand, "social_instagram_url"),_brand(brand, "social_instagram_label"),_brand(brand, "social_instagram_icon")),
    ]
    social_html = "".join(
        f'<td style="padding-left: 6px; padding-right: 6px;">'
        f'<a href="{url}" target="_blank" style="text-decoration: none;">'
        f'<img src="{icon}" alt="{label}" width="24" height="24" style="display: block; border: 0;" />'
        f'</a></td>'
        for _, url, label, icon in social_entries
        if url
    )
    return f"""
    <tr>
      <td style="padding-top: 32px; padding-right: {p}px; padding-bottom: 32px; padding-left: {p}px; background-color: {_brand(brand, 'color_surface_light')}; border-top: 1px solid {_brand(brand, 'color_surface_border')};">
        <!-- Social Icons -->
        <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin: 0 auto 20px auto;">
          <tr>{social_html}</tr>
        </table>

        <!-- Company Info -->
        <p style="margin: 0 0 8px 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 13px; color: {_brand(brand, 'color_text_muted')}; text-align: center; line-height: 1.5;">
          {_brand(brand, 'company_name')} &middot; {_brand(brand, 'company_legal_name')}
        </p>
        <p style="margin: 0 0 8px 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 12px; color: {_brand(brand, 'color_text_muted')}; text-align: center; line-height: 1.5;">
          {_brand(brand, 'company_full_address')}
        </p>
        <p style="margin: 0 0 16px 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 12px; color: {_brand(brand, 'color_text_muted')}; text-align: center; line-height: 1.5;">
          <a href="mailto:{_brand(brand, 'company_email')}" style="color: {_brand(brand, 'color_primary')}; text-decoration: none;">{_brand(brand, 'company_email')}</a>
          &middot; {_brand(brand, 'company_phone')}
        </p>

        <!-- Unsubscribe -->
        <p style="margin: 0 0 8px 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 11px; color: {_brand(brand, 'color_text_muted')}; text-align: center; line-height: 1.5;">
          <a href="{_brand(brand, 'merge_tag_unsubscribe')}" style="color: {_brand(brand, 'color_text_muted')}; text-decoration: underline;">Unsubscribe</a>
          &middot;
          <a href="{_brand(brand, 'company_url')}/privacy" style="color: {_brand(brand, 'color_text_muted')}; text-decoration: underline;">Privacy Policy</a>
        </p>
        <p style="margin: 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 11px; color: {_brand(brand, 'color_text_muted')}; text-align: center;">
          &copy; {_brand(brand, 'merge_tag_current_year')} {_brand(brand, 'company_legal_name')} All rights reserved.
        </p>
        <p style="margin: 4px 0 0 0; padding: 0; font-family: {_brand(brand, 'font_stack')}; font-size: 10px; color: {_brand(brand, 'color_text_muted')}; text-align: center;">
          {_brand(brand, 'merge_tag_list_address')}
        </p>
      </td>
    </tr>"""


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_RENDERERS = {
    "header":         render_header,
    "hero":           render_hero,
    "hero_image":     render_hero_image,
    "accent_bar":     render_accent_bar,
    "body":           render_body,
    "greeting":       render_greeting,
    "signoff":        render_signoff,
    "cta":            render_cta,
    "secondary_cta":  render_secondary_cta,
    "stats_grid":     render_stats_grid,
    "bullet_list":    render_bullet_list,
    "numbered_steps": render_numbered_steps,
    "agenda_list":    render_agenda_list,
    "feature_list":   render_feature_list,
    "speaker_list":   render_speaker_list,
    "callout_box":    render_callout_box,
    "ps_block":       render_ps_block,
    "divider":        render_divider,
    "subheading":     render_subheading,
    "quote":          render_quote,
    "footer":         render_footer,
}


def render_block(block_type: str, props: Dict[str, Any], brand: Dict[str, str]) -> str:
    """
    Render a single block row.

    Args:
        block_type: One of the known block type strings (e.g. 'header', 'hero').
        props:      Property dict for the block (varies per type).
        brand:      Flat brand context dict from get_brand_context().

    Returns:
        HTML string (one or more <tr> elements).

    Raises:
        ValueError: If block_type is unknown.
    """
    fn = _RENDERERS.get(block_type)
    if fn is None:
        raise ValueError(f"Unknown block type: {block_type!r}")
    return fn(props or {}, brand or {})


def render_block_tree(tree: Dict[str, Any], brand: Dict[str, str]) -> str:
    """
    Render a full block tree into a body_html string (the <tr> rows only,
    not the outer email wrapper).

    The outer email wrapper is produced by email_renderer.py — we just supply
    the rows that go inside the main <table>.

    Args:
        tree:  {"blocks": [{id, type, props}, ...]}
        brand: Brand context from get_brand_context().

    Returns:
        Concatenated HTML string of all block rows.
    """
    blocks = (tree or {}).get("blocks", [])
    parts: List[str] = []
    for block in blocks:
        block_type = block.get("type", "")
        props = block.get("props") or {}
        html = render_block(block_type, props, brand or {})
        if html:
            parts.append(html)
    return "".join(parts)
