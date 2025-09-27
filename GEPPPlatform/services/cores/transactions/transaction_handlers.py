"""
Transaction API handlers for CRUD operations
"""

from typing import Dict, Any
import logging
import traceback

from .transaction_service import TransactionService
from .presigned_url_service import TransactionPresignedUrlService

logger = logging.getLogger(__name__)
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_transaction_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for transaction management routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    transaction_service = TransactionService(db_session)

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')

    try:
        # Route to specific handlers
        if path == '/api/transactions' and method == 'GET':
            return handle_list_transactions(
                transaction_service,
                query_params,
                current_user_organization_id
            )

        elif path == '/api/transactions' and method == 'POST':
            return handle_create_transaction(
                transaction_service,
                data,
                current_user_id,
                current_user_organization_id
            )

        elif '/api/transactions/' in path and method == 'GET':
            # GET /api/transactions/{id}
            transaction_id = _extract_transaction_id_from_path(path)
            include_records = query_params.get('include_records', 'false').lower() == 'true'
            return handle_get_transaction(
                transaction_service,
                transaction_id,
                include_records,
                current_user_organization_id
            )

        elif '/api/transactions/' in path and method == 'PUT':
            # PUT /api/transactions/{id}
            transaction_id = _extract_transaction_id_from_path(path)
            return handle_update_transaction(
                transaction_service,
                transaction_id,
                data,
                current_user_id,
                current_user_organization_id
            )

        elif '/api/transactions/' in path and method == 'DELETE':
            # DELETE /api/transactions/{id}
            transaction_id = _extract_transaction_id_from_path(path)
            soft_delete = query_params.get('soft_delete', 'true').lower() == 'true'
            return handle_delete_transaction(
                transaction_service,
                transaction_id,
                soft_delete,
                current_user_organization_id
            )

        elif '/api/transactions/' in path and 'images' in path and method == 'POST':
            # POST /api/transactions/{id}/images - Upload images for transaction
            transaction_id = _extract_transaction_id_from_path(path)
            return handle_upload_transaction_images(
                transaction_service,
                transaction_id,
                data,
                current_user_id,
                current_user_organization_id
            )

        elif path == '/api/transactions/presigneds' and method == 'POST':
            # POST /api/transactions/presigneds - Get presigned URLs for file uploads
            return handle_get_presigned_urls(
                data,
                current_user_id,
                current_user_organization_id
            )

        elif path == '/api/transactions/get_view_presigned' and method == 'POST':
            # POST /api/transactions/get_view_presigned - Get presigned URLs for viewing files
            return handle_get_view_presigned_urls(
                data,
                current_user_id,
                current_user_organization_id
            )

        else:
            return {
                'success': False,
                'message': 'Transaction route not found',
                'error_code': 'ROUTE_NOT_FOUND'
            }

    except ValidationException as e:
        return {
            'success': False,
            'message': str(e),
            'error_code': 'VALIDATION_ERROR'
        }
    except NotFoundException as e:
        return {
            'success': False,
            'message': str(e),
            'error_code': 'NOT_FOUND'
        }
    except UnauthorizedException as e:
        return {
            'success': False,
            'message': str(e),
            'error_code': 'UNAUTHORIZED'
        }
    except BadRequestException as e:
        return {
            'success': False,
            'message': str(e),
            'error_code': 'BAD_REQUEST'
        }
    except APIException as e:
        print(e)
        return {
            'success': False,
            'message': str(e),
            'error_code': 'API_ERROR',
            "stack_trace": traceback.format_exc()
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'error_code': 'INTERNAL_ERROR'
        }


def handle_create_transaction(
    transaction_service: TransactionService,
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions - Create new transaction
    """
    try:
        # Validate request data
        if not data:
            raise BadRequestException('Request body is required')

        # Extract transaction data and records data
        transaction_data = data.get('transaction', data)  # Support both nested and flat structure
        transaction_records_data = data.get('transaction_records', data.get('records', []))

        # Set organization_id and created_by_id from current user
        transaction_data['organization_id'] = current_user_organization_id
        transaction_data['created_by_id'] = int(current_user_id)

        # Set created_by_id for all transaction records
        for record_data in transaction_records_data:
            record_data['created_by_id'] = int(current_user_id)

        # Create transaction
        result = transaction_service.create_transaction(
            transaction_data,
            transaction_records_data if transaction_records_data else None
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'transaction': result['transaction'],
                'transaction_records_count': result.get('transaction_records_count', 0)
            }
        else:
            raise ValidationException(result['message'])

    except Exception as e:
        if isinstance(e, (ValidationException, BadRequestException)):
            raise
        raise APIException(f'Failed to create transaction: {str(e)}')


def handle_get_transaction(
    transaction_service: TransactionService,
    transaction_id: int,
    include_records: bool,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transactions/{id} - Get transaction by ID
    """
    try:
        result = transaction_service.get_transaction(transaction_id, include_records)

        if not result['success']:
            if 'not found' in result['message'].lower():
                raise NotFoundException(result['message'])
            else:
                raise APIException(result['message'])

        # Check if user has access to this transaction
        transaction = result['transaction']
        if transaction['organization_id'] != current_user_organization_id:
            raise UnauthorizedException('Access denied: Transaction belongs to different organization')

        return {
            'success': True,
            'transaction': transaction
        }

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException)):
            raise
        raise APIException(f'Failed to retrieve transaction: {str(e)}')


