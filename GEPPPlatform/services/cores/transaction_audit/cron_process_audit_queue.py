"""
Cron Job: Process AI Audit Queue
Processes transaction_audit_history records with 'in_progress' status
"""

import logging
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from ....models.logs.transaction_audit_history import TransactionAuditHistory
from ....models.transactions.transactions import Transaction, AIAuditStatus
from .transaction_audit_service import TransactionAuditService

logger = logging.getLogger(__name__)


def process_audit_queue(db: Session) -> Dict[str, Any]:
    """
    Process all in_progress audit batches

    This function should be called by a cron job periodically (e.g., every minute)
    to process queued AI audit batches.

    Args:
        db: Database session

    Returns:
        Dict containing processing results
    """
    try:
        logger.info("Starting audit queue processing")

        # Get Gemini API key from environment
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            logger.error('Gemini API key not configured')
            return {
                'success': False,
                'error': 'Gemini API key not configured',
                'processed_batches': 0
            }

        # Initialize audit service
        audit_service = TransactionAuditService(gemini_api_key)

        # Get all in_progress audit batches
        in_progress_batches = db.query(TransactionAuditHistory).filter(
            TransactionAuditHistory.status == 'in_progress',
            TransactionAuditHistory.deleted_date.is_(None)
        ).all()

        if not in_progress_batches:
            logger.info("No in_progress audit batches found")
            return {
                'success': True,
                'message': 'No batches to process',
                'processed_batches': 0
            }

        logger.info(f"Found {len(in_progress_batches)} in_progress audit batches to process")

        processed_count = 0
        failed_count = 0

        for batch in in_progress_batches:
            try:
                logger.info(f"Processing audit batch {batch.id} for organization {batch.organization_id}")

                # Get transactions for this batch that are in 'queued' status
                transaction_ids = batch.transactions
                transactions = db.query(Transaction).filter(
                    Transaction.id.in_(transaction_ids),
                    Transaction.ai_audit_status == AIAuditStatus.queued,
                    Transaction.deleted_date.is_(None)
                ).all()

                if not transactions:
                    logger.warning(f"No queued transactions found for batch {batch.id}")
                    # Update batch as completed with no results
                    batch.status = 'completed'
                    batch.completed_at = datetime.now(timezone.utc)
                    batch.processed_transactions = 0
                    db.commit()
                    continue

                # Get organization-specific audit rules
                audit_rules = audit_service._get_audit_rules(db, batch.organization_id)
                if not audit_rules:
                    logger.error(f"No audit rules found for organization {batch.organization_id}")
                    batch.status = 'failed'
                    batch.error_message = 'No audit rules found for this organization'
                    batch.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    failed_count += 1
                    continue

                # Prepare transaction data
                transaction_audit_data = audit_service._prepare_transaction_data(db, transactions)

                # Process transactions with AI
                audit_results = audit_service._process_transactions_with_ai(
                    transaction_audit_data,
                    audit_rules
                )

                # Check organization's AI audit permission
                from ....models.subscriptions.organizations import Organization
                allow_ai_audit = False
                org = db.query(Organization).filter(Organization.id == batch.organization_id).first()
                if org and hasattr(org, 'allow_ai_audit'):
                    allow_ai_audit = org.allow_ai_audit

                # Update transaction statuses
                updated_count = audit_service._update_transaction_statuses(db, audit_results, allow_ai_audit)

                # Calculate statistics
                approved_count = sum(1 for result in audit_results if result.get('audit_status') == 'approved')
                rejected_count = sum(1 for result in audit_results if result.get('audit_status') == 'rejected')

                # Calculate token usage
                total_input_tokens = sum(r.get('token_usage', {}).get('input_tokens', 0) for r in audit_results)
                total_output_tokens = sum(r.get('token_usage', {}).get('output_tokens', 0) for r in audit_results)
                total_tokens = sum(r.get('token_usage', {}).get('total_tokens', 0) for r in audit_results)

                # Update batch record with results
                batch.audit_info = {
                    'audit_results': audit_results,
                    'summary': {
                        'total_transactions': len(transaction_ids),
                        'processed_transactions': len(audit_results),
                        'approved_count': approved_count,
                        'rejected_count': rejected_count,
                        'token_usage': {
                            'total_input_tokens': total_input_tokens,
                            'total_output_tokens': total_output_tokens,
                            'total_tokens': total_tokens
                        }
                    }
                }
                batch.processed_transactions = len(audit_results)
                batch.approved_count = approved_count
                batch.rejected_count = rejected_count
                batch.status = 'completed'
                batch.completed_at = datetime.now(timezone.utc)

                db.commit()

                logger.info(f"Successfully processed audit batch {batch.id}. "
                           f"Processed: {len(audit_results)}, Updated: {updated_count}, "
                           f"Tokens: {total_tokens}")
                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing audit batch {batch.id}: {str(e)}")
                db.rollback()

                # Mark batch as failed
                try:
                    batch.status = 'failed'
                    batch.error_message = str(e)
                    batch.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    failed_count += 1
                except Exception as update_error:
                    logger.error(f"Failed to update batch {batch.id} status: {str(update_error)}")
                    db.rollback()

        logger.info(f"Audit queue processing completed. Processed: {processed_count}, Failed: {failed_count}")

        return {
            'success': True,
            'message': f'Processed {processed_count} batches, {failed_count} failed',
            'processed_batches': processed_count,
            'failed_batches': failed_count,
            'total_batches': len(in_progress_batches)
        }

    except Exception as e:
        logger.error(f"Error in audit queue processing: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processed_batches': 0
        }


def main():
    """
    Main entry point for the cron job
    Can be called directly via python -m or from a scheduler
    """
    from ....database import get_db

    db = next(get_db())
    try:
        result = process_audit_queue(db)
        logger.info(f"Cron job result: {result}")
        return result
    finally:
        db.close()


if __name__ == "__main__":
    main()
