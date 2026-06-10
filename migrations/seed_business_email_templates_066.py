#!/usr/bin/env python3
"""
Migration 066 (companion) — seed the business-v3 system email templates.

The SQL companion (`20260604_120000_066_add_system_key_to_crm_email_templates.sql`)
adds the `system_key` column + unique index. This script inserts the editable
template ROWS that mirror the emails gepp-business-v3 currently sends as
hardcoded HTML, so they can be edited from the Backoffice "Email Templates" page.

Templates seeded (all is_system = TRUE, organization_id = NULL, category
'transactional'):
    TXN_CREATED        — new transaction notification
    TXN_UPDATED        — transaction updated notification
    TXN_DELETED        — transaction deleted notification
    RPT_TXN_SCHEDULED  — scheduled report (shared by daily/weekly/biweekly/monthly;
                         the period is carried by {{period_display}})

Variable contract (the {{ ... }} tokens the sender will fill per recipient):
    transaction_id   — numeric id (txn templates)
    materials_table  — RAW server-generated HTML <table> (txn templates; NOT escaped)
    materials_text   — plain-text material list (txn templates, body_plain)
    period_display   — e.g. "Weekly - (26 May 2026 - 1 June 2026)" (report)
    filename         — attached PDF filename (report)
    user.name, org.name — available for personalisation (not used by default copy)

The seeded bodies reproduce the CURRENT hardcoded output verbatim (only the
dynamic bits are tokenised) so wiring the senders to these templates in Phase 4
is behaviour-preserving.

Idempotent: by default only inserts templates whose system_key is missing, so
re-runs never clobber admin edits. Use --reset to overwrite bodies back to the
seed defaults (handy when this file changes).

Usage (from v3/backend):
    .venv/bin/python migrations/seed_business_email_templates_066.py [--reset] [--dry-run]

Connects via the standard env vars (DB_HOST / DB_PORT / DB_NAME / DB_USER /
DB_PASSWORD) — same as the rest of the platform.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('migration_066_seed')


def _build_db_url() -> str:
    host = os.environ.get('DB_HOST', 'localhost')
    port = os.environ.get('DB_PORT', '5432')
    name = os.environ.get('DB_NAME', 'gepp_platform')
    user = os.environ.get('DB_USER', 'postgres')
    pwd = os.environ.get('DB_PASSWORD', '')
    auth = f'{user}:{pwd}' if pwd else user
    return f'postgresql+psycopg2://{auth}@{host}:{port}/{name}'


# ───────────────────────────────────────────────────────────────────────────
# Template bodies — copied verbatim from the hardcoded senders, with only the
# dynamic f-string pieces replaced by {{ tokens }}. Plain Python strings (NOT
# f-strings) so the double braces stay literal for the renderer.
# ───────────────────────────────────────────────────────────────────────────

_TXN_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f6f8; line-height: 1.6; color: #333;">
    <div style="max-width: 560px; margin: 0 auto; padding: 32px 24px;">
        <div style="background: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2c3e50 0%, __ACCENT__ 100%); padding: 28px 24px; text-align: center;">
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">__TITLE__</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">__LEAD__</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid __ACCENT__;">
                    __DETAIL_BLOCK__
                </div>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">__FOOTER_LINE__</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""

# Detail block WITH the "See details" button (CREATED / UPDATED)
_TXN_DETAIL_WITH_BUTTON = (
    '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse;"><tr>\n'
    '                        <td style="vertical-align: middle; padding-right: 16px;"><p style="margin: 0; font-size: 13px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction ID &nbsp;<strong style="font-size: 18px; color: #2c3e50; text-transform: none; letter-spacing: normal;">#{{transaction_id}}</strong></p></td>\n'
    '                        <td style="vertical-align: middle; text-align: right; white-space: nowrap;"><a href="https://geppdata.com/waste-transactions#{{transaction_id}}" style="display: inline-block; padding: 10px 24px; background: linear-gradient(135deg, __BTN__ 0%, __ACCENT__ 100%); color: #ffffff; font-size: 14px; font-weight: 600; text-decoration: none; border-radius: 8px; white-space: nowrap;">See details</a></td></tr></table>{{materials_table}}'
)

# Detail block WITHOUT a button (DELETED)
_TXN_DETAIL_NO_BUTTON = (
    '<p style="margin: 0; font-size: 13px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction ID &nbsp;<strong style="font-size: 18px; color: #2c3e50; text-transform: none; letter-spacing: normal;">#{{transaction_id}}</strong></p>{{materials_table}}'
)


def _txn_html(title: str, lead: str, footer: str, accent: str, btn: str, with_button: bool) -> str:
    detail = (
        _TXN_DETAIL_WITH_BUTTON.replace('__BTN__', btn).replace('__ACCENT__', accent)
        if with_button else _TXN_DETAIL_NO_BUTTON
    )
    return (
        _TXN_HTML
        .replace('__TITLE__', title)
        .replace('__LEAD__', lead)
        .replace('__FOOTER_LINE__', footer)
        .replace('__DETAIL_BLOCK__', detail)
        .replace('__ACCENT__', accent)
    )


def _txn_plain(title: str, lead: str, footer: str) -> str:
    return (
        f"{title} – GEPP Platform\n\n"
        "Hello,\n\n"
        f"{lead}\n\n"
        "Transaction ID: #{{transaction_id}}{{materials_text}}\n\n"
        + ("See details: https://geppdata.com/waste-transactions#{{transaction_id}}\n\n" if footer != _DELETED_FOOTER else "")
        + f"{footer}\n\n"
        "—\n"
        "This is an automated message from GEPP Platform. Please do not reply to this email."
    )


_CREATED_FOOTER = "Log in to the platform to view details and take action if needed."
_UPDATED_FOOTER = "Log in to the platform to view the latest details."
_DELETED_FOOTER = "Log in to the platform for more information."

_REPORT_HTML = """<!DOCTYPE html>
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
                    <p style="margin: 0; font-size: 16px; font-weight: 600; color: #2c3e50;">{{period_display}}</p>
                </div>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #6c757d;">The attachment <strong style="color: #333;">{{filename}}</strong> contains your full report.</p>
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

