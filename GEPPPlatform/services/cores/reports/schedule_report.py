"""
Scheduled report notification job.

Runs every hour (e.g. via AWS Lambda + CloudWatch Events). Queries
organization_notification_settings for schedule-type events (RPT_TXN_*),
filters by current hour in Thai time (Asia/Bangkok) matching email_time
and is_active. For each matching setting, checks day/date (Monday for
weekly/bi-weekly, 1st for monthly) and builds date_from/date_to for the
report period, then calls the same export logic as _handle_export_pdf_report
to get PDF export data (and optionally send to recipients).

Event types (interval): RPT_TXN_DAILY, RPT_TXN_WEEKLY, RPT_TXN_MONTHLY, RPT_TXN_BIWEEKLY.
"""

# Ensure full model registry is loaded (e.g. UserLocation.input_channels from models/__init__.py)
# so ORM queries in reports_service do not raise "Mapper has no property 'input_channels'".
import GEPPPlatform.models  # noqa: F401

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import boto3

THAI_TZ = ZoneInfo("Asia/Bangkok")

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Schedule-type events (report transaction notifications by interval)
SCHEDULED_REPORT_EVENTS = (
    "RPT_TXN_DAILY",
    "RPT_TXN_WEEKLY",
    "RPT_TXN_MONTHLY",
    "RPT_TXN_BIWEEKLY",
)


def _thai_date_to_utc_iso(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0, microsecond: int = 0
) -> str:
    """Build a datetime in Thai time and return UTC ISO string for filters."""
    local_dt = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=THAI_TZ)
    return local_dt.astimezone(timezone.utc).isoformat()


def should_run_scheduled_event(event: str, now_thai: datetime) -> bool:
    """
    Return True if today (Thai time) is the correct day/date for this event.
    - RPT_TXN_DAILY: every day
    - RPT_TXN_WEEKLY: Monday only (report for last week)
    - RPT_TXN_BIWEEKLY: Monday only, every other week (ISO week number even)
    - RPT_TXN_MONTHLY: 1st of month only (report for last month)
    """
    if event == "RPT_TXN_DAILY":
        return True
    if event == "RPT_TXN_WEEKLY":
        return now_thai.weekday() == 0  # Monday
    if event == "RPT_TXN_BIWEEKLY":
        if now_thai.weekday() != 0:
            return False
        iso_week = now_thai.isocalendar()[1]
        return iso_week % 2 == 0  # Run on Mondays of even ISO weeks
    if event == "RPT_TXN_MONTHLY":
        return now_thai.day == 1
    return False


def get_date_range_for_scheduled_event(
    event: str, now_thai: datetime
) -> Optional[Tuple[str, str]]:
    """
    Return (date_from_iso, date_to_iso) in UTC for the report period.
    - Daily: yesterday (full day Thai)
    - Weekly: last week Mon 00:00 - Sun 23:59:59 Thai
    - Bi-weekly: previous 14 days ending yesterday (Mon-Sun of prior 2 weeks)
    - Monthly: previous month 1st 00:00 - last day 23:59:59 Thai
    Returns None if this event should not run today (caller can still use should_run_scheduled_event).
    """
    if event == "RPT_TXN_DAILY":
        yesterday = now_thai.date() - timedelta(days=1)
        date_from = _thai_date_to_utc_iso(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, 0)
        date_to = _thai_date_to_utc_iso(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, 999999)
        return (date_from, date_to)

    if event == "RPT_TXN_WEEKLY":
        # Last week: Monday to Sunday
        last_monday = now_thai.date() - timedelta(days=7)
        last_sunday = last_monday + timedelta(days=6)
        date_from = _thai_date_to_utc_iso(last_monday.year, last_monday.month, last_monday.day, 0, 0, 0, 0)
        date_to = _thai_date_to_utc_iso(last_sunday.year, last_sunday.month, last_sunday.day, 23, 59, 59, 999999)
        return (date_from, date_to)

    if event == "RPT_TXN_BIWEEKLY":
        # Previous 14 days ending yesterday (so we're on Monday, period = 2 weeks ending last Sunday)
        this_monday = now_thai.date()
        period_end = this_monday - timedelta(days=1)
        period_start = period_end - timedelta(days=13)
        date_from = _thai_date_to_utc_iso(period_start.year, period_start.month, period_start.day, 0, 0, 0, 0)
        date_to = _thai_date_to_utc_iso(period_end.year, period_end.month, period_end.day, 23, 59, 59, 999999)
        return (date_from, date_to)

    if event == "RPT_TXN_MONTHLY":
        # Previous month
        first_this_month = now_thai.replace(day=1)
        last_prev_month_dt = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month_dt.replace(day=1)
        date_from = _thai_date_to_utc_iso(first_prev_month.year, first_prev_month.month, first_prev_month.day, 0, 0, 0, 0)
        date_to = _thai_date_to_utc_iso(
            last_prev_month_dt.year, last_prev_month_dt.month, last_prev_month_dt.day, 23, 59, 59, 999999
        )
        return (date_from, date_to)

    return None


