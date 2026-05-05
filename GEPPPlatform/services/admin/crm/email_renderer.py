"""
CRM Email Renderer — variable substitution for CRM email templates.

Regex-based (NOT Jinja) per brief.md requirement.  Variable syntax:
  {{user.name}}            {{user.email}}            {{user.first_name}}
  {{org.name}}             {{last_login_date}}        {{days_since_last_login}}
  {{transaction_count_30d}} {{reward_points}}         {{next_payment_date}}
  {{unsubscribe_url}}      {{ custom.<key> }}          (spaces around tag optional)

Rules:
- HTML-escape variable values when inserting into body_html (prevent XSS).
- Do NOT escape when inserting into body_plain.
- Unknown / missing variables → replaced with empty string + WARNING logged.

Public API:
    render(template_row, user_location, org, extra_vars={}) -> (subject, html, plain)
"""

import re
import logging
from html import escape
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported variable registry
# ---------------------------------------------------------------------------
# Maps canonical variable name (as it appears between {{ }}) →
# a dotted key path used to look up the value from the render context.
# Custom variables are handled separately via the 'custom.*' pattern.
_KNOWN_VARIABLES = {
    "user.name":                  "user.name",
    "user.email":                 "user.email",
    "user.first_name":            "user.first_name",
    "org.name":                   "org.name",
    "last_login_date":            "last_login_date",
    "days_since_last_login":      "days_since_last_login",
    "transaction_count_30d":      "transaction_count_30d",
    "reward_points":              "reward_points",
    "next_payment_date":          "next_payment_date",
    "unsubscribe_url":            "unsubscribe_url",
}

# Matches {{ varname }} with optional surrounding spaces.
# Group 1 captures the raw variable name (stripped).
_VAR_PATTERN = re.compile(r'\{\{\s*([^}]+?)\s*\}\}')


def _build_context(
    template_row: Dict[str, Any],
    user_location: Optional[Dict[str, Any]],
    org: Optional[Dict[str, Any]],
    extra_vars: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Flatten all variable sources into a single dict keyed by canonical variable name.

    Priority (highest first):
        extra_vars > user_location fields > org fields
    """
    ctx: Dict[str, Any] = {}

    # org.*
    if org:
        ctx["org.name"] = org.get("name") or org.get("company_name") or ""

    # user.* and profile-derived fields
    if user_location:
        first = user_location.get("firstname") or user_location.get("first_name") or ""
        last  = user_location.get("lastname")  or user_location.get("last_name")  or ""
        full  = f"{first} {last}".strip() or user_location.get("name") or ""
        ctx["user.name"]       = full
        ctx["user.first_name"] = first
        ctx["user.email"]      = user_location.get("email") or ""

        # Profile fields (pre-computed and stored on the user_location dict or separately)
        for field in (
            "last_login_date",
            "days_since_last_login",
            "transaction_count_30d",
            "reward_points",
            "next_payment_date",
        ):
            val = user_location.get(field)
            if val is not None:
                ctx[field] = val

    # unsubscribe_url may be passed in extra_vars or template_row metadata
    if "unsubscribe_url" not in ctx:
        ctx["unsubscribe_url"] = (extra_vars or {}).get("unsubscribe_url", "")

    # extra_vars overrides everything (caller-supplied custom.* and overrides)
    for k, v in (extra_vars or {}).items():
        ctx[k] = v

    return ctx


def _resolve_value(var_name: str, context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve a variable name from context.  Returns None if not found.

    Handles:
        "custom.<key>"  → context["custom.<key>"] or context["custom"]["key"]
        everything else → context[var_name]
    """
    # Direct lookup first
    if var_name in context:
        val = context[var_name]
        return str(val) if val is not None else ""

    # custom.* nested lookup
    if var_name.startswith("custom."):
        key = var_name[7:]  # strip "custom."
        # Try nested dict
        custom_dict = context.get("custom")
        if isinstance(custom_dict, dict) and key in custom_dict:
            val = custom_dict[key]
            return str(val) if val is not None else ""

    return None


def _substitute(text: str, context: Dict[str, Any], html_escape: bool) -> str:
    """
    Replace all {{ var }} occurrences in *text* using *context*.

    Args:
        text:        Template string (HTML or plain text).
        context:     Flat dict of resolved variable values.
        html_escape: If True, escape HTML-special characters in substituted values.

    Returns:
        String with all variables replaced.
    """
    def replace(match: re.Match) -> str:
        var_name = match.group(1).strip()
        value = _resolve_value(var_name, context)
        if value is None:
            logger.warning(
                "email_renderer: unknown/missing variable '%s' — replacing with empty string",
                var_name,
            )
            value = ""
        return escape(value) if html_escape else value

    return _VAR_PATTERN.sub(replace, text)


def render(
    template_row: Dict[str, Any],
    user_location: Optional[Dict[str, Any]],
    org: Optional[Dict[str, Any]],
    extra_vars: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str]:
    """
    Render a CRM email template into (subject, html, plain).

    Args:
        template_row:   Dict with keys: subject, body_html, body_plain
                        (matches crm_templates model columns).
        user_location:  Dict with user fields (firstname, lastname, email, etc.)
                        and optionally pre-computed profile fields
                        (days_since_last_login, transaction_count_30d, …).
                        May be None for broadcast/org-scoped sends.
        org:            Dict with organisation fields (name, …).
                        May be None for user-scoped sends.
        extra_vars:     Additional variables to inject (override anything).
                        Supports 'custom.<key>' keys and 'unsubscribe_url'.

    Returns:
        (subject, html, plain) — all variables substituted.

    Raises:
        Nothing — missing variables are logged and replaced with "".
    """
    if extra_vars is None:
        extra_vars = {}

    context = _build_context(template_row, user_location, org, extra_vars)

    subject_raw  = template_row.get("subject", "")
    html_raw     = template_row.get("body_html", "")
    plain_raw    = template_row.get("body_plain", "")

    # Ensure unsubscribe_url is in context — fill lazily from token utility if missing
    if not context.get("unsubscribe_url"):
        try:
            from .unsubscribe_token import make_unsub_url  # lazy to avoid circular
            user_email = context.get("user.email") or ""
            if user_email:
                context["unsubscribe_url"] = make_unsub_url(user_email)
        except Exception as exc:
            logger.warning("email_renderer: could not generate unsubscribe_url: %s", exc)

    subject = _substitute(subject_raw, context, html_escape=False)
    html    = _substitute(html_raw,    context, html_escape=True)
    plain   = _substitute(plain_raw,   context, html_escape=False)

    # Auto-inject unsubscribe footer if the rendered output doesn't already reference it
    unsub_url = context.get("unsubscribe_url", "")
    if unsub_url:
        if "unsubscribe_url" not in html_raw.lower() and "unsubscribe" not in html.lower():
            html += (
                '\n<p style="text-align:center;color:#888;font-size:12px;margin-top:24px;">'
                f'Don\'t want these emails? <a href="{unsub_url}">Unsubscribe</a>.'
                "</p>"
            )
        if "unsubscribe_url" not in plain_raw.lower() and "unsubscribe" not in plain.lower():
            plain += f"\n\nUnsubscribe: {unsub_url}\n"

    return subject, html, plain
