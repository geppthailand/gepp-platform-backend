"""
BMA Integration API handlers
"""

from typing import Dict, Any
import logging
import traceback

from .bma_service import BMAIntegrationService
from ....exceptions import (
    APIException,
    BadRequestException,
    ValidationException
)

logger = logging.getLogger(__name__)


def handle_bma_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for BMA integration routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_organization_id = current_user.get('organization_id')

    if not current_user_organization_id:
        raise BadRequestException('Organization ID is required')

    bma_service = BMAIntegrationService(db_session)

    try:
        # Route to specific handlers
        if '/api/integration/bma/transaction' in path and method == 'POST':
            # Extract JWT token from headers
            headers = params.get('headers', {})
            auth_header = headers.get('Authorization') or headers.get('authorization', '')
            jwt_token = None
            if auth_header and auth_header.startswith('Bearer '):
                jwt_token = auth_header.split(' ')[1]

            return handle_bma_transaction_batch(
                bma_service,
                data,
                current_user_organization_id,
                jwt_token
            )

        elif '/api/integration/bma/transaction' in path and method == 'GET':
            # Check if it's a specific transaction retrieval or list
            path_parts = path.strip('/').split('/')
            # Path format: /api/integration/bma/transaction[/{transaction_version}/{house_id}]
            if len(path_parts) >= 6:  # /api/integration/bma/transaction/{version}/{house_id}
                transaction_version = path_parts[4]
                house_id = path_parts[5]
                return handle_get_transaction_by_ids(
                    bma_service,
                    transaction_version,
                    house_id,
                    current_user_organization_id
                )
            else:
                # List transactions
                query_params = event.get('queryStringParameters') or {}
                return handle_get_transactions(
                    bma_service,
                    query_params,
                    current_user_organization_id
                )

        elif '/api/integration/bma/usage' in path and method == 'GET':
            return handle_bma_usage(
                bma_service,
                current_user_organization_id
            )

        elif '/api/integration/bma/audit_status' in path and method == 'GET':
            return handle_bma_audit_status(
                bma_service,
                current_user_organization_id
            )

        elif '/api/integration/bma/add_transactions_to_audit_queue' in path and method == 'POST':
            return handle_add_transactions_to_audit_queue(
                bma_service,
                current_user_organization_id
            )

        else:
            raise APIException(
                message='Route not found',
                status_code=404,
                error_code='ROUTE_NOT_FOUND'
            )

    except (BadRequestException, ValidationException) as e:
        logger.error(f"Validation error in BMA route: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error in BMA route handler: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Internal server error: {str(e)}",
            status_code=500,
            error_code='INTERNAL_ERROR'
        )


def handle_bma_transaction_batch(
    bma_service: BMAIntegrationService,
    data: Dict[str, Any],
    organization_id: int,
    jwt_token: str = None
) -> Dict[str, Any]:
    """
    Handle POST /api/integration/bma/transaction
    Process a batch of BMA transactions

    Expected request body:
    {
        "batch": {
            "<transaction_version>": {
                "<house_id>": {
                    "timestamp": "2025-10-23T10:00:00+07:00",
                    "material": {
                        "general": {
                            "image_url": "https://example.com/image.jpg"
                        },
                        "recyclable": {
                            "image_url": "https://example.com/image2.jpg"
                        }
                    }
                }
            }
        }
    }
    """
    try:
        if not data:
            raise BadRequestException('Request body is required')

        result = bma_service.process_bma_transaction_batch(
            batch_data=data,
            organization_id=organization_id,
            jwt_token=jwt_token
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error processing BMA transaction batch: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to process transaction batch: {str(e)}",
            status_code=500,
            error_code='BATCH_PROCESSING_ERROR'
        )


def handle_bma_usage(
    bma_service: BMAIntegrationService,
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/integration/bma/usage
    Get subscription usage information

    Returns subscription usage limits and current usage
    """
    try:
        result = bma_service.get_subscription_usage(
            organization_id=organization_id
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error getting subscription usage: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to get subscription usage: {str(e)}",
            status_code=500,
            error_code='USAGE_RETRIEVAL_ERROR'
        )


def handle_bma_audit_status(
    bma_service: BMAIntegrationService,
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/integration/bma/audit_status
    Get audit status summary for transactions in the past year

    Returns summary of transaction statuses and AI audit statuses
    """
    try:
        result = bma_service.get_audit_status_summary(
            organization_id=organization_id
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error getting audit status summary: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to get audit status summary: {str(e)}",
            status_code=500,
            error_code='AUDIT_STATUS_RETRIEVAL_ERROR'
        )


def handle_add_transactions_to_audit_queue(
    bma_service: BMAIntegrationService,
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/integration/bma/add_transactions_to_audit_queue
    Add all transactions with ai_audit_status = 'null' to the audit queue

    Returns number of transactions queued
    """
    try:
        result = bma_service.add_transactions_to_audit_queue(
            organization_id=organization_id
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error adding transactions to audit queue: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to add transactions to audit queue: {str(e)}",
            status_code=500,
            error_code='AUDIT_QUEUE_ERROR'
        )


def handle_get_transactions(
    bma_service: BMAIntegrationService,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/integration/bma/transaction
    Get list of transactions filtered by query parameters with pagination

    Query Parameters:
        - limit: Number of transactions to return per page (default: 100, max: 1000)
        - page: Page number (default: 1, starts from 1)
        - transaction_version: Filter by transaction version (ext_id_1)
        - origin_id: Filter by origin ID (default: 2170)
    """
    try:
        # Parse query parameters
        limit = int(query_params.get('limit', 100))
        limit = min(limit, 1000)  # Cap at 1000

        page = int(query_params.get('page', 1))
        page = max(1, page)  # Minimum page 1

        transaction_version = query_params.get('transaction_version')
        origin_id = query_params.get('origin_id', '2170')

        # Convert origin_id to int
        try:
            origin_id = int(origin_id)
        except (ValueError, TypeError):
            raise BadRequestException('Invalid origin_id format. Must be an integer.')

        result = bma_service.get_transactions(
            organization_id=organization_id,
            limit=limit,
            page=page,
            transaction_version=transaction_version,
            origin_id=origin_id
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error retrieving transactions: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to retrieve transactions: {str(e)}",
            status_code=500,
            error_code='TRANSACTION_RETRIEVAL_ERROR'
        )


def handle_get_transaction_by_ids(
    bma_service: BMAIntegrationService,
    transaction_version: str,
    house_id: str,
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/integration/bma/transaction/{transaction_version}/{house_id}
    Get a specific transaction by ext_id_1 (transaction_version) and ext_id_2 (house_id)

    Path Parameters:
        - transaction_version: Transaction version (ext_id_1)
        - house_id: House ID (ext_id_2)
    """
    try:
        result = bma_service.get_transaction_by_ids(
            organization_id=organization_id,
            transaction_version=transaction_version,
            house_id=house_id
        )

        return result

    except (BadRequestException, ValidationException):
        raise

    except Exception as e:
        logger.error(f"Error retrieving transaction: {str(e)}")
        logger.error(traceback.format_exc())
        raise APIException(
            message=f"Failed to retrieve transaction: {str(e)}",
            status_code=500,
            error_code='TRANSACTION_RETRIEVAL_ERROR'
        )