def get_report_period_display(event: str, now_thai: datetime) -> Tuple[str, str]:
    """
    Return (period_display, period_label) in Thai calendar dates for email display.
    Uses the same logical periods as get_date_range_for_scheduled_event but without
    UTC conversion, so the displayed dates match what users expect (e.g. weekly = Mon–Sun in Thai).
    """
    if event == "RPT_TXN_DAILY":
        d = (now_thai.date() - timedelta(days=1)).isoformat()
        return d, "Report date"
    if event == "RPT_TXN_WEEKLY":
        last_monday = now_thai.date() - timedelta(days=7)
        last_sunday = last_monday + timedelta(days=6)
        return f"{last_monday.isoformat()} — {last_sunday.isoformat()}", "Report period"
    if event == "RPT_TXN_BIWEEKLY":
        this_monday = now_thai.date()
        period_end = this_monday - timedelta(days=1)
        period_start = period_end - timedelta(days=13)
        return f"{period_start.isoformat()} — {period_end.isoformat()}", "Report period"
    if event == "RPT_TXN_MONTHLY":
        first_this_month = now_thai.replace(day=1)
        last_prev_month_dt = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month_dt.replace(day=1)
        return (
            f"{first_prev_month.date().isoformat()} — {last_prev_month_dt.date().isoformat()}",
            "Report period",
        )
    return "", "Report period"


def get_scheduled_settings_for_current_hour(db: Session) -> List[Dict[str, Any]]:
    """
    Query organization_notification_settings for rows that:
    - Have email_time set (scheduled email, not instant)
    - Are is_active
    - Event is one of RPT_TXN_DAILY, RPT_TXN_WEEKLY, RPT_TXN_MONTHLY, RPT_TXN_BIWEEKLY
    - Current hour in Thai time (Asia/Bangkok, UTC+7) matches email_time hour

    Returns list of dicts: id, organization_id, event, role_id, email_time, ...
    """
    result = db.execute(
        text("""
            SELECT id, organization_id, event, role_id, channels_mask, email_time
            FROM organization_notification_settings
            WHERE email_time IS NOT NULL
              AND is_active = TRUE
              AND deleted_date IS NULL
              AND event IN :events
              AND EXTRACT(HOUR FROM (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Bangkok')) = EXTRACT(HOUR FROM email_time)
            ORDER BY organization_id, event
        """).bindparams(events=tuple(SCHEDULED_REPORT_EVENTS)),
    )
    rows = result.fetchall()
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "event": r.event,
            "role_id": r.role_id,
            "channels_mask": r.channels_mask,
            "email_time": str(r.email_time)[:5] if r.email_time else None,
        }
        for r in rows
    ]


