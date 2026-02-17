"""
Transaction Service - Business logic for transaction management
Handles CRUD operations, validation, and transaction record linking
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import cast, String, exists, and_
import json
import logging
import os
from datetime import datetime
from decimal import Decimal

import boto3

from sqlalchemy import cast, String, text
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError

from ....models.transactions.transactions import Transaction, TransactionStatus, TransactionRecordStatus

from ....models.transactions.transaction_records import TransactionRecord
from ...file_upload_service import S3FileUploadService
from ....models.users.user_location import UserLocation
from ....models.users.user_related import UserLocationTag, UserTenant
from ....models.subscriptions.organizations import Organization, OrganizationSetup

logger = logging.getLogger(__name__)

# Two decimal places for all weight, quantity, and amount values
TWO_PLACES = Decimal('0.01')


def _round_decimal(value) -> Decimal:
    """Round a numeric value to 2 decimal places as Decimal."""
    if value is None:
        return Decimal('0')
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(TWO_PLACES)


def _round_float(value) -> float:
    """Round a numeric value to 2 decimal places as float (for API output)."""
    if value is None:
        return 0.0
    return round(float(value), 2)


class TransactionService:
    """
    High-level transaction management service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== TRANSACTION CRUD OPERATIONS ==========

    def create_transaction(
        self,
        transaction_data: Dict[str, Any],
        transaction_records_data: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new transaction with optional transaction records

        Args:
            transaction_data: Dict containing transaction information
            transaction_records_data: List of dicts containing transaction record data

        Returns:
            Dict with success status and transaction data
        """
        try:
            # Validate transaction data
            validation_errors = self._validate_transaction_data(transaction_data)
            if validation_errors:
                return {
                    'success': False,
                    'message': 'Transaction validation failed',
                    'errors': validation_errors
                }

            # Create transaction (tag_id / tenant_id from request map to location_tag_id / tenant_id)
            location_tag_id = transaction_data.get('tag_id') or transaction_data.get('location_tag_id')
            tenant_id = transaction_data.get('tenant_id')

            transaction = Transaction(
                transaction_method=transaction_data.get('transaction_method', 'origin'),
                status=TransactionStatus(transaction_data.get('status', 'pending')),
                organization_id=transaction_data.get('organization_id'),
                origin_id=transaction_data.get('origin_id'),
                destination_ids=[],  # Will be populated from transaction records
                location_tag_id=location_tag_id,
                tenant_id=tenant_id,
                transaction_date=transaction_data.get('transaction_date', datetime.now()),
                arrival_date=transaction_data.get('arrival_date'),
                origin_coordinates=transaction_data.get('origin_coordinates'),
                destination_coordinates=transaction_data.get('destination_coordinates'),
                notes=transaction_data.get('notes'),
                images=transaction_data.get('images', []),
                vehicle_info=transaction_data.get('vehicle_info'),
                driver_info=transaction_data.get('driver_info'),
                hazardous_level=transaction_data.get('hazardous_level', 0),
                treatment_method=transaction_data.get('treatment_method'),
                disposal_method=transaction_data.get('disposal_method'),
                created_by_id=transaction_data.get('created_by_id'),
                weight_kg=Decimal('0'),  # Will be calculated from transaction records
                total_amount=Decimal('0')  # Will be calculated from transaction records
            )

            self.db.add(transaction)
            self.db.flush()  # Get transaction ID

            # Create transaction records if provided
            transaction_record_ids = []
            destination_ids = []
            if transaction_records_data:
                for record_data in transaction_records_data:
                    record_result = self._create_transaction_record(
                        record_data,
                        transaction.id
                    )
                    if record_result['success']:
                        transaction_record_ids.append(record_result['transaction_record'].id)
                        # Collect destination_id from each record (in same order as records)
                        destination_ids.append(record_data.get('destination_id'))
                    else:
                        # Rollback transaction if any record fails
                        self.db.rollback()
                        return {
                            'success': False,
                            'message': f'Failed to create transaction record: {record_result["message"]}',
                            'errors': record_result.get('errors', [])
                        }

            # Update transaction with record IDs, destination_ids, and calculated totals
            transaction.transaction_records = transaction_record_ids
            transaction.destination_ids = destination_ids
            self._calculate_transaction_totals(transaction)

            # Handle file uploads if provided
            if transaction_data.get('file_uploads') and transaction.id:
                try:
                    # Upload directly to S3 and store URLs in JSONB field
                    s3_service = S3FileUploadService()
                    uploaded_files = s3_service.upload_transaction_files(
                        files=transaction_data['file_uploads'],
                        transaction_record_id=transaction.id,
                        upload_type='transaction'
                    )

                    if uploaded_files:
                        # Extract S3 URLs and store in JSONB field
                        image_urls = [file_info['s3_url'] for file_info in uploaded_files]
                        transaction.images = image_urls

                        logger.info(f"Successfully uploaded {len(image_urls)} images for transaction {transaction.id}")
                    else:
                        logger.warning(f"No files were uploaded for transaction {transaction.id}")

                except Exception as e:
                    logger.error(f"Error handling file uploads for transaction {transaction.id}: {str(e)}")
                    # Continue without failing the transaction creation

            self.db.commit()

            return {
                'success': True,
                'message': 'Transaction created successfully',
                'transaction': self._transaction_to_dict(transaction),
                'transaction_records_count': len(transaction_record_ids)
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error creating transaction: {str(e)}")
            return {
                'success': False,
                'message': 'Database error occurred',
                'errors': [str(e)]
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Unexpected error creating transaction: {str(e)}")
            return {
                'success': False,
                'message': 'An unexpected error occurred',
                'errors': [str(e)]
            }

    def _send_email_via_lambda(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send email via Lambda (same contract as auth_handlers)."""
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
            lambda_client = boto3.client("lambda")
            response = lambda_client.invoke(
                FunctionName=lambda_function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps({"data": {"message": message}}).encode("utf-8"),
            )
            response_payload = response.get("Payload").read()
            response_data = json.loads(response_payload)
            if response.get("FunctionError"):
                logger.warning("Email Lambda function error: %s", response.get("FunctionError"))
                return False
            if isinstance(response_data, dict) and "body" in response_data:
                body_data = json.loads(response_data.get("body", "{}"))
                if body_data.get("data", {}).get("status") == "success":
                    return True
            return False
        except Exception as e:
            logger.exception("Error sending email via Lambda: %s", e)
            return False

    def _send_txn_created_emails(
        self,
        transaction_id: int,
        organization_id: int,
        email_list: List[str],
        resource: Dict[str, Any],
    ) -> None:
        """
        Send TXN_CREATED notification emails to the given addresses via Lambda.
        """
        if not email_list:
            return
        subject = f"New transaction #{transaction_id} – GEPP Platform"
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
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">New Transaction</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">A new transaction has been created in your organization.</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid #27ae60;">
                    <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction ID</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #2c3e50;">#{transaction_id}</p>
                </div>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">Log in to the platform to view details and take action if needed.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        text_content = f"""New Transaction – GEPP Platform

Hello,

A new transaction has been created in your organization.

Transaction ID: #{transaction_id}

Log in to the platform to view details and take action if needed.

—
This is an automated message from GEPP Platform. Please do not reply to this email."""
        for to_email in email_list:
            try:
                sent = self._send_email_via_lambda(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )
                logger.info(
                    "TXN_CREATED email to %s for transaction_id=%s: sent=%s",
                    to_email,
                    transaction_id,
                    sent,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send TXN_CREATED email to %s for transaction_id=%s: %s",
                    to_email,
                    transaction_id,
                    e,
                )

    def _send_txn_updated_emails(
        self,
        transaction_id: int,
        organization_id: int,
        email_list: List[str],
        resource: Dict[str, Any],
    ) -> None:
        """
        Send TXN_UPDATED notification emails to the given addresses via Lambda.
        """
        if not email_list:
            return
        subject = f"Transaction #{transaction_id} updated – GEPP Platform"
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f6f8; line-height: 1.6; color: #333;">
    <div style="max-width: 560px; margin: 0 auto; padding: 32px 24px;">
        <div style="background: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); padding: 28px 24px; text-align: center;">
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">Transaction Updated</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">A transaction in your organization has been updated.</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid #3498db;">
                    <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction ID</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #2c3e50;">#{transaction_id}</p>
                </div>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">Log in to the platform to view the latest details.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        text_content = f"""Transaction Updated – GEPP Platform

Hello,

A transaction in your organization has been updated.

Transaction ID: #{transaction_id}

Log in to the platform to view the latest details.

—
This is an automated message from GEPP Platform. Please do not reply to this email."""
        for to_email in email_list:
            try:
                sent = self._send_email_via_lambda(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )
                logger.info(
                    "TXN_UPDATED email to %s for transaction_id=%s: sent=%s",
                    to_email,
                    transaction_id,
                    sent,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send TXN_UPDATED email to %s for transaction_id=%s: %s",
                    to_email,
                    transaction_id,
                    e,
                )

    def create_txn_created_notifications(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """
        Create one notification (notification_type='TXN_CREATED'), user_notifications for users
        whose roles have BELL (channels_mask 2 or 3), and collect emails for users whose roles
        have EMAIL (channels_mask 1 or 3) then call _send_txn_created_emails (stub).
        """
        try:
            resource_dict = {'transaction_id': transaction_id}
            resource_json = json.dumps(resource_dict)

            # BELL: roles with channels_mask 2 or 3
            r_bell = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = 'TXN_CREATED'
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 2) != 0
                """),
                {'org_id': organization_id},
            )
            bell_role_ids = [row[0] for row in r_bell.fetchall()]

            if bell_role_ids:
                ins = self.db.execute(
                    text("""
                        INSERT INTO notifications
                            (created_by_id, resource, notification_type, is_active, created_date, updated_date)
                        VALUES (:created_by_id, CAST(:resource AS jsonb), :notification_type, TRUE, NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        'created_by_id': created_by_id,
                        'resource': resource_json,
                        'notification_type': 'TXN_CREATED',
                    },
                )
                row = ins.fetchone()
                if row:
                    notif_id = row[0]
                    users_bell = self.db.execute(
                        text("""
                            SELECT DISTINCT id FROM user_locations
                            WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                              AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                        """),
                        {'org_id': organization_id, 'role_ids': bell_role_ids},
                    )
                    user_rows = users_bell.fetchall()
                    for u in user_rows:
                        self.db.execute(
                            text("""
                                INSERT INTO user_notifications
                                    (user_id, notification_id, is_read, is_active, created_date, updated_date)
                                VALUES (:user_id, :notification_id, FALSE, TRUE, NOW(), NOW())
                                ON CONFLICT (user_id, notification_id) DO NOTHING
                            """),
                            {'user_id': u[0], 'notification_id': notif_id},
                        )

            # EMAIL: roles with channels_mask 1 or 3; collect user emails
            r_email = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = 'TXN_CREATED'
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 1) != 0
                """),
                {'org_id': organization_id},
            )
            email_role_ids = [row[0] for row in r_email.fetchall()]
            email_list: List[str] = []
            if email_role_ids:
                users_email = self.db.execute(
                    text("""
                        SELECT DISTINCT id, email FROM user_locations
                        WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                          AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                          AND email IS NOT NULL AND TRIM(email) != ''
                    """),
                    {'org_id': organization_id, 'role_ids': email_role_ids},
                )
                seen: set = set()
                for u in users_email.fetchall():
                    em = (u[1] or '').strip()
                    if em and em not in seen:
                        seen.add(em)
                        email_list.append(em)

            self._send_txn_created_emails(
                transaction_id=transaction_id,
                organization_id=organization_id,
                email_list=email_list,
                resource=resource_dict,
            )
            self.db.flush()
        except Exception as e:
            logger.error(
                "Error creating TXN_CREATED notifications for transaction_id=%s: %s",
                transaction_id,
                str(e),
                exc_info=True,
            )

    def create_txn_updated_notifications(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """
        Create one notification (notification_type='TXN_UPDATED'), user_notifications for users
        whose roles have BELL (channels_mask 2 or 3), and collect emails for users whose roles
        have EMAIL (channels_mask 1 or 3) then call _send_txn_updated_emails (stub).
        """
        try:
            resource_dict = {'transaction_id': transaction_id}
            resource_json = json.dumps(resource_dict)

            r_bell = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = 'TXN_UPDATED'
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 2) != 0
                """),
                {'org_id': organization_id},
            )
            bell_role_ids = [row[0] for row in r_bell.fetchall()]

            if bell_role_ids:
                ins = self.db.execute(
                    text("""
                        INSERT INTO notifications
                            (created_by_id, resource, notification_type, is_active, created_date, updated_date)
                        VALUES (:created_by_id, CAST(:resource AS jsonb), :notification_type, TRUE, NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        'created_by_id': created_by_id,
                        'resource': resource_json,
                        'notification_type': 'TXN_UPDATED',
                    },
                )
                row = ins.fetchone()
                if row:
                    notif_id = row[0]
                    users_bell = self.db.execute(
                        text("""
                            SELECT DISTINCT id FROM user_locations
                            WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                              AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                        """),
                        {'org_id': organization_id, 'role_ids': bell_role_ids},
                    )
                    for u in users_bell.fetchall():
                        self.db.execute(
                            text("""
                                INSERT INTO user_notifications
                                    (user_id, notification_id, is_read, is_active, created_date, updated_date)
                                VALUES (:user_id, :notification_id, FALSE, TRUE, NOW(), NOW())
                                ON CONFLICT (user_id, notification_id) DO NOTHING
                            """),
                            {'user_id': u[0], 'notification_id': notif_id},
                        )

            r_email = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = 'TXN_UPDATED'
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 1) != 0
                """),
                {'org_id': organization_id},
            )
            email_role_ids = [row[0] for row in r_email.fetchall()]
            email_list: List[str] = []
            if email_role_ids:
                users_email = self.db.execute(
                    text("""
                        SELECT DISTINCT id, email FROM user_locations
                        WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                          AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                          AND email IS NOT NULL AND TRIM(email) != ''
                    """),
                    {'org_id': organization_id, 'role_ids': email_role_ids},
                )
                seen: set = set()
                for u in users_email.fetchall():
                    em = (u[1] or '').strip()
                    if em and em not in seen:
                        seen.add(em)
                        email_list.append(em)

            self._send_txn_updated_emails(
                transaction_id=transaction_id,
                organization_id=organization_id,
                email_list=email_list,
                resource=resource_dict,
            )
            self.db.flush()
        except Exception as e:
            logger.error(
                "Error creating TXN_UPDATED notifications for transaction_id=%s: %s",
                transaction_id,
                str(e),
                exc_info=True,
            )

    def _send_txn_approved_emails(
        self,
        transaction_id: int,
        organization_id: int,
        email_list: List[str],
        resource: Dict[str, Any],
    ) -> None:
        """Send TXN_APPROVED notification emails to the given addresses via Lambda."""
        if not email_list:
            return
        txn_ref = f"#{transaction_id}"
        subject = f"Transaction {txn_ref} has been approved – GEPP Platform"
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
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">Transaction Approved</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">Transaction {txn_ref} has been approved.</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid #27ae60;">
                    <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #2c3e50;">{txn_ref}</p>
                </div>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">Log in to the platform to view details.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        text_content = f"""Transaction Approved – GEPP Platform