def handle_list_transactions(
    transaction_service: TransactionService,
    query_params: Dict[str, str],
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transactions - List transactions with filtering
    """
    try:
        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = min(int(query_params.get('page_size', 20)), 100)  # Max 100 per page
        status = query_params.get('status')
        origin_id = int(query_params['origin_id']) if query_params.get('origin_id') else None
        destination_id = int(query_params['destination_id']) if query_params.get('destination_id') else None
        include_records = query_params.get('include_records', 'false').lower() == 'true'

        # Always filter by user's organization
        result = transaction_service.list_transactions(
            organization_id=current_user_organization_id,
            status=status,
            origin_id=origin_id,
            destination_id=destination_id,
            page=page,
            page_size=page_size,
            include_records=include_records
        )

        if result['success']:
            return {
                'success': True,
                'transactions': result['transactions'],
                'pagination': result['pagination']
            }
        else:
            raise APIException(result['message'])

    except ValueError as e:
        raise BadRequestException(f'Invalid query parameter: {str(e)}')
    except Exception as e:
        if isinstance(e, (BadRequestException, APIException)):
            raise
        raise APIException(f'Failed to list transactions: {str(e)}')


def handle_update_transaction(
    transaction_service: TransactionService,
    transaction_id: int,
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle PUT /api/transactions/{id} - Update transaction
    """
    try:
        # Validate request data
        if not data:
            raise BadRequestException('Request body is required')

        # First, check if transaction exists and user has access
        existing_result = transaction_service.get_transaction(transaction_id)
        if not existing_result['success']:
            raise NotFoundException('Transaction not found')

        transaction = existing_result['transaction']
        if transaction['organization_id'] != current_user_organization_id:
            raise UnauthorizedException('Access denied: Transaction belongs to different organization')

        # Update transaction
        result = transaction_service.update_transaction(
            transaction_id,
            data,
            int(current_user_id)
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'transaction': result['transaction']
            }
        else:
            raise ValidationException(result['message'])

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException, ValidationException, BadRequestException)):
            raise
        raise APIException(f'Failed to update transaction: {str(e)}')


def handle_delete_transaction(
    transaction_service: TransactionService,
    transaction_id: int,
    soft_delete: bool,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle DELETE /api/transactions/{id} - Delete transaction
    """
    try:
        # First, check if transaction exists and user has access
        existing_result = transaction_service.get_transaction(transaction_id)
        if not existing_result['success']:
            raise NotFoundException('Transaction not found')

        transaction = existing_result['transaction']
        if transaction['organization_id'] != current_user_organization_id:
            raise UnauthorizedException('Access denied: Transaction belongs to different organization')

        # Delete transaction
        result = transaction_service.delete_transaction(transaction_id, soft_delete)

        if result['success']:
            return {
                'success': True,
                'message': result['message']
            }
        else:
            raise APIException(result['message'])

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException, APIException)):
            raise
        raise APIException(f'Failed to delete transaction: {str(e)}')


def handle_upload_transaction_images(
    transaction_service: TransactionService,
    transaction_id: int,
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions/{id}/images - Upload images for transaction
    """
    try:
        # Validate request data
        if not data or not data.get('files'):
            raise BadRequestException('Files are required')

        # First, check if transaction exists and user has access
        existing_result = transaction_service.get_transaction(transaction_id)
        if not existing_result['success']:
            raise NotFoundException('Transaction not found')

        transaction = existing_result['transaction']
        if transaction['organization_id'] != current_user_organization_id:
            raise UnauthorizedException('Access denied: Transaction belongs to different organization')

        # Import S3 service for direct upload
        from ...file_upload_service import S3FileUploadService

        # Upload files directly to S3
        s3_service = S3FileUploadService()
        uploaded_files = s3_service.upload_transaction_files(
            files=data['files'],
            transaction_record_id=transaction_id,
            upload_type='transaction'
        )

        if uploaded_files:
            # Update transaction's images JSONB field
            try:
                # Get transaction object
                from ....models.transactions.transactions import Transaction
                transaction_obj = transaction_service.db.query(Transaction).filter(
                    Transaction.id == transaction_id
                ).first()

                if transaction_obj:
                    # Update JSONB field with new image URLs
                    existing_images = transaction_obj.images or []
                    new_image_urls = [file_info['s3_url'] for file_info in uploaded_files]
                    transaction_obj.images = existing_images + new_image_urls
                    transaction_service.db.commit()

            except Exception as e:
                logger.error(f"Error updating transaction images JSONB field: {str(e)}")

            return {
                'success': True,
                'message': f'Successfully uploaded {len(uploaded_files)} files',
                'images': [{'image_url': file_info['s3_url'], 'filename': file_info['original_filename']} for file_info in uploaded_files]
            }
        else:
            raise APIException('Failed to upload files to S3')

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException, BadRequestException, APIException)):
            raise
        raise APIException(f'Failed to upload images: {str(e)}')