def get_user_emails_by_org_and_role(
    db: Session, organization_id: int, role_id: int
) -> List[str]:
    """
    Get distinct, non-empty emails for users in the given organization
    with the given organization_role_id (user_locations.organization_role_id).
    """
    result = db.execute(
        text("""
            SELECT DISTINCT ul.email
            FROM user_locations ul
            WHERE ul.organization_id = :organization_id
              AND ul.organization_role_id = :role_id
              AND ul.is_user = TRUE
              AND (ul.deleted_date IS NULL OR ul.deleted_date > CURRENT_TIMESTAMP)
              AND ul.is_active = TRUE
              AND ul.email IS NOT NULL
              AND TRIM(ul.email) != ''
        """),
        {"organization_id": organization_id, "role_id": role_id},
    )
    rows = result.fetchall()
    return [r.email.strip() for r in rows if r.email and r.email.strip()]


def get_one_user_context_for_org_role(
    db: Session, organization_id: int, role_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get one user (user_locations row) as a current_user-style dict for export.
    Used as the "acting user" for PDF export (display name, timezone, org_id).
    """
    result = db.execute(
        text("""
            SELECT ul.id, ul.organization_id, ul.display_name, ul.name_en, ul.name_th,
                   ul.username, ul.email, ul.profile_image_url
            FROM user_locations ul
            WHERE ul.organization_id = :organization_id
              AND ul.organization_role_id = :role_id
              AND ul.is_user = TRUE
              AND (ul.deleted_date IS NULL OR ul.deleted_date > CURRENT_TIMESTAMP)
              AND ul.is_active = TRUE
            LIMIT 1
        """),
        {"organization_id": organization_id, "role_id": role_id},
    )
    row = result.fetchone()
    if not row:
        return None
    display = (
        (row.display_name or row.name_en or row.name_th or row.username or row.email or "")
    ).strip() or str(row.id)
    return {
        "id": row.id,
        "user_id": row.id,
        "uid": row.id,
        "organization_id": row.organization_id,
        "timezone": "Asia/Bangkok",
        "display_name": display,
        "name_en": row.name_en,
        "name_th": row.name_th,
        "username": row.username,
        "email": row.email,
        "profile_image_url": row.profile_image_url,
    }


def _send_email_via_lambda(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    pdf_attachment_base64: Optional[str] = None,
    pdf_filename: Optional[str] = None,
) -> bool:
    """
    Send email via Lambda (same as auth_handlers). Optional PDF attachment.
    """
    try:
        lambda_function_name = os.environ.get("EMAIL_LAMBDA_FUNCTION", "PROD-GEPPEmailNotification")
        message = {
            "from_email": os.environ.get("EMAIL_FROM", "noreply@gepp.me"),
            "from_name": os.environ.get("EMAIL_FROM_NAME", "GEPP Platform"),
            "to": [{"email": to_email, "type": "to"}],
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            message["text"] = text_content
        if pdf_attachment_base64 and pdf_filename:
            message["attachments"] = [
                {
                    "type": "application/pdf",
                    "name": pdf_filename,
                    "content": pdf_attachment_base64,
                }
            ]
        lambda_client = boto3.client("lambda")
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"data": {"message": message}}).encode("utf-8"),
        )
        response_payload = response.get("Payload").read()
        response_data = json.loads(response_payload)
        if response.get("FunctionError"):
            print(f"[ScheduleReport] Email Lambda error: {response.get('FunctionError')}")
            return False
        if isinstance(response_data, dict) and "body" in response_data:
            body_data = json.loads(response_data.get("body", "{}"))
            if body_data.get("data", {}).get("status") == "success":
                return True
        return False
    except Exception as e:
        print(f"[ScheduleReport] Error sending email via Lambda: {e}")
        logger.exception("Error sending email via Lambda: %s", e)
        return False


def run_scheduled_report_job(db: Session) -> Dict[str, Any]:
    """
    Main job: find settings that match the current hour and day/date.
    For each matching setting, compute date_from/date_to for the report period,
    get one user context for that org+role, and call _handle_export_pdf_report
    to get export data (and optionally PDF). Collects recipients and export
    results per setting.
    """
    from .reports_service import ReportsService
    from .reports_handlers import _handle_export_pdf_report

    try:
        print("[ScheduleReport] Starting scheduled report job (hourly)")
        logger.info("Starting scheduled report job (hourly)")
        now_thai = datetime.now(THAI_TZ)
        print(f"[ScheduleReport] Current Thai time: {now_thai.isoformat()} (hour={now_thai.hour}, date={now_thai.date()})")

        print("[ScheduleReport] Querying organization_notification_settings for current hour...")
        settings = get_scheduled_settings_for_current_hour(db)
        if not settings:
            print("[ScheduleReport] No scheduled notification settings match current hour. Done.")
            logger.info("No scheduled notification settings match current hour")
            return {
                "success": True,
                "message": "No matching schedules",
                "current_thai_hour": now_thai.hour,
                "current_thai_date": now_thai.date().isoformat(),
                "settings_matched": 0,
                "exports": [],
                "recipients": [],
            }

        print(f"[ScheduleReport] Matched {len(settings)} setting(s) for current hour. Processing...")
        logger.info("Matched %s scheduled settings for current hour", len(settings))

        exports: List[Dict[str, Any]] = []
        recipients: List[Dict[str, Any]] = []
        seen = set()
        processed = 0
        skipped = 0

        for s in settings:
            org_id = s["organization_id"]
            role_id = s["role_id"]
            event = s["event"]
            key = (org_id, role_id, event)
            if key in seen:
                continue

            print(f"[ScheduleReport] Checking org_id={org_id} role_id={role_id} event={event}...")
            if not should_run_scheduled_event(event, now_thai):
                print(f"[ScheduleReport]   Skip: wrong day/date for {event} (today={now_thai.date()})")
                logger.debug("Skip event %s: wrong day/date (today %s)", event, now_thai.date())
                skipped += 1
                continue
            seen.add(key)

            date_range = get_date_range_for_scheduled_event(event, now_thai)
            if not date_range:
                print(f"[ScheduleReport]   Skip: no date range for {event}")
                skipped += 1
                continue
            date_from_iso, date_to_iso = date_range
            print(f"[ScheduleReport]   Date range: {date_from_iso[:10]} to {date_to_iso[:10]}")

            emails = get_user_emails_by_org_and_role(db, org_id, role_id)
            if not emails:
                print(f"[ScheduleReport]   Skip: no recipient emails for org_id={org_id} event={event}")
                logger.debug(
                    "Skip org_id=%s event=%s: no recipient emails for this org and report type",
                    org_id,
                    event,
                )
                skipped += 1
                continue
            print(f"[ScheduleReport]   Found {len(emails)} recipient(s)")

            user_context = get_one_user_context_for_org_role(db, org_id, role_id)
            if not user_context:
                print(f"[ScheduleReport]   Skip: no user for org_id={org_id} role_id={role_id}")
                logger.warning("No user for org_id=%s role_id=%s, skipping export", org_id, role_id)
                skipped += 1
                continue

            print(f"[ScheduleReport]   Running PDF export for org_id={org_id} event={event}...")
            filters: Dict[str, Any] = {"date_from": date_from_iso, "date_to": date_to_iso}
            reports_service = ReportsService(db)
            try:
                print(f"Starting export for org_id={org_id} event={event}...")
                export_result = _handle_export_pdf_report(
                    reports_service, int(org_id), filters, user_context
                )
                # Success: API Gateway shape (statusCode 200 + body) or legacy {success, pdf_base64}
                ok = (
                    export_result.get("statusCode") == 200 and bool(export_result.get("body"))
                ) or export_result.get("success", False)
                print(f"[ScheduleReport]   Export finished: success={ok}")
                if ok and emails:
                    pdf_base64 = export_result.get("body") or export_result.get("pdf_base64")
                    filename = export_result.get("filename")
                    if not filename and isinstance(export_result.get("headers"), dict):
                        content_disp = (export_result.get("headers") or {}).get("Content-Disposition") or ""
                        if "filename=" in content_disp:
                            m = re.search(r'filename=["\']?([^"\']+)["\']?', content_disp)
                            if m:
                                filename = m.group(1).strip()
                    if not filename:
                        filename = f"report_{date_from_iso[:10]}_{date_to_iso[:10]}.pdf"
                    period_display, period_label = get_report_period_display(event, now_thai)
                    subject = f"Your scheduled report – {period_display}"
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f6f8; line-height: 1.6; color: #333;">
    <div style="max-width: 560px; margin: 0 auto; padding: 32px 24px;">
        <div style="background: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2c3e50 0%, #27ae60 100%); padding: 28px 24px; text-align: center;">
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">Scheduled Report</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">Your scheduled report is ready. Please find the PDF attached to this email.</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid #27ae60;">
                    <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">{period_label}</p>
                    <p style="margin: 0; font-size: 16px; font-weight: 600; color: #2c3e50;">{period_display}</p>
                </div>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #6c757d;">The attachment <strong style="color: #333;">{filename}</strong> contains your full report.</p>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">If you have any questions, please contact your administrator.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
                    text_content = f"""Scheduled Report – GEPP Platform

Hello,

Your scheduled report is ready. Please find the PDF attached to this email.

{period_label}: {period_display}
Attachment: {filename}

If you have any questions, please contact your administrator.

—
This is an automated message from GEPP Platform. Please do not reply to this email."""
                    for email in emails:
                        email_sent = _send_email_via_lambda(
                            to_email=email,
                            subject=subject,
                            html_content=html_content,
                            text_content=text_content,
                            pdf_attachment_base64=pdf_base64,
                            pdf_filename=filename,
                        )
                        print(f"[ScheduleReport]   Email to {email}: sent={email_sent}")
            except Exception as export_err:
                print(f"[ScheduleReport]   Export failed: {export_err}")
                logger.exception(
                    "Export failed for org_id=%s event=%s: %s", org_id, event, export_err
                )
                export_result = {"success": False, "error": str(export_err)}
            processed += 1
            recipients.append({
                "organization_id": org_id,
                "role_id": role_id,
                "event": event,
                "setting_id": s["id"],
                "email_time": s["email_time"],
                "date_from": date_from_iso,
                "date_to": date_to_iso,
                "emails": emails,
            })
            exports.append({
                "organization_id": org_id,
                "role_id": role_id,
                "event": event,
                "setting_id": s["id"],
                "date_from": date_from_iso,
                "date_to": date_to_iso,
                "export_success": export_result,
                "recipient_count": len(emails),
            })

        print(f"[ScheduleReport] Done. Processed {len(exports)} export(s), skipped {skipped} setting(s).")
        return {
            "success": True,
            "message": f"Processed {len(exports)} export(s), {len(recipients)} recipient group(s), skipped {skipped}",
            "current_thai_hour": now_thai.hour,
            "current_thai_date": now_thai.date().isoformat(),
            "settings_matched": len(settings),
            "exports": exports,
            "recipients": recipients,
        }
    except Exception as e:
        print(f"[ScheduleReport] ERROR: {e}")
        logger.exception("Scheduled report job failed: %s", e)
        now_thai = datetime.now(THAI_TZ)
        return {
            "success": False,
            "error": str(e),
            "current_thai_hour": now_thai.hour,
            "current_thai_date": now_thai.date().isoformat(),
            "settings_matched": 0,
            "exports": [],
            "recipients": [],
        }


def main() -> Dict[str, Any]:
    """
    Entry point for cron/Lambda: get a DB session, run the job, close session.
    """
    from GEPPPlatform.database import get_db_session

    print("[ScheduleReport] main() entry — getting DB session...")
    db = get_db_session()
    try:
        result = run_scheduled_report_job(db)
        print(f"[ScheduleReport] main() done. success={result.get('success')}, exports={len(result.get('exports', []))}")
        logger.info("Scheduled report job result: %s", result)
        return result
    finally:
        db.close()
        print("[ScheduleReport] DB session closed.")


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    AWS Lambda handler. Invoke this on an hourly schedule (e.g. rate(1 hour)).
    """
    return main()


if __name__ == "__main__":
    main()