Hello,

Transaction {txn_ref} has been approved.

Log in to the platform to view details.

—
This is an automated message from GEPP Platform. Please do not reply to this email."""
        for to_email in email_list:
            try:
                sent = self._send_email_via_lambda(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )
                logger.info(
                    "TXN_APPROVED email to %s for transaction_id=%s: sent=%s",
                    to_email,
                    transaction_id,
                    sent,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send TXN_APPROVED email to %s for transaction_id=%s: %s",
                    to_email,
                    transaction_id,
                    e,
                )

    def _send_txn_rejected_emails(
        self,
        transaction_id: int,
        organization_id: int,
        email_list: List[str],
        resource: Dict[str, Any],
    ) -> None:
        """Send TXN_REJECTED notification emails to the given addresses via Lambda."""
        if not email_list:
            return
        txn_ref = f"#{transaction_id}"
        subject = f"Transaction {txn_ref} has been rejected – GEPP Platform"
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f6f8; line-height: 1.6; color: #333;">
    <div style="max-width: 560px; margin: 0 auto; padding: 32px 24px;">
        <div style="background: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2c3e50 0%, #e74c3c 100%); padding: 28px 24px; text-align: center;">
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 600; letter-spacing: -0.02em;">Transaction Rejected</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">GEPP Platform</p>
            </div>
            <div style="padding: 28px 24px;">
                <p style="margin: 0 0 16px 0; font-size: 15px;">Hello,</p>
                <p style="margin: 0 0 20px 0; font-size: 15px;">Transaction {txn_ref} has been rejected because one or all of its records have been rejected. Please check the platform.</p>
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 24px 0; border-left: 4px solid #e74c3c;">
                    <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Transaction</p>
                    <p style="margin: 0; font-size: 18px; font-weight: 600; color: #2c3e50;">{txn_ref}</p>
                </div>
                <p style="margin: 0; font-size: 14px; color: #6c757d;">Log in to the platform to view details and take action if needed.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 0;">
            <div style="padding: 16px 24px;">
                <p style="margin: 0; font-size: 12px; color: #95a5a6;">This is an automated message from GEPP Platform. Please do not reply to this email.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        text_content = f"""Transaction Rejected – GEPP Platform

