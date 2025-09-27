"""
Debug Handlers - Development utilities for debugging and testing
WARNING: These endpoints should only be available in development environments
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ...models.transactions.transactions import Transaction, TransactionStatus
from ...database import get_session
from ...exceptions import APIException

logger = logging.getLogger(__name__)

def handle_debug_routes(event: Dict[str, Any], data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """
    Route handler for debug endpoints
    """
    try:
        path = event.get("rawPath", "")
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

        logger.info(f"Debug route: {method} {path}")

        # Get current user from commonParams
        current_user = kwargs.get('current_user', {})
        user_id = current_user.get('user_id')
        organization_id = current_user.get('organization_id')

        if not user_id or not organization_id:
            raise APIException(
                message="User authentication required",
                status_code=401,
                error_code="AUTHENTICATION_REQUIRED"
            )

        # Route to specific handlers
        if path == "/api/debug/transaction/reset_pending_all" and method == "POST":
            return reset_all_transactions_to_pending(user_id, organization_id, **kwargs)

        else:
            raise APIException(
                message=f"Debug endpoint not found: {method} {path}",
                status_code=404,
                error_code="DEBUG_ENDPOINT_NOT_FOUND"
            )

    except APIException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in debug route handler: {str(e)}")
        raise APIException(
            message="Internal server error in debug handlers",
            status_code=500,
            error_code="DEBUG_HANDLER_ERROR"
        )

def reset_all_transactions_to_pending(user_id: int, organization_id: int, **kwargs) -> Dict[str, Any]:
    """
    DEBUG: Reset all transactions of current user's organization to pending status
    WARNING: This is a destructive operation that should only be used for testing
    """
    try:
        # Get database session - use the one passed in kwargs if available
        session = kwargs.get('session')

        if session:
            # Use existing session
            try:
                # Find all transactions for the organization that are NOT already pending
                transactions_to_reset = session.query(Transaction).filter(
                    Transaction.organization_id == organization_id,
                    Transaction.status != TransactionStatus.pending,
                    Transaction.is_active == True
                ).all()

                # Count of transactions that will be updated
                update_count = len(transactions_to_reset)

                if update_count == 0:
                    return {
                        "success": True,
                        "message": "No transactions to reset - all are already pending",
                        "data": {
                            "updated_count": 0,
                            "organization_id": organization_id,
                            "reset_by": user_id,
                            "reset_at": datetime.now(timezone.utc).isoformat()
                        }
                    }

                # Reset all transactions to pending status
                updated_transactions = []
                for transaction in transactions_to_reset:
                    old_status = transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status)
                    transaction.status = TransactionStatus.pending
                    transaction.updated_date = datetime.now(timezone.utc)

                    # Clear any audit notes to allow fresh auditing
                    transaction.notes = None

                    updated_transactions.append({
                        "transaction_id": transaction.id,
                        "old_status": old_status,
                        "new_status": "pending"
                    })

                    logger.info(f"Reset transaction {transaction.id} from {old_status} to pending")

                # Commit the changes
                session.commit()

                logger.info(f"DEBUG: Reset {update_count} transactions to pending for organization {organization_id} by user {user_id}")

                return {
                    "success": True,
                    "message": f"Successfully reset {update_count} transactions to pending status",
                    "data": {
                        "updated_count": update_count,
                        "organization_id": organization_id,
                        "reset_by": user_id,
                        "reset_at": datetime.now(timezone.utc).isoformat(),
                        "updated_transactions": updated_transactions
                    }
                }

            except Exception as e:
                session.rollback()
                raise e
        else:
            # Create new session using context manager
            with get_session() as session:
                # Find all transactions for the organization that are NOT already pending
                transactions_to_reset = session.query(Transaction).filter(
                    Transaction.organization_id == organization_id,
                    Transaction.status != TransactionStatus.pending,
                    Transaction.is_active == True
                ).all()

                # Count of transactions that will be updated
                update_count = len(transactions_to_reset)

                if update_count == 0:
                    return {
                        "success": True,
                        "message": "No transactions to reset - all are already pending",
                        "data": {
                            "updated_count": 0,
                            "organization_id": organization_id,
                            "reset_by": user_id,
                            "reset_at": datetime.now(timezone.utc).isoformat()
                        }
                    }

                # Reset all transactions to pending status
                updated_transactions = []
                for transaction in transactions_to_reset:
                    old_status = transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status)
                    transaction.status = TransactionStatus.pending
                    transaction.updated_date = datetime.now(timezone.utc)

                    # Clear any audit notes to allow fresh auditing
                    transaction.notes = None

                    updated_transactions.append({
                        "transaction_id": transaction.id,
                        "old_status": old_status,
                        "new_status": "pending"
                    })

                    logger.info(f"Reset transaction {transaction.id} from {old_status} to pending")

                # Commit the changes
                session.commit()

                logger.info(f"DEBUG: Reset {update_count} transactions to pending for organization {organization_id} by user {user_id}")

                return {
                    "success": True,
                    "message": f"Successfully reset {update_count} transactions to pending status",
                    "data": {
                        "updated_count": update_count,
                        "organization_id": organization_id,
                        "reset_by": user_id,
                        "reset_at": datetime.now(timezone.utc).isoformat(),
                        "updated_transactions": updated_transactions
                    }
                }

    except SQLAlchemyError as e:
        logger.error(f"Database error in reset_all_transactions_to_pending: {str(e)}")
        raise APIException(
            message="Database error while resetting transactions",
            status_code=500,
            error_code="DATABASE_ERROR"
        )
    except Exception as e:
        logger.error(f"Unexpected error in reset_all_transactions_to_pending: {str(e)}")
        raise APIException(
            message="Failed to reset transactions",
            status_code=500,
            error_code="RESET_TRANSACTIONS_ERROR"
        )