_REPORT_PLAIN = (
    "Scheduled Report – GEPP Platform\n\n"
    "Hello,\n\n"
    "Your scheduled report is ready. Please find the PDF attached to this email.\n\n"
    "{{period_display}}\n"
    "Attachment: {{filename}}\n\n"
    "If you have any questions, please contact your administrator.\n\n"
    "—\n"
    "This is an automated message from GEPP Platform. Please do not reply to this email."
)

_TXN_VARS = ["transaction_id", "materials_table", "materials_text", "user.name", "org.name"]
_REPORT_VARS = ["period_display", "filename", "user.name", "org.name"]

TEMPLATES = [
    {
        "system_key": "TXN_CREATED",
        "name": "Transaction created notification",
        "subject": "New transaction #{{transaction_id}} – GEPP Platform",
        "preview_text": "A new transaction has been created in your organization.",
        "icon": "plus-circle",
        "variables": _TXN_VARS,
        "body_html": _txn_html(
            "New Transaction",
            "A new transaction has been created in your organization.",
            _CREATED_FOOTER, accent="#27ae60", btn="#8fc9a3", with_button=True,
        ),
        "body_plain": _txn_plain("New Transaction",
                                 "A new transaction has been created in your organization.",
                                 _CREATED_FOOTER),
    },
    {
        "system_key": "TXN_UPDATED",
        "name": "Transaction updated notification",
        "subject": "Transaction #{{transaction_id}} updated – GEPP Platform",
        "preview_text": "A transaction in your organization has been updated.",
        "icon": "edit",
        "variables": _TXN_VARS,
        "body_html": _txn_html(
            "Transaction Updated",
            "A transaction in your organization has been updated.",
            _UPDATED_FOOTER, accent="#3498db", btn="#7ec4e8", with_button=True,
        ),
        "body_plain": _txn_plain("Transaction Updated",
                                 "A transaction in your organization has been updated.",
                                 _UPDATED_FOOTER),
    },
    {
        "system_key": "TXN_DELETED",
        "name": "Transaction deleted notification",
        "subject": "Transaction #{{transaction_id}} deleted – GEPP Platform",
        "preview_text": "A transaction in your organization has been deleted.",
        "icon": "delete",
        "variables": _TXN_VARS,
        "body_html": _txn_html(
            "Transaction Deleted",
            "A transaction in your organization has been deleted.",
            _DELETED_FOOTER, accent="#e67e22", btn="#e67e22", with_button=False,
        ),
        "body_plain": _txn_plain("Transaction Deleted",
                                 "A transaction in your organization has been deleted.",
                                 _DELETED_FOOTER),
    },
    {
        "system_key": "RPT_TXN_SCHEDULED",
        "name": "Scheduled transaction report",
        "subject": "Scheduled Report – {{period_display}}",
        "preview_text": "Your scheduled report is ready — PDF attached.",
        "icon": "file-text",
        "variables": _REPORT_VARS,
        "body_html": _REPORT_HTML,
        "body_plain": _REPORT_PLAIN,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset', action='store_true',
                        help='overwrite existing system templates back to seed defaults')
    parser.add_argument('--dry-run', action='store_true',
                        help='report actions without writing')
    args = parser.parse_args()

    db_url = _build_db_url()
    logger.info('Connecting to %s', db_url.split('@')[-1])
    engine = create_engine(db_url)
    session: Session = sessionmaker(bind=engine)()

    inserted, updated, skipped = 0, 0, 0
    try:
        for tpl in TEMPLATES:
            existing = session.execute(
                text("SELECT id FROM crm_email_templates "
                     "WHERE system_key = :sk AND is_system = TRUE AND deleted_date IS NULL "
                     "LIMIT 1"),
                {"sk": tpl["system_key"]},
            ).fetchone()

            if existing and not args.reset:
                logger.info("skip %-18s (exists, id=%s) — use --reset to overwrite",
                            tpl["system_key"], existing[0])
                skipped += 1
                continue

            params = {
                "name": tpl["name"],
                "subject": tpl["subject"],
                "preview_text": tpl["preview_text"],
                "body_html": tpl["body_html"],
                "body_plain": tpl["body_plain"],
                "variables": json.dumps(tpl["variables"]),
                "icon": tpl["icon"],
                "system_key": tpl["system_key"],
            }

            if existing:  # --reset path
                if args.dry_run:
                    logger.info("would RESET %s (id=%s)", tpl["system_key"], existing[0])
                else:
                    params["id"] = existing[0]
                    session.execute(text("""
                        UPDATE crm_email_templates SET
                            name = :name, subject = :subject, preview_text = :preview_text,
                            body_html = :body_html, body_plain = :body_plain,
                            variables = CAST(:variables AS jsonb), icon = :icon,
                            updated_date = NOW()
                        WHERE id = :id
                    """), params)
                updated += 1
            else:
                if args.dry_run:
                    logger.info("would INSERT %s", tpl["system_key"])
                else:
                    session.execute(text("""
                        INSERT INTO crm_email_templates (
                            organization_id, name, subject, preview_text,
                            body_html, body_plain, variables, generated_by,
                            version, is_active, is_system, category, icon,
                            system_key, created_date, updated_date
                        ) VALUES (
                            NULL, :name, :subject, :preview_text,
                            :body_html, :body_plain, CAST(:variables AS jsonb), 'human',
                            1, TRUE, TRUE, 'transactional', :icon,
                            :system_key, NOW(), NOW()
                        )
                    """), params)
                inserted += 1

        if args.dry_run:
            logger.info("DRY RUN — inserted=%d updated=%d skipped=%d", inserted, updated, skipped)
            return 0

        session.commit()
        logger.info("Done. inserted=%d updated=%d skipped=%d", inserted, updated, skipped)
        return 0
    except Exception:
        session.rollback()
        logger.exception("seed failed — rolled back")
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    raise SystemExit(main())
