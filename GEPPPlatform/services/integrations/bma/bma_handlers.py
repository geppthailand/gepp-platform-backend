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
            return handle_bma_transaction_batch(
                bma_service,
                data,
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
    organization_id: int
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
            organization_id=organization_id
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