def handle_get_presigned_urls(
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions/presigneds - Get presigned URLs for file uploads
    """
    try:
        # Validate request data
        if not data or not data.get('file_names'):
            raise BadRequestException('file_names is required')

        file_names = data.get('file_names', [])
        if not isinstance(file_names, list) or not file_names:
            raise BadRequestException('file_names must be a non-empty list')

        # Validate file names
        for file_name in file_names:
            if not isinstance(file_name, str) or not file_name.strip():
                raise BadRequestException('All file names must be non-empty strings')

        # Create presigned URL service
        presigned_service = TransactionPresignedUrlService()

        # Generate presigned URLs
        result = presigned_service.get_transaction_file_upload_presigned_urls(
            file_names=file_names,
            organization_id=current_user_organization_id,
            user_id=int(current_user_id),
            expiration_seconds=data.get('expiration_seconds', 3600)
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'presigned_urls': result['presigned_urls'],
                'expires_in_seconds': result.get('expires_in_seconds', 3600)
            }
        else:
            raise APIException(result['message'])

    except Exception as e:
        if isinstance(e, (BadRequestException, APIException)):
            raise
        logger.error(f"Error generating presigned URLs: {str(e)}")
        raise APIException(f'Failed to generate presigned URLs: {str(e)}')


def handle_get_view_presigned_urls(
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions/get_view_presigned - Get presigned URLs for viewing files
    """
    try:
        # Validate request data
        if not data or not data.get('file_urls'):
            raise BadRequestException('file_urls is required')

        file_urls = data.get('file_urls', [])
        if not isinstance(file_urls, list) or not file_urls:
            raise BadRequestException('file_urls must be a non-empty list')

        # Validate file URLs
        for file_url in file_urls:
            if not isinstance(file_url, str) or not file_url.strip():
                raise BadRequestException('All file URLs must be non-empty strings')

        # Create presigned URL service
        presigned_service = TransactionPresignedUrlService()

        # Generate view presigned URLs
        result = presigned_service.get_transaction_file_view_presigned_urls(
            file_urls=file_urls,
            organization_id=current_user_organization_id,
            user_id=int(current_user_id),
            expiration_seconds=data.get('expiration_seconds', 3600)
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'presigned_urls': result['presigned_urls'],
                'expires_in_seconds': result.get('expires_in_seconds', 3600)
            }
        else:
            raise APIException(result['message'])

    except Exception as e:
        if isinstance(e, (BadRequestException, APIException)):
            raise
        logger.error(f"Error generating view presigned URLs: {str(e)}")
        raise APIException(f'Failed to generate view presigned URLs: {str(e)}')


# ========== HELPER FUNCTIONS ==========

def _extract_transaction_id_from_path(path: str) -> int:
    """
    Extract transaction ID from URL path
    Expected format: /api/transactions/{id} or /api/transactions/{id}/...
    """
    try:
        # Split path and find the part after 'transactions'
        path_parts = path.split('/')
        transactions_index = path_parts.index('transactions')
        transaction_id = path_parts[transactions_index + 1]
        return int(transaction_id)
    except (ValueError, IndexError):
        raise BadRequestException('Invalid transaction ID in URL path')


