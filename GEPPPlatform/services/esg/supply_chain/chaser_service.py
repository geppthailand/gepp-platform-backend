"""
Automated Chaser/Reminder Service
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

from GEPPPlatform.models.esg.supplier_chasers import EsgSupplierChaser
from GEPPPlatform.models.esg.suppliers import EsgSupplier

logger = logging.getLogger(__name__)


class ChaserService:
    """Schedule and trigger automated reminders for supplier data collection."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_chasers(self, org_id: int) -> List[Dict[str, Any]]:
        """Return all chaser configs for the organization."""
        chasers = (
            self.session.query(EsgSupplierChaser)
            .filter(
                EsgSupplierChaser.organization_id == org_id,
                EsgSupplierChaser.is_active == True,
            )
            .order_by(EsgSupplierChaser.scheduled_date.asc())
            .all()
        )
        return [c.to_dict() for c in chasers]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_chaser(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule a new chaser reminder."""
        chaser = EsgSupplierChaser(
            organization_id=data['organization_id'],
            supplier_id=data.get('supplier_id'),
            channel=data.get('channel', 'email'),
            scheduled_date=data.get('scheduled_date', date.today() + timedelta(days=7)),
            message_template=data.get('message_template'),
            frequency=data.get('frequency', 'once'),
            status='scheduled',
            reminder_count=0,
        )
        self.session.add(chaser)
        self.session.flush()
        return chaser.to_dict()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_chaser(
        self, chaser_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a chaser configuration."""
        chaser = self.session.query(EsgSupplierChaser).filter(
            EsgSupplierChaser.id == chaser_id,
            EsgSupplierChaser.is_active == True,
        ).first()
        if not chaser:
            return None

        updatable = [
            'channel', 'scheduled_date', 'message_template',
            'frequency', 'status', 'supplier_id',
        ]
        for field in updatable:
            if field in data:
                setattr(chaser, field, data[field])

        self.session.flush()
        return chaser.to_dict()

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    def delete_chaser(self, chaser_id: int, org_id: int) -> bool:
        """Soft-delete a chaser."""
        chaser = self.session.query(EsgSupplierChaser).filter(
            EsgSupplierChaser.id == chaser_id,
            EsgSupplierChaser.organization_id == org_id,
            EsgSupplierChaser.is_active == True,
        ).first()
        if not chaser:
            return False

        chaser.is_active = False
        self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Trigger due chasers
    # ------------------------------------------------------------------

    def trigger_due_chasers(
        self, org_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Find all chasers where scheduled_date <= today and status='scheduled'.
        For each: send reminder, update status and sent_at, increment reminder_count.
        """
        today = date.today()

        query = self.session.query(EsgSupplierChaser).filter(
            EsgSupplierChaser.scheduled_date <= today,
            EsgSupplierChaser.status == 'scheduled',
            EsgSupplierChaser.is_active == True,
        )
        if org_id:
            query = query.filter(EsgSupplierChaser.organization_id == org_id)

        due_chasers = query.all()
        sent = 0
        failed = 0

        for chaser in due_chasers:
            try:
                supplier = None
                if chaser.supplier_id:
                    supplier = self.session.query(EsgSupplier).filter(
                        EsgSupplier.id == chaser.supplier_id,
                    ).first()

                if chaser.channel == 'email':
                    self._send_email_reminder(supplier, chaser)
                elif chaser.channel == 'line':
                    self._send_line_reminder(supplier, chaser)

                chaser.status = 'sent'
                chaser.sent_at = datetime.now(timezone.utc)
                chaser.reminder_count = (chaser.reminder_count or 0) + 1

                # Reschedule if recurring
                if chaser.frequency == 'weekly':
                    self._reschedule(chaser, timedelta(weeks=1))
                elif chaser.frequency == 'monthly':
                    self._reschedule(chaser, timedelta(days=30))
                elif chaser.frequency == 'quarterly':
                    self._reschedule(chaser, timedelta(days=90))

                sent += 1
            except Exception as e:
                logger.error(f"Failed to send chaser {chaser.id}: {e}", exc_info=True)
                chaser.status = 'failed'
                failed += 1

        self.session.flush()
        return {'sent': sent, 'failed': failed, 'total': len(due_chasers)}

    # ------------------------------------------------------------------
    # Reminder sending (placeholders)
    # ------------------------------------------------------------------

    def _send_email_reminder(self, supplier, chaser):
        """Placeholder for email sending via Lambda/SES."""
        logger.info(
            f"[EMAIL] Chaser {chaser.id} -> supplier {chaser.supplier_id}: "
            f"{chaser.message_template or 'Please submit your ESG data.'}"
        )

    def _send_line_reminder(self, supplier, chaser):
        """Placeholder for LINE push message."""
        logger.info(
            f"[LINE] Chaser {chaser.id} -> supplier {chaser.supplier_id}: "
            f"{chaser.message_template or 'Please submit your ESG data.'}"
        )

    # ------------------------------------------------------------------
    # Reschedule helper
    # ------------------------------------------------------------------

    def _reschedule(self, chaser, delta: timedelta):
        """Create a new scheduled chaser for the next occurrence."""
        next_chaser = EsgSupplierChaser(
            organization_id=chaser.organization_id,
            supplier_id=chaser.supplier_id,
            channel=chaser.channel,
            scheduled_date=chaser.scheduled_date + delta,
            message_template=chaser.message_template,
            frequency=chaser.frequency,
            status='scheduled',
            reminder_count=0,
        )
        self.session.add(next_chaser)
