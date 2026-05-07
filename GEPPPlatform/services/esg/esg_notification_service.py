"""
ESG Notification Service — Proactive monthly reminders via LINE Push Message
"""

import json
import logging
import os
from typing import List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.records import EsgRecord

logger = logging.getLogger(__name__)

LINE_PUSH_URL = 'https://api.line.me/v2/bot/message/push'


class EsgNotificationService:

    def __init__(self, db: Session):
        self.db = db

    def send_monthly_reminders(self) -> Dict[str, Any]:
        """
        Called by cron at month-end.
        Finds users who haven't submitted data this month and sends a push reminder.
        """
        now = datetime.utcnow()
        current_month = now.month
        current_year = now.year

        settings_list = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.is_active == True,
            EsgOrganizationSettings.line_channel_token.isnot(None),
        ).all()

        results = []
        for settings in settings_list:
            org_id = settings.organization_id
            channel_token = settings.line_channel_token

            # Get distinct LINE user IDs who have entries for this org
            user_ids = (
                self.db.query(EsgRecord.line_user_id)
                .filter(
                    EsgRecord.organization_id == org_id,
                    EsgRecord.line_user_id.isnot(None),
                    EsgRecord.is_active == True,
                )
                .distinct()
                .all()
            )

            for (line_user_id,) in user_ids:
                if not line_user_id:
                    continue

                # Check if user has submitted this month
                has_this_month = self.db.query(EsgRecord).filter(
                    EsgRecord.line_user_id == line_user_id,
                    EsgRecord.organization_id == org_id,
                    EsgRecord.is_active == True,
                ).filter(
                    EsgRecord.created_date >= datetime(current_year, current_month, 1),
                ).first()

                if not has_this_month:
                    self._send_push(channel_token, line_user_id, self._reminder_message())
                    results.append({'line_user_id': line_user_id, 'org_id': org_id, 'sent': True})

        return {
            'success': True,
            'reminders_sent': len(results),
            'details': results,
        }

    def _reminder_message(self) -> str:
        now = datetime.utcnow()
        month_name = now.strftime('%B %Y')
        return (
            f'GEPP ESG Reminder\n\n'
            f'สวัสดีครับ! อย่าลืมอัปเดตข้อมูล ESG ประจำเดือน {month_name} นะครับ\n\n'
            f'ส่งรูปบิลค่าไฟ/ค่าน้ำมัน หรือกรอกข้อมูลผ่าน LIFF ได้เลย'
        )

    def _send_push(self, channel_token: str, user_id: str, message: str):
        """Send a push message to a LINE user."""
        try:
            import urllib.request
            data = json.dumps({
                'to': user_id,
                'messages': [{'type': 'text', 'text': message}],
            }).encode('utf-8')
            req = urllib.request.Request(LINE_PUSH_URL, data=data, headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {channel_token}',
            })
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send push to {user_id}: {e}")
