"""POST /api/public/customer-leads — GEPP.me contact-form lead intake.

Strictly origin-allowlisted to https://gepp.me. Submissions are persisted in
`crm_leads` so the Backoffice Marketing tab can use them immediately.
"""

import html
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ...exceptions import BadRequestException

logger = logging.getLogger(__name__)

# Origins permitted to call this endpoint. The product requirement is exact:
# accept https://gepp.me only, not sibling origins.
ALLOWED_ORIGINS = frozenset({
    "https://gepp.me",
})

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MAX_TEXT_LEN = 1000
_MAX_MESSAGE_LEN = 5000
_DEFAULT_NOTIFY_EMAIL = "hello@gepp.me"


def is_origin_allowed(origin: Optional[str]) -> bool:
    """True when the request Origin header matches our allowlist exactly."""
    return bool(origin) and origin in ALLOWED_ORIGINS


def _clean(value: Any, *, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


def handle_customer_lead_capture(
    data: dict,
    db: Session,
    request_meta: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Validates + persists a marketing-site lead submission.

    Body:
      name (required), email (required), company (required),
      type ('existing' | 'new'), message, source (default 'landing-page'),
      metadata (object — page URL, referrer, UTM, and other attribution)
    """
    if not isinstance(data, dict):
        raise BadRequestException("Body must be a JSON object")

    name    = _clean(data.get("name") or data.get("fullName"), max_len=_MAX_TEXT_LEN)
    email   = _clean(data.get("email"),   max_len=_MAX_TEXT_LEN)
    company = _clean(data.get("company"), max_len=_MAX_TEXT_LEN)

    if not name:
        raise BadRequestException("name is required")
    if not email:
        raise BadRequestException("email is required")
    if not _EMAIL_RE.match(email):
        raise BadRequestException("email is not a valid address")
    if not company:
        raise BadRequestException("company is required")

    lead_type = _clean(data.get("type") or data.get("lead_type"), max_len=64) or "new"
    if lead_type not in {"existing", "new"}:
        raise BadRequestException("type must be 'existing' or 'new'")

    message      = _clean(data.get("message"), max_len=_MAX_MESSAGE_LEN)
    source_label = _clean(data.get("source"),  max_len=64) or "landing-page"

    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    meta = request_meta or {}
    first_name, last_name = _split_full_name(name)
    page_url = _clean(data.get("pageUrl") or metadata.get("page_url"), max_len=2000)
    referrer = _clean(
        data.get("referrer") or metadata.get("referrer") or meta.get("referrer"),
        max_len=2000,
    )
    source_metadata = {
        "source_site": "gepp.me",
        "source_form": "contact",
        "source_label": source_label,
        "lead_type": lead_type,
        "page_url": page_url,
        "referrer": referrer,
        "origin": meta.get("origin"),
        "ip_address": meta.get("ip_address"),
        "user_agent": meta.get("user_agent"),
        "utm": metadata.get("utm"),
    }
    source_metadata = {k: v for k, v in source_metadata.items() if v not in (None, "", {})}

    from ..admin.crm import lead_service

    lead = lead_service.create_lead(
        db,
        org_id=None,
        data={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "company": company,
            "notes": message,
            "tags": ["gepp_me", "contact_form", lead_type],
        },
        source="web_form",
        source_metadata=source_metadata,
    )
    lead_id = lead.get("id")

    if lead_id:
        lead_service.add_activity(
            db,
            lead_id,
            activity_type="contact_form_submitted",
            properties={
                "name": name,
                "company": company,
                "message": message,
                "lead_type": lead_type,
                "source_metadata": source_metadata,
            },
        )
        db.commit()

    email_status = _send_internal_notification(
        lead_id=lead_id,
        name=name,
        email=email,
        company=company,
        lead_type=lead_type,
        message=message,
        source_metadata=source_metadata,
    )

    logger.info(
        "customer_lead captured lead_id=%s email=%s source=%s origin=%s email_status=%s",
        lead_id, email, source_label, meta.get("origin"), email_status,
    )

    return {
        "ok": True,
        "id": lead_id,
        "source": "web_form",
        "sourceDetail": "gepp.me/contact",
        "emailNotification": email_status,
    }


def _split_full_name(name: str) -> Tuple[str, Optional[str]]:
    parts = [p for p in name.split() if p]
    if not parts:
        return "", None
    return parts[0], " ".join(parts[1:]) or None


def _parse_cc(value: Optional[str]) -> List[Dict[str, str]]:
    if not value:
        return []
    emails = [v.strip() for v in value.split(",") if v.strip()]
    return [{"email": e} for e in emails if _EMAIL_RE.match(e)]


def _send_internal_notification(
    *,
    lead_id: Optional[int],
    name: str,
    email: str,
    company: str,
    lead_type: str,
    message: Optional[str],
    source_metadata: Dict[str, Any],
) -> str:
    """Send a non-fatal internal notification through the Mailchimp Lambda path."""
    to_email = os.environ.get("GEPP_ME_LEAD_NOTIFY_EMAIL", _DEFAULT_NOTIFY_EMAIL).strip()
    if not to_email:
        return "skipped"

    page_url = source_metadata.get("page_url") or "-"
    referrer = source_metadata.get("referrer") or "-"
    subject = f"New GEPP.me contact request: {company}"
    safe = {
        "name": html.escape(name),
        "email": html.escape(email),
        "company": html.escape(company),
        "lead_type": html.escape(lead_type),
        "message": html.escape(message or "-").replace("\n", "<br />"),
        "page_url": html.escape(str(page_url)),
        "referrer": html.escape(str(referrer)),
        "lead_id": html.escape(str(lead_id or "-")),
    }
    html_content = f"""
        <h2>New GEPP.me contact request</h2>
        <p><strong>Name:</strong> {safe["name"]}</p>
        <p><strong>Email:</strong> {safe["email"]}</p>
        <p><strong>Company:</strong> {safe["company"]}</p>
        <p><strong>Type:</strong> {safe["lead_type"]}</p>
        <p><strong>CRM Lead ID:</strong> {safe["lead_id"]}</p>
        <p><strong>Page:</strong> {safe["page_url"]}</p>
        <p><strong>Referrer:</strong> {safe["referrer"]}</p>
        <p><strong>Message:</strong><br />{safe["message"]}</p>
    """
    text_content = (
        "New GEPP.me contact request\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Company: {company}\n"
        f"Type: {lead_type}\n"
        f"CRM Lead ID: {lead_id or '-'}\n"
        f"Page: {page_url}\n"
        f"Referrer: {referrer}\n"
        f"Message: {message or '-'}\n"
    )

    try:
        from ..admin.crm import crm_service

        result = crm_service.send_via_email_lambda(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            from_name=os.environ.get("GEPP_ME_LEAD_FROM_NAME", "GEPP Lead Intake"),
            from_email=os.environ.get("GEPP_ME_LEAD_FROM_EMAIL"),
            cc_emails=_parse_cc(os.environ.get("GEPP_ME_LEAD_NOTIFY_CC")),
            metadata={
                "lead_id": str(lead_id or ""),
                "source_site": "gepp.me",
                "source_form": "contact",
            },
            tags=["gepp-me-contact", f"lead-type-{lead_type}"],
        )
    except Exception as exc:
        logger.warning("customer_lead notification raised: %s", exc)
        return "failed"

    if result.get("success"):
        return "sent"
    logger.warning("customer_lead notification failed: %s", result.get("error"))
    return "failed"