Hello,

Transaction {txn_ref} has been rejected because one or all of its records have been rejected. Please check the platform.

Log in to the platform to view details and take action if needed.

—
This is an automated message from GEPP Platform. Please do not reply to this email."""
        for to_email in email_list:
            try:
                sent = self._send_email_via_lambda(
                    to_email=to_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )
                logger.info(
                    "TXN_REJECTED email to %s for transaction_id=%s: sent=%s",
                    to_email,
                    transaction_id,
                    sent,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send TXN_REJECTED email to %s for transaction_id=%s: %s",
                    to_email,
                    transaction_id,
                    e,
                )

    def _create_txn_event_notifications(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
        event: str,
        send_email_fn: Any,
        resource_override: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Shared logic: create one notification for event, user_notifications (BELL),
        collect emails (EMAIL), call send_email_fn. Used for TXN_APPROVED, TXN_REJECTED.
        resource_override: if set, use as notification resource (e.g. {'transaction': {'id': txn_id, 'record_id': record_id}}).
        """
        try:
            resource_dict = resource_override if resource_override is not None else {'transaction_id': transaction_id}
            resource_json = json.dumps(resource_dict)

            r_bell = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = :event
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 2) != 0
                """),
                {'org_id': organization_id, 'event': event},
            )
            bell_role_ids = [row[0] for row in r_bell.fetchall()]

            if bell_role_ids:
                ins = self.db.execute(
                    text("""
                        INSERT INTO notifications
                            (created_by_id, resource, notification_type, is_active, created_date, updated_date)
                        VALUES (:created_by_id, CAST(:resource AS jsonb), :notification_type, TRUE, NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        'created_by_id': created_by_id,
                        'resource': resource_json,
                        'notification_type': event,
                    },
                )
                row = ins.fetchone()
                if row:
                    notif_id = row[0]
                    users_bell = self.db.execute(
                        text("""
                            SELECT DISTINCT id FROM user_locations
                            WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                              AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                        """),
                        {'org_id': organization_id, 'role_ids': bell_role_ids},
                    )
                    for u in users_bell.fetchall():
                        self.db.execute(
                            text("""
                                INSERT INTO user_notifications
                                    (user_id, notification_id, is_read, is_active, created_date, updated_date)
                                VALUES (:user_id, :notification_id, FALSE, TRUE, NOW(), NOW())
                                ON CONFLICT (user_id, notification_id) DO NOTHING
                            """),
                            {'user_id': u[0], 'notification_id': notif_id},
                        )

            r_email = self.db.execute(
                text("""
                    SELECT role_id FROM organization_notification_settings
                    WHERE organization_id = :org_id AND event = :event
                      AND is_active = TRUE AND deleted_date IS NULL
                      AND (channels_mask & 1) != 0
                """),
                {'org_id': organization_id, 'event': event},
            )
            email_role_ids = [row[0] for row in r_email.fetchall()]
            email_list: List[str] = []
            if email_role_ids:
                users_email = self.db.execute(
                    text("""
                        SELECT DISTINCT id, email FROM user_locations
                        WHERE organization_id = :org_id AND organization_role_id = ANY(:role_ids)
                          AND is_user = TRUE AND is_active = TRUE AND deleted_date IS NULL
                          AND email IS NOT NULL AND TRIM(email) != ''
                    """),
                    {'org_id': organization_id, 'role_ids': email_role_ids},
                )
                seen: set = set()
                for u in users_email.fetchall():
                    em = (u[1] or '').strip()
                    if em and em not in seen:
                        seen.add(em)
                        email_list.append(em)

            send_email_fn(
                transaction_id=transaction_id,
                organization_id=organization_id,
                email_list=email_list,
                resource=resource_dict,
            )
            self.db.flush()
        except Exception as e:
            logger.error(
                "Error creating %s notifications for transaction_id=%s: %s",
                event,
                transaction_id,
                str(e),
                exc_info=True,
            )

    def _transaction_has_all_records_approved(self, transaction_id: int) -> bool:
        """Return True if the transaction has at least one record and all records are approved."""
        count = self.db.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == transaction_id,
        ).count()
        if count == 0:
            return False
        not_approved = self.db.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == transaction_id,
            TransactionRecord.status != 'approved',
        ).count()
        return not_approved == 0

    def create_txn_approved_notifications(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """Create notifications and email list for TXN_APPROVED (BELL + EMAIL)."""
        self._create_txn_event_notifications(
            transaction_id=transaction_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
            event='TXN_APPROVED',
            send_email_fn=self._send_txn_approved_emails,
        )

    def create_txn_approved_notifications_if_all_records_approved(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """Create TXN_APPROVED notifications and emails only when all records in the transaction are approved."""
        if not self._transaction_has_all_records_approved(transaction_id):
            return
        self.create_txn_approved_notifications(
            transaction_id=transaction_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
        )

    def create_txn_rejected_notifications(
        self,
        transaction_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """Create notifications and email list for TXN_REJECTED (BELL + EMAIL stub)."""
        self._create_txn_event_notifications(
            transaction_id=transaction_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
            event='TXN_REJECTED',
            send_email_fn=self._send_txn_rejected_emails,
        )

    def create_txn_approved_notifications_for_record(
        self,
        transaction_id: int,
        record_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """Create TXN_APPROVED notifications for a record approve; resource = { transaction: { id, record_id } }."""
        self._create_txn_event_notifications(
            transaction_id=transaction_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
            event='TXN_APPROVED',
            send_email_fn=self._send_txn_approved_emails,
            resource_override={'transaction': {'id': transaction_id, 'record_id': record_id}},
        )

    def create_txn_rejected_notifications_for_record(
        self,
        transaction_id: int,
        record_id: int,
        organization_id: int,
        created_by_id: int,
    ) -> None:
        """Create TXN_REJECTED notifications for a record reject; resource = { transaction: { id, record_id } }."""
        self._create_txn_event_notifications(
            transaction_id=transaction_id,
            organization_id=organization_id,
            created_by_id=created_by_id,
            event='TXN_REJECTED',
            send_email_fn=self._send_txn_rejected_emails,
            resource_override={'transaction': {'id': transaction_id, 'record_id': record_id}},
        )

    def get_transaction(self, transaction_id: int, include_records: bool = False) -> Dict[str, Any]:
        """
        Retrieve a transaction by ID

        Args:
            transaction_id: The transaction ID to retrieve
            include_records: Whether to include transaction records

        Returns:
            Dict with success status and transaction data
        """
        try:
            # Eager load location relationships (destination_ids is an array, no relationship)
            transaction = self.db.query(Transaction).options(
                joinedload(Transaction.origin),
                joinedload(Transaction.created_by)
            ).filter(
                Transaction.id == transaction_id,
                Transaction.is_active == True
            ).first()

            if not transaction:
                return {
                    'success': False,
                    'message': 'Transaction not found',
                    'errors': ['Transaction does not exist or has been deleted']
                }

            transaction_dict = self._transaction_to_dict(transaction)

            # Enrich with location_tag and tenant (id, name) only; do not expose raw IDs
            location_tag_id = transaction_dict.pop('location_tag_id', None)
            transaction_dict.pop('tag_id', None)  # alias, remove
            tenant_id = transaction_dict.pop('tenant_id', None)
            if location_tag_id:
                tag = self.db.query(UserLocationTag).filter(
                    UserLocationTag.id == location_tag_id,
                    UserLocationTag.is_active == True,
                    UserLocationTag.deleted_date.is_(None)
                ).first()
                if tag:
                    transaction_dict['location_tag'] = {'id': tag.id, 'name': tag.name or f"Tag {tag.id}"}
                else:
                    transaction_dict['location_tag'] = {'id': location_tag_id, 'name': None}
            else:
                transaction_dict['location_tag'] = None
            if tenant_id:
                tenant = self.db.query(UserTenant).filter(
                    UserTenant.id == tenant_id,
                    UserTenant.is_active == True,
                    UserTenant.deleted_date.is_(None)
                ).first()
                if tenant:
                    transaction_dict['tenant'] = {'id': tenant.id, 'name': tenant.name or f"Tenant {tenant.id}"}
                else:
                    transaction_dict['tenant'] = {'id': tenant_id, 'name': None}
            else:
                transaction_dict['tenant'] = None

            if include_records:
                # Get transaction records with eager loading of material, category, and destination
                records = self.db.query(TransactionRecord).options(
                    joinedload(TransactionRecord.material),
                    joinedload(TransactionRecord.category),
                    joinedload(TransactionRecord.destination)
                ).filter(
                    TransactionRecord.created_transaction_id == transaction_id,
                    TransactionRecord.deleted_date.is_(None)
                ).all()

                transaction_dict['records'] = [
                    self._transaction_record_to_dict(record) for record in records
                ]

            return {
                'success': True,
                'transaction': transaction_dict
            }

        except Exception as e:
            logger.error(f"Error retrieving transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Error retrieving transaction',
                'errors': [str(e)]
            }

    def list_transactions(
        self,
        organization_id: Optional[int] = None,
        status: Optional[str] = None,
        origin_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        include_records: bool = False,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        district: Optional[int] = None,
        sub_district: Optional[int] = None,
        location_tag_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
        material_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        List transactions with filtering and pagination

        Transactions are ordered by ID in descending order (newest first)

        Args:
            organization_id: Filter by organization
            status: Filter by transaction status
            origin_id: Filter by origin location
            destination_id: Filter by destination location
            page: Page number
            page_size: Number of items per page
            include_records: Include transaction records in response
            search: Search text to filter transactions
            date_from: Filter transactions from this date (YYYY-MM-DD)
            date_to: Filter transactions to this date (YYYY-MM-DD)
            district: Filter by district (user_location level 3)
            sub_district: Filter by sub-district (user_location level 4)
            location_tag_id: Filter by location tag (when using composite origin filter)
            tenant_id: Filter by tenant (when using composite origin filter)
            material_id: Filter by material (transactions that have at least one record with this material_id)

        Returns:
            Dict with success status, transactions list, and pagination info
        """
        try:
            # Ensure database session is valid
            if not self.db:
                logger.error("Database session is None")
                return {
                    'success': False,
                    'message': 'Database session not available',
                    'errors': ['Database connection error']
                }

            # Test basic query first
            logger.info(f"Starting transaction query with org_id={organization_id}, status={status}")
            query = self.db.query(Transaction).options(
                joinedload(Transaction.origin),
                joinedload(Transaction.created_by)
            ).filter(Transaction.deleted_date.is_(None))

            # Apply filters
            if organization_id:
                query = query.filter(Transaction.organization_id == organization_id)
            if status:
                query = query.filter(Transaction.status == status)
            if origin_id:
                query = query.filter(Transaction.origin_id == origin_id)
            if location_tag_id is not None:
                query = query.filter(Transaction.location_tag_id == location_tag_id)
            if tenant_id is not None:
                query = query.filter(Transaction.tenant_id == tenant_id)
            if destination_id:
                # Filter by destination_id in the destination_ids array
                query = query.filter(Transaction.destination_ids.any(destination_id))

            # Material filter - transactions that have at least one record with this material_id
            if material_id is not None:
                query = query.filter(
                    exists().where(
                        and_(
                            TransactionRecord.created_transaction_id == Transaction.id,
                            TransactionRecord.is_active == True,
                            TransactionRecord.material_id == material_id
                        )
                    )
                )

            # Search filter - search in notes and transaction ID
            if search:
                search_pattern = f'%{search}%'
                query = query.filter(
                    (Transaction.notes.ilike(search_pattern)) |
                    (cast(Transaction.id, String).ilike(search_pattern))
                )

            # Date range filters
            if date_from:
                from datetime import datetime
                date_from_obj = datetime.fromisoformat(date_from)
                query = query.filter(Transaction.transaction_date >= date_from_obj)
            if date_to:
                from datetime import datetime
                date_to_obj = datetime.fromisoformat(date_to)
                query = query.filter(Transaction.transaction_date <= date_to_obj)

            # District/Sub-district filters (filter by origin_id)
            if district or sub_district:
                if sub_district:
                    # Filter by specific subdistrict
                    query = query.filter(Transaction.origin_id == sub_district)
                else:
                    # Filter by all subdistricts under the district
                    # Get organization_setup to extract subdistricts from root_nodes
                    org_setup = self.db.query(OrganizationSetup).filter(
                        OrganizationSetup.organization_id == organization_id
                    ).first()

                    if org_setup and org_setup.root_nodes:
                        # Extract all level 4 (subdistrict) IDs that are children of the selected district (level 3)
                        subdistrict_ids = []

                        def extract_subdistricts(nodes, current_level=1, parent_district_id=None):
                            """Recursively extract subdistrict IDs from district node"""
                            for node in nodes if isinstance(nodes, list) else []:
                                node_id = node.get('nodeId')
                                children = node.get('children', [])

                                if current_level == 3 and node_id == district:
                                    # Found the district, extract all its children (subdistricts)
                                    if children:
                                        for child in children if isinstance(children, list) else []:
                                            child_id = child.get('nodeId')
                                            if child_id:
                                                subdistrict_ids.append(child_id)
                                    return True
                                elif children:
                                    # Continue searching deeper
                                    if extract_subdistricts(children, current_level + 1, node_id):
                                        return True
                            return False

                        extract_subdistricts(org_setup.root_nodes)

                        if subdistrict_ids:
                            # Filter by all subdistricts in the district
                            query = query.filter(Transaction.origin_id.in_(subdistrict_ids))
                        else:
                            # No subdistricts found, filter by district itself
                            query = query.filter(Transaction.origin_id == district)
                    else:
                        # No organization setup, just filter by district
                        query = query.filter(Transaction.origin_id == district)

            # Get total count
            logger.info("Getting total count...")
            total_count = query.count()
            logger.info(f"Total count: {total_count}")

            # Apply pagination
            offset = (page - 1) * page_size
            logger.info(f"Applying pagination: offset={offset}, limit={page_size}")
            transactions = query.order_by(Transaction.id.desc())\
                              .offset(offset)\
                              .limit(page_size)\
                              .all()
            logger.info(f"Retrieved {len(transactions)} transactions")

            # Convert to dict format
            logger.info("Converting transactions to dict format...")
            transactions_list = []
            for i, transaction in enumerate(transactions):
                try:
                    logger.info(f"Processing transaction {i+1}/{len(transactions)}: ID={transaction.id}")
                    transaction_dict = self._transaction_to_dict(transaction)

                    if include_records:
                        logger.info(f"Including records for transaction {transaction.id}")
                        # Get transaction records with eager loading of destination
                        records = self.db.query(TransactionRecord).options(
                            joinedload(TransactionRecord.material),
                            joinedload(TransactionRecord.category),
                            joinedload(TransactionRecord.destination)
                        ).filter(
                            TransactionRecord.created_transaction_id == transaction.id,
                            TransactionRecord.deleted_date.is_(None)
                        ).all()
                        logger.info(f"Found {len(records)} records for transaction {transaction.id}")

                        transaction_dict['records'] = [
                            self._transaction_record_to_dict(record) for record in records
                        ]

                    transactions_list.append(transaction_dict)
                except Exception as e:
                    logger.error(f"Error processing transaction {transaction.id}: {str(e)}")
                    # Continue with other transactions instead of failing completely
                    continue

            logger.info(f"Successfully processed {len(transactions_list)} transactions")

            return {
                'success': True,
                'transactions': transactions_list,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total_count,
                    'pages': (total_count + page_size - 1) // page_size,
                    'has_next': page * page_size < total_count,
                    'has_prev': page > 1
                }
            }

        except Exception as e:
            logger.error(f"Error listing transactions: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'message': f'Error retrieving transactions: {str(e)}',
                'errors': [str(e)]
            }

    def update_transaction(
        self,
        transaction_id: int,
        update_data: Dict[str, Any],
        updated_by_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Update an existing transaction

        Args:
            transaction_id: The transaction ID to update
            update_data: Dict containing fields to update
            updated_by_id: ID of user making the update

        Returns:
            Dict with success status and updated transaction data
        """
        try:
            transaction = self.db.query(Transaction).filter(
                Transaction.id == transaction_id,
                Transaction.is_active == True
            ).first()

            if not transaction:
                return {
                    'success': False,
                    'message': 'Transaction not found',
                    'errors': ['Transaction does not exist or has been deleted']
                }

            # Validate update data
            validation_errors = self._validate_transaction_update_data(update_data, transaction)
            if validation_errors:
                return {
                    'success': False,
                    'message': 'Transaction update validation failed',
                    'errors': validation_errors
                }

            # Update allowed fields (tag_id maps to location_tag_id)
            updatable_fields = [
                'transaction_method', 'status', 'destination_ids', 'arrival_date',
                'destination_coordinates', 'notes', 'images', 'vehicle_info',
                'driver_info', 'hazardous_level', 'treatment_method', 'disposal_method',
                'location_tag_id', 'tenant_id'
            ]

            for field in updatable_fields:
                if field in update_data:
                    if field == 'status' and isinstance(update_data[field], str):
                        setattr(transaction, field, TransactionStatus(update_data[field]))
                    else:
                        setattr(transaction, field, update_data[field])

            if 'tag_id' in update_data:
                transaction.location_tag_id = update_data['tag_id']

            if updated_by_id:
                transaction.updated_by_id = updated_by_id

            transaction.updated_date = datetime.now()

            self.db.commit()

            return {
                'success': True,
                'message': 'Transaction updated successfully',
                'transaction': self._transaction_to_dict(transaction)
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error updating transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Database error occurred',
                'errors': [str(e)]
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Error updating transaction',
                'errors': [str(e)]
            }

    def update_transaction_with_records(
        self,
        transaction_id: int,
        update_data: Dict[str, Any],
        updated_by_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Update an existing transaction with records management
        Supports adding new records, updating existing records, and soft deleting removed records

        Args:
            transaction_id: The transaction ID to update
            update_data: Dict containing:
                - origin_id: Optional origin location ID
                - transaction_method: Optional transaction method
                - transaction_date: Optional transaction date
                - notes: Optional notes
                - images: Optional images list
                - records_to_add: List of new records to add
                - records_to_update: List of records to update
                - records_to_delete: List of record IDs to soft delete
            updated_by_id: ID of user making the update

        Returns:
            Dict with success status, updated transaction, and counts of operations
        """
        try:
            # Get the existing transaction
            transaction = self.db.query(Transaction).filter(
                Transaction.id == transaction_id,
                Transaction.is_active == True
            ).first()

            if not transaction:
                return {
                    'success': False,
                    'message': 'Transaction not found',
                    'errors': ['Transaction does not exist or has been deleted']
                }

            # Update transaction-level fields
            if 'origin_id' in update_data and update_data['origin_id']:
                transaction.origin_id = update_data['origin_id']
            if 'tag_id' in update_data:
                transaction.location_tag_id = update_data['tag_id']
            if 'location_tag_id' in update_data:
                transaction.location_tag_id = update_data['location_tag_id']
            if 'tenant_id' in update_data:
                transaction.tenant_id = update_data['tenant_id']
            if 'transaction_method' in update_data:
                transaction.transaction_method = update_data['transaction_method']
            if 'transaction_date' in update_data:
                transaction.transaction_date = update_data['transaction_date']
            if 'notes' in update_data:
                transaction.notes = update_data['notes']
            if 'images' in update_data:
                transaction.images = update_data['images']

            if updated_by_id:
                transaction.updated_by_id = updated_by_id
            transaction.updated_date = datetime.now()

            # Track operation counts
            records_added = 0
            records_updated = 0
            records_deleted = 0

            # Soft delete records
            records_to_delete = update_data.get('records_to_delete', [])
            if records_to_delete:
                for record_id in records_to_delete:
                    record = self.db.query(TransactionRecord).filter(
                        TransactionRecord.id == record_id,
                        TransactionRecord.created_transaction_id == transaction_id
                    ).first()
                    if record:
                        record.is_active = False
                        record.deleted_date = datetime.now()
                        records_deleted += 1
                        logger.info(f"Soft deleted transaction record {record_id}")

            # Update existing records
            records_to_update = update_data.get('records_to_update', [])
            if records_to_update:
                for record_data in records_to_update:
                    record_id = record_data.get('id')
                    if not record_id:
                        continue

                    record = self.db.query(TransactionRecord).filter(
                        TransactionRecord.id == record_id,
                        TransactionRecord.created_transaction_id == transaction_id,
                        TransactionRecord.is_active == True
                    ).first()

                    if record:
                        # Update record fields
                        if 'material_id' in record_data:
                            record.material_id = record_data['material_id']
                        if 'main_material_id' in record_data:
                            record.main_material_id = record_data['main_material_id']
                        if 'category_id' in record_data:
                            record.category_id = record_data['category_id']
                        if 'unit' in record_data:
                            record.unit = record_data['unit']
                        if 'transaction_date' in record_data:
                            record.transaction_date = record_data['transaction_date']
                        if 'origin_quantity' in record_data:
                            record.origin_quantity = _round_decimal(record_data['origin_quantity'])
                        if 'origin_weight_kg' in record_data:
                            record.origin_weight_kg = _round_decimal(record_data['origin_weight_kg'])
                        if 'images' in record_data:
                            record.images = record_data['images']
                        if 'origin_price_per_unit' in record_data:
                            record.origin_price_per_unit = _round_decimal(record_data['origin_price_per_unit'])
                        if 'total_amount' in record_data:
                            record.total_amount = _round_decimal(record_data['total_amount'])

                        record.updated_date = datetime.now()
                        records_updated += 1
                        logger.info(f"Updated transaction record {record_id}")

            # Add new records
            records_to_add = update_data.get('records_to_add', [])
            new_record_ids = []
            if records_to_add:
                for record_data in records_to_add:
                    # Set created_by_id
                    record_data['created_by_id'] = updated_by_id
                    record_result = self._create_transaction_record(record_data, transaction_id)
                    if record_result['success']:
                        new_record_ids.append(record_result['transaction_record'].id)
                        records_added += 1
                        logger.info(f"Added new transaction record {record_result['transaction_record'].id}")

            # Update transaction_records JSONB list
            # Get all active record IDs for this transaction
            active_records = self.db.query(TransactionRecord.id).filter(
                TransactionRecord.created_transaction_id == transaction_id,
                TransactionRecord.is_active == True
            ).all()
            active_record_ids = [r.id for r in active_records]
            transaction.transaction_records = active_record_ids

            # Recalculate total weight and amount from active records (2 decimal places)
            total_weight = Decimal('0')
            total_amount = Decimal('0')
            for record_id in active_record_ids:
                record = self.db.query(TransactionRecord).filter(
                    TransactionRecord.id == record_id
                ).first()
                if record:
                    total_weight += record.origin_weight_kg or Decimal('0')
                    total_amount += record.total_amount or Decimal('0')

            transaction.weight_kg = _round_decimal(total_weight)
            transaction.total_amount = _round_decimal(total_amount)

            self.db.commit()

            # Get updated transaction with records
            result = self.get_transaction(transaction_id, include_records=True)

            return {
                'success': True,
                'message': 'Transaction updated successfully with records',
                'transaction': result.get('transaction') if result.get('success') else self._transaction_to_dict(transaction),
                'records_added': records_added,
                'records_updated': records_updated,
                'records_deleted': records_deleted
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error updating transaction with records {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Database error occurred',
                'errors': [str(e)]
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating transaction with records {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Error updating transaction with records',
                'errors': [str(e)]
            }

    def delete_transaction(self, transaction_id: int, soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete a transaction (soft delete by default)

        Args:
            transaction_id: The transaction ID to delete
            soft_delete: Whether to soft delete (True) or hard delete (False)

        Returns:
            Dict with success status and message
        """
        try:
            transaction = self.db.query(Transaction).filter(
                Transaction.id == transaction_id,
                Transaction.is_active == True if soft_delete else True
            ).first()

            if not transaction:
                return {
                    'success': False,
                    'message': 'Transaction not found',
                    'errors': ['Transaction does not exist or has been deleted']
                }

            if soft_delete:
                # Soft delete - set is_active to False and set deleted_date
                transaction.is_active = False
                transaction.deleted_date = datetime.now()

                # Also soft delete associated transaction records
                self.db.query(TransactionRecord).filter(
                    TransactionRecord.created_transaction_id == transaction_id
                ).update({
                    TransactionRecord.is_active: False,
                    TransactionRecord.deleted_date: datetime.now()
                })

                message = 'Transaction soft deleted successfully'
            else:
                # Hard delete - remove from database
                # First delete associated transaction records
                self.db.query(TransactionRecord).filter(
                    TransactionRecord.created_transaction_id == transaction_id
                ).delete()

                self.db.delete(transaction)
                message = 'Transaction deleted successfully'

            self.db.commit()

            return {
                'success': True,
                'message': message
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error deleting transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Database error occurred',
                'errors': [str(e)]
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'message': 'Error deleting transaction',
                'errors': [str(e)]
            }

    # ========== TRANSACTION RECORD OPERATIONS ==========

    def _create_transaction_record(
        self,
        record_data: Dict[str, Any],
        created_transaction_id: int
    ) -> Dict[str, Any]:
        """
        Create a transaction record and link it to a transaction

        Args:
            record_data: Dict containing transaction record data
            created_transaction_id: ID of the transaction this record belongs to

        Returns:
            Dict with success status and transaction record data
        """
        try:
            # Validate transaction record data
            validation_errors = self._validate_transaction_record_data(record_data)
            if validation_errors:
                return {
                    'success': False,
                    'message': 'Transaction record validation failed',
                    'errors': validation_errors
                }

            # Parse transaction_date if provided
            transaction_date = None
            if record_data.get('transaction_date'):
                from datetime import datetime
                if isinstance(record_data['transaction_date'], str):
                    # Parse ISO format string
                    transaction_date = datetime.fromisoformat(record_data['transaction_date'].replace('Z', '+00:00'))
                elif isinstance(record_data['transaction_date'], datetime):
                    transaction_date = record_data['transaction_date']

            # Create transaction record
            transaction_record = TransactionRecord(
                status=record_data.get('status', TransactionRecordStatus.pending.value),
                created_transaction_id=created_transaction_id,
                traceability=[created_transaction_id],  # Start traceability with current transaction
                transaction_type=record_data.get('transaction_type', 'manual_input'),
                material_id=record_data.get('material_id'),
                main_material_id=record_data.get('main_material_id'),
                category_id=record_data.get('category_id'),
                tags=record_data.get('tags', []),
                unit=record_data.get('unit'),
                origin_quantity=_round_decimal(record_data.get('origin_quantity', 0)),
                origin_weight_kg=_round_decimal(record_data.get('origin_weight_kg', 0)),
                origin_price_per_unit=_round_decimal(record_data.get('origin_price_per_unit', 0)),
                total_amount=_round_decimal(record_data.get('total_amount', 0)),
                currency_id=record_data.get('currency_id'),
                notes=record_data.get('notes'),
                images=record_data.get('images', []),
                destination_id=record_data.get('destination_id'),
                origin_coordinates=record_data.get('origin_coordinates'),
                destination_coordinates=record_data.get('destination_coordinates'),
                hazardous_level=record_data.get('hazardous_level', 0),
                treatment_method=record_data.get('treatment_method'),
                disposal_method=record_data.get('disposal_method'),
                transaction_date=transaction_date,  # Add transaction_date
                created_by_id=record_data.get('created_by_id')
            )

            # Calculate total amount if not provided (then round to 2 decimals)
            if not transaction_record.total_amount:
                transaction_record.calculate_total_value()
            transaction_record.total_amount = _round_decimal(transaction_record.total_amount)

            self.db.add(transaction_record)
            self.db.flush()  # Get the ID

            return {
                'success': True,
                'transaction_record': transaction_record
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error creating transaction record: {str(e)}")
            return {
                'success': False,
                'message': 'Database error occurred',
                'errors': [str(e)]
            }
        except Exception as e:
            logger.error(f"Error creating transaction record: {str(e)}")
            return {
                'success': False,
                'message': 'Error creating transaction record',
                'errors': [str(e)]
            }

    # ========== PRIVATE HELPER METHODS ==========

    def _validate_transaction_data(self, data: Dict[str, Any]) -> List[str]:
        """Validate transaction data"""
        errors = []

        # Required fields
        if not data.get('organization_id'):
            errors.append('organization_id is required')
        if not data.get('origin_id'):
            errors.append('origin_id is required')
        if not data.get('created_by_id'):
            errors.append('created_by_id is required')

        # Validate transaction method
        transaction_method = data.get('transaction_method', 'origin')
        valid_methods = ['origin', 'transport', 'transform', 'qr_input', 'scale_input']
        if transaction_method not in valid_methods:
            errors.append(f'transaction_method must be one of: {", ".join(valid_methods)}')

        # Validate status
        status = data.get('status', 'pending')
        try:
            TransactionStatus(status)
        except ValueError:
            valid_statuses = [s.value for s in TransactionStatus]
            errors.append(f'status must be one of: {", ".join(valid_statuses)}')

        # Validate hazardous level
        hazardous_level = data.get('hazardous_level', 0)
        if not isinstance(hazardous_level, int) or hazardous_level < 0 or hazardous_level > 5:
            errors.append('hazardous_level must be an integer between 0 and 5')

        # Validate organization exists
        if data.get('organization_id'):
            org = self.db.query(Organization).filter(
                Organization.id == data['organization_id'],
                Organization.is_active == True
            ).first()
            if not org:
                errors.append('Organization not found or inactive')

        # Validate origin location exists
        if data.get('origin_id'):
            origin = self.db.query(UserLocation).filter(
                UserLocation.id == data['origin_id'],
                UserLocation.is_active == True
            ).first()
            if not origin:
                errors.append('Origin location not found or inactive')

        # Note: destination_ids is populated from transaction records, no validation needed here

        return errors

    def _validate_transaction_record_data(self, data: Dict[str, Any]) -> List[str]:
        """Validate transaction record data"""
        errors = []

        # Required fields
        required_fields = ['main_material_id', 'category_id', 'unit', 'created_by_id']
        for field in required_fields:
            if not data.get(field):
                errors.append(f'{field} is required')

        # Validate transaction type
        transaction_type = data.get('transaction_type', 'manual_input')
        valid_types = ['manual_input', 'rewards', 'iot']
        if transaction_type not in valid_types:
            errors.append(f'transaction_type must be one of: {", ".join(valid_types)}')

        # Validate numeric fields
        numeric_fields = ['origin_quantity', 'origin_weight_kg', 'origin_price_per_unit', 'total_amount']
        for field in numeric_fields:
            value = data.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                errors.append(f'{field} must be a non-negative number')

        # Validate hazardous level
        hazardous_level = data.get('hazardous_level', 0)
        if not isinstance(hazardous_level, int) or hazardous_level < 0 or hazardous_level > 5:
            errors.append('hazardous_level must be an integer between 0 and 5')

        return errors

    def _validate_transaction_update_data(self, data: Dict[str, Any], transaction: Transaction) -> List[str]:
        """Validate transaction update data"""
        errors = []

        # Status transition validation
        if 'status' in data:
            current_status = transaction.status
            new_status = data['status']
            if isinstance(new_status, str):
                try:
                    new_status = TransactionStatus(new_status)
                except ValueError:
                    valid_statuses = [s.value for s in TransactionStatus]
                    errors.append(f'status must be one of: {", ".join(valid_statuses)}')
                    return errors

            # Define valid status transitions
            valid_transitions = {
                TransactionStatus.pending: [TransactionStatus.approved, TransactionStatus.rejected],
                TransactionStatus.approved: [TransactionStatus.pending, TransactionStatus.rejected],
                TransactionStatus.rejected: [TransactionStatus.pending, TransactionStatus.approved],
                # TransactionStatus.in_transit: [TransactionStatus.delivered, TransactionStatus.cancelled],
                # TransactionStatus.delivered: [TransactionStatus.completed, TransactionStatus.rejected],
                # TransactionStatus.completed: [],  # Final state
                # TransactionStatus.cancelled: [],  # Final state
                # TransactionStatus.rejected: []   # Final state
            }

            if new_status not in valid_transitions.get(current_status, []):
                errors.append(f'Cannot transition from {current_status.value} to {new_status.value}')

        return errors

    def _calculate_transaction_totals(self, transaction: Transaction):
        """Calculate total weight and amount from transaction records"""
        if transaction.transaction_records:
            records = self.db.query(TransactionRecord).filter(
                TransactionRecord.id.in_(transaction.transaction_records),
                TransactionRecord.is_active == True
            ).all()

            total_weight = sum((record.origin_weight_kg or Decimal('0') for record in records), Decimal('0'))
            total_amount = sum((record.total_amount or Decimal('0') for record in records), Decimal('0'))

            transaction.weight_kg = _round_decimal(total_weight)
            transaction.total_amount = _round_decimal(total_amount)

    def _transaction_to_dict(self, transaction: Transaction) -> Dict[str, Any]:
        """Convert Transaction object to dictionary"""
        # Handle images - use JSONB field directly to avoid relationship issues
        images = transaction.images if hasattr(transaction, 'images') else []

        # Include location objects if available
        origin_location = None
        if hasattr(transaction, 'origin') and transaction.origin:
            origin_location = {
                'id': transaction.origin.id,
                'name_en': transaction.origin.name_en if hasattr(transaction.origin, 'name_en') else None,
                'name_th': transaction.origin.name_th if hasattr(transaction.origin, 'name_th') else None,
                'display_name': transaction.origin.display_name if hasattr(transaction.origin, 'display_name') else None
            }

        # Get creator display name from relationship
        created_by_name = None
        if hasattr(transaction, 'created_by') and transaction.created_by:
            created_by_name = transaction.created_by.display_name or transaction.created_by.name_en or transaction.created_by.name_th

        return {
            'id': transaction.id,
            'transaction_records': transaction.transaction_records,
            'transaction_method': transaction.transaction_method,
            'status': transaction.status.value if transaction.status else None,
            'organization_id': transaction.organization_id,
            'origin_id': transaction.origin_id,
            'destination_ids': transaction.destination_ids if hasattr(transaction, 'destination_ids') else [],
            'location_tag_id': transaction.location_tag_id,
            'tag_id': transaction.location_tag_id,  # Alias for API
            'tenant_id': getattr(transaction, 'tenant_id', None),
            'origin_location': origin_location,
            'weight_kg': _round_float(transaction.weight_kg),
            'total_amount': _round_float(transaction.total_amount),
            'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
            'arrival_date': transaction.arrival_date.isoformat() if transaction.arrival_date else None,
            'origin_coordinates': transaction.origin_coordinates,
            'destination_coordinates': transaction.destination_coordinates,
            'notes': transaction.notes,
            'images': images,  # Use JSONB field for image URLs
            'vehicle_info': transaction.vehicle_info,
            'driver_info': transaction.driver_info,
            'hazardous_level': transaction.hazardous_level,
            'treatment_method': transaction.treatment_method,
            'disposal_method': transaction.disposal_method,
            'created_by_id': transaction.created_by_id,
            'created_by_name': created_by_name,
            'updated_by_id': transaction.updated_by_id,
            'approved_by_id': transaction.approved_by_id,
            'ai_audit_status': transaction.ai_audit_status.value if hasattr(transaction, 'ai_audit_status') and transaction.ai_audit_status else None,
            'ai_audit_note': transaction.ai_audit_note if hasattr(transaction, 'ai_audit_note') else None,
            'is_user_audit': transaction.is_user_audit if hasattr(transaction, 'is_user_audit') else False,
            'is_active': transaction.is_active,
            'created_date': transaction.created_date.isoformat() if transaction.created_date else None,
            'updated_date': transaction.updated_date.isoformat() if transaction.updated_date else None,
            'deleted_date': transaction.deleted_date.isoformat() if transaction.deleted_date else None
        }

    def _transaction_record_to_dict(self, record: TransactionRecord) -> Dict[str, Any]:
        """Convert TransactionRecord object to dictionary"""
        # Include material object if available
        material = None
        if hasattr(record, 'material') and record.material:
            material = {
                'id': record.material.id,
                'name_en': record.material.name_en if hasattr(record.material, 'name_en') else None,
                'name_th': record.material.name_th if hasattr(record.material, 'name_th') else None
            }

        # Include category object if available
        category = None
        if hasattr(record, 'category') and record.category:
            category = {
                'id': record.category.id,
                'name_en': record.category.name_en if hasattr(record.category, 'name_en') else None,
                'name_th': record.category.name_th if hasattr(record.category, 'name_th') else None
            }

        # Include destination object if available
        destination = None
        if hasattr(record, 'destination') and record.destination:
            destination = {
                'id': record.destination.id,
                'name_en': record.destination.name_en if hasattr(record.destination, 'name_en') else None,
                'name_th': record.destination.name_th if hasattr(record.destination, 'name_th') else None,
                'display_name': record.destination.display_name if hasattr(record.destination, 'display_name') else None
            }

        return {
            'id': record.id,
            'status': record.status,
            'created_transaction_id': record.created_transaction_id,
            'traceability': record.traceability,
            'transaction_type': record.transaction_type,
            'material_id': record.material_id,
            'main_material_id': record.main_material_id,
            'category_id': record.category_id,
            'material': material,
            'category': category,
            'tags': record.tags,
            'unit': record.unit,
            'origin_quantity': _round_float(record.origin_quantity),
            'origin_weight_kg': _round_float(record.origin_weight_kg),
            'origin_price_per_unit': _round_float(record.origin_price_per_unit),
            'total_amount': _round_float(record.total_amount),
            'currency_id': record.currency_id,
            'notes': record.notes,
            'images': record.images,
            'destination_id': record.destination_id,
            'destination': destination,
            'origin_coordinates': record.origin_coordinates,
            'destination_coordinates': record.destination_coordinates,
            'hazardous_level': record.hazardous_level,
            'treatment_method': record.treatment_method,
            'disposal_method': record.disposal_method,
            'created_by_id': record.created_by_id,
            'approved_by_id': record.approved_by_id,
            'transaction_date': record.transaction_date.isoformat() if record.transaction_date else None,
            'completed_date': record.completed_date.isoformat() if record.completed_date else None,
            'is_active': record.is_active,
            'created_date': record.created_date.isoformat() if record.created_date else None,
            'updated_date': record.updated_date.isoformat() if record.updated_date else None,
            'deleted_date': record.deleted_date.isoformat() if record.deleted_date else None
        }