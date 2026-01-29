"""
Transaction API handlers for CRUD operations
"""

from typing import Dict, Any
import logging
import traceback

from .transaction_service import TransactionService
from .presigned_url_service import TransactionPresignedUrlService
from GEPPPlatform.services.cores.users.user_service import UserService

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
    user_service = UserService(db_session)

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
                user_service,
                transaction_id,
                include_records,
                current_user_organization_id
            )

        elif '/api/transactions/' in path and '/with-records' in path and method == 'PUT':
            # PUT /api/transactions/{id}/with-records - Update transaction with records
            transaction_id = _extract_transaction_id_from_path(path)
            return handle_update_transaction_with_records(
                transaction_service,
                transaction_id,
                data,
                current_user_id,
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
                current_user_organization_id,
                db_session
            )

        elif path == '/api/transactions/get_view_presigned' and method == 'POST':
            # POST /api/transactions/get_view_presigned - Get presigned URLs for viewing files
            return handle_get_view_presigned_urls(
                data,
                current_user_id,
                current_user_organization_id,
                db_session
            )

        else:
            return {
                'success': False,
                'message': 'Transaction route not found',
                'error_code': 'ROUTE_NOT_FOUND'
            }

    except ValidationException as e:
        response = {
            'success': False,
            'message': str(e),
            'error_code': 'VALIDATION_ERROR'
        }
        if hasattr(e, 'errors') and e.errors:
            response['errors'] = e.errors
        return response
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

        print(transaction_data)
        # Create transaction
        result = transaction_service.create_transaction(
            transaction_data,
            transaction_records_data if transaction_records_data else None
        )

        if result['success']:
            txn = result['transaction']
            transaction_id = txn.get('id')
            organization_id = txn.get('organization_id') or current_user_organization_id
            created_by_id = int(current_user_id)
            if transaction_id and organization_id is not None:
                transaction_service.create_txn_created_notifications(
                    transaction_id=transaction_id,
                    organization_id=organization_id,
                    created_by_id=created_by_id,
                )
            return {
                'success': True,
                'message': result['message'],
                'transaction': result['transaction'],
                'transaction_records_count': result.get('transaction_records_count', 0)
            }
        else:
            raise ValidationException(
                result['message'],
                errors=result.get('errors', [])
            )

    except Exception as e:
        if isinstance(e, (ValidationException, BadRequestException)):
            raise
        raise APIException(f'Failed to create transaction: {str(e)}')


def handle_get_transaction(
    transaction_service: TransactionService,
    user_service: UserService,
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

        # Enrich origin_location with hierarchy path using UserService._build_location_paths
        origin_id = transaction.get('origin_id')
        if origin_id:
            # Build location_data structure expected by _build_location_paths
            location_data_for_paths = [{'id': origin_id}]
            location_paths = user_service._build_location_paths(
                organization_id=current_user_organization_id,
                location_data=location_data_for_paths
            )
            origin_path = location_paths.get(origin_id)

            if origin_path is not None:
                # Ensure origin_location dict exists
                origin_location = transaction.get('origin_location') or {}
                origin_location.setdefault('id', origin_id)
                origin_location['path'] = origin_path
                transaction['origin_location'] = origin_location

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

    Transactions are ordered by ID in descending order (newest first)
    """
    try:
        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = min(int(query_params.get('page_size', 20)), 100)  # Max 100 per page
        status = query_params.get('status')
        origin_id = int(query_params['origin_id']) if query_params.get('origin_id') else None
        destination_id = int(query_params['destination_id']) if query_params.get('destination_id') else None
        include_records = query_params.get('include_records', 'false').lower() == 'true'

        # Additional filter parameters
        search = query_params.get('search')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        district = int(query_params['district']) if query_params.get('district') else None
        sub_district = int(query_params['sub_district']) if query_params.get('sub_district') else None

        # Always filter by user's organization
        result = transaction_service.list_transactions(
            organization_id=current_user_organization_id,
            status=status,
            origin_id=origin_id,
            destination_id=destination_id,
            page=page,
            page_size=page_size,
            include_records=include_records,
            search=search,
            date_from=date_from,
            date_to=date_to,
            district=district,
            sub_district=sub_district
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
            organization_id = transaction.get('organization_id') or current_user_organization_id
            if organization_id is not None:
                transaction_service.create_txn_updated_notifications(
                    transaction_id=transaction_id,
                    organization_id=organization_id,
                    created_by_id=int(current_user_id),
                )
            return {
                'success': True,
                'message': result['message'],
                'transaction': result['transaction']
            }
        else:
            raise ValidationException(
                result['message'],
                errors=result.get('errors', [])
            )

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException, ValidationException, BadRequestException)):
            raise
        raise APIException(f'Failed to update transaction: {str(e)}')


def handle_update_transaction_with_records(
    transaction_service: TransactionService,
    transaction_id: int,
    data: Dict[str, Any],
    current_user_id: str,
    current_user_organization_id: int
) -> Dict[str, Any]:
    """
    Handle PUT /api/transactions/{id}/with-records - Update transaction with records
    Supports adding new records, updating existing records, and soft deleting removed records
    """
    try:
        # Validate request data
        if not data:
            raise BadRequestException('Request body is required')

        # First, check if transaction exists and user has access
        existing_result = transaction_service.get_transaction(transaction_id, include_records=True)
        if not existing_result['success']:
            raise NotFoundException('Transaction not found')

        transaction = existing_result['transaction']
        if transaction['organization_id'] != current_user_organization_id:
            raise UnauthorizedException('Access denied: Transaction belongs to different organization')

        # Update transaction with records
        result = transaction_service.update_transaction_with_records(
            transaction_id,
            data,
            int(current_user_id)
        )

        if result['success']:
            organization_id = transaction.get('organization_id') or current_user_organization_id
            if organization_id is not None:
                transaction_service.create_txn_updated_notifications(
                    transaction_id=transaction_id,
                    organization_id=organization_id,
                    created_by_id=int(current_user_id),
                )
            return {
                'success': True,
                'message': result['message'],
                'transaction': result['transaction'],
                'records_added': result.get('records_added', 0),
                'records_updated': result.get('records_updated', 0),
                'records_deleted': result.get('records_deleted', 0)
            }
        else:
            raise ValidationException(
                result['message'],
                errors=result.get('errors', [])
            )

    except Exception as e:
        if isinstance(e, (NotFoundException, UnauthorizedException, ValidationException, BadRequestException)):
            raise
        raise APIException(f'Failed to update transaction with records: {str(e)}')


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
    current_user_organization_id: int,
    db_session
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions/presigneds - Get presigned URLs for file uploads
    Creates file records in database and returns file IDs with presigned URLs
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

        # Generate presigned URLs with file record creation
        result = presigned_service.get_transaction_file_upload_presigned_urls(
            file_names=file_names,
            organization_id=current_user_organization_id,
            user_id=int(current_user_id),
            db=db_session,
            file_type=data.get('file_type', 'transaction_image'),
            related_entity_type=data.get('related_entity_type'),
            related_entity_id=data.get('related_entity_id'),
            expiration_seconds=data.get('expiration_seconds', 3600)
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'presigned_urls': result['presigned_urls'],
                'file_records': result.get('file_records', []),  # Include file records with IDs
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
    current_user_organization_id: int,
    db_session
) -> Dict[str, Any]:
    """
    Handle POST /api/transactions/get_view_presigned - Get presigned URLs for viewing files
    Accepts either file_ids (preferred) or file_urls (legacy) for backward compatibility

    Note: file_urls parameter now accepts both file IDs (integers) and URLs (strings) for flexibility
    """
    try:
        # Create presigned URL service
        presigned_service = TransactionPresignedUrlService()

        # Check if using file_ids (new approach) or file_urls (legacy)
        if data.get('file_ids'):
            # New approach: Use file IDs
            file_ids = data.get('file_ids', [])
            if not isinstance(file_ids, list) or not file_ids:
                raise BadRequestException('file_ids must be a non-empty list')

            # Validate file IDs
            for file_id in file_ids:
                if not isinstance(file_id, int):
                    raise BadRequestException('All file IDs must be integers')

            # Generate view presigned URLs by file IDs
            result = presigned_service.get_transaction_file_view_presigned_urls_by_ids(
                file_ids=file_ids,
                db=db_session,
                organization_id=current_user_organization_id,
                user_id=int(current_user_id),
                expiration_seconds=data.get('expiration_seconds', 3600)
            )

        elif data.get('file_urls'):
            # Legacy approach: Use file URLs (now supports both IDs and URLs)
            file_urls = data.get('file_urls', [])
            if not isinstance(file_urls, list) or not file_urls:
                raise BadRequestException('file_urls must be a non-empty list')

            # Check if array contains integers (file IDs) or strings (URLs)
            if file_urls and isinstance(file_urls[0], int):
                # Array contains file IDs - convert to file_ids approach
                file_ids = file_urls

                # Validate all items are integers
                for file_id in file_ids:
                    if not isinstance(file_id, int):
                        raise BadRequestException('All items in file_urls must be of the same type (all integers or all strings)')

                # Generate view presigned URLs by file IDs
                result = presigned_service.get_transaction_file_view_presigned_urls_by_ids(
                    file_ids=file_ids,
                    db=db_session,
                    organization_id=current_user_organization_id,
                    user_id=int(current_user_id),
                    expiration_seconds=data.get('expiration_seconds', 3600)
                )
            else:
                # Array contains URL strings - use legacy approach
                # Validate file URLs
                for file_url in file_urls:
                    if not isinstance(file_url, str) or not file_url.strip():
                        raise BadRequestException('All file URLs must be non-empty strings')

                # Generate view presigned URLs by file URLs
                result = presigned_service.get_transaction_file_view_presigned_urls(
                    file_urls=file_urls,
                    organization_id=current_user_organization_id,
                    user_id=int(current_user_id),
                    expiration_seconds=data.get('expiration_seconds', 3600),
                    db=db_session  # Pass db session to check file sources
                )

        else:
            raise BadRequestException('Either file_ids or file_urls is required')

        if result['success']:
            response = {
                'success': True,
                'message': result['message'],
                'presigned_urls': result['presigned_urls'],
                'expires_in_seconds': result.get('expires_in_seconds', 3600)
            }
            # Include errors if any occurred (partial success)
            if result.get('errors'):
                response['errors'] = result['errors']
            return response
        else:
            # Include error details in the exception
            error_message = result.get('message', 'Failed to generate view presigned URLs')
            if result.get('errors'):
                error_message += f"\nErrors: {result['errors']}"
            raise APIException(error_message)

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


