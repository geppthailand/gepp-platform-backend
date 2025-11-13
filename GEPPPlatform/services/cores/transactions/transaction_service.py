"""
Transaction Service - Business logic for transaction management
Handles CRUD operations, validation, and transaction record linking
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from decimal import Decimal
import logging

from ....models.transactions.transactions import Transaction, TransactionStatus, TransactionRecordStatus
from ....models.transactions.transaction_records import TransactionRecord
from ...file_upload_service import S3FileUploadService
from ....models.users.user_location import UserLocation
from ....models.subscriptions.organizations import Organization, OrganizationSetup

logger = logging.getLogger(__name__)


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

            # Create transaction
            transaction = Transaction(
                transaction_method=transaction_data.get('transaction_method', 'origin'),
                status=TransactionStatus(transaction_data.get('status', 'pending')),
                organization_id=transaction_data.get('organization_id'),
                origin_id=transaction_data.get('origin_id'),
                destination_id=transaction_data.get('destination_id'),
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
            if transaction_records_data:
                for record_data in transaction_records_data:
                    record_result = self._create_transaction_record(
                        record_data,
                        transaction.id
                    )
                    if record_result['success']:
                        transaction_record_ids.append(record_result['transaction_record'].id)
                    else:
                        # Rollback transaction if any record fails
                        self.db.rollback()
                        return {
                            'success': False,
                            'message': f'Failed to create transaction record: {record_result["message"]}',
                            'errors': record_result.get('errors', [])
                        }

            # Update transaction with record IDs and calculated totals
            transaction.transaction_records = transaction_record_ids
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
            # Eager load location relationships
            transaction = self.db.query(Transaction).options(
                joinedload(Transaction.origin),
                joinedload(Transaction.destination)
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

            if include_records:
                # Get transaction records with eager loading of material and category
                records = self.db.query(TransactionRecord).options(
                    joinedload(TransactionRecord.material),
                    joinedload(TransactionRecord.category)
                ).filter(
                    TransactionRecord.created_transaction_id == transaction_id,
                    TransactionRecord.is_active == True
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
        sub_district: Optional[int] = None
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
            query = self.db.query(Transaction).filter(Transaction.deleted_date.is_(None))

            # Apply filters
            if organization_id:
                query = query.filter(Transaction.organization_id == organization_id)
            if status:
                query = query.filter(Transaction.status == status)
            if origin_id:
                query = query.filter(Transaction.origin_id == origin_id)
            if destination_id:
                query = query.filter(Transaction.destination_id == destination_id)

            # Search filter - search in notes and transaction ID
            if search:
                search_pattern = f'%{search}%'
                query = query.filter(
                    (Transaction.notes.ilike(search_pattern)) |
                    (Transaction.id == int(search) if search.isdigit() else False)
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
                        # Get transaction records
                        records = self.db.query(TransactionRecord).filter(
                            TransactionRecord.created_transaction_id == transaction.id,
                            TransactionRecord.is_active == True
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

            # Update allowed fields
            updatable_fields = [
                'transaction_method', 'status', 'destination_id', 'arrival_date',
                'destination_coordinates', 'notes', 'images', 'vehicle_info',
                'driver_info', 'hazardous_level', 'treatment_method', 'disposal_method'
            ]

            for field in updatable_fields:
                if field in update_data:
                    if field == 'status' and isinstance(update_data[field], str):
                        setattr(transaction, field, TransactionStatus(update_data[field]))
                    else:
                        setattr(transaction, field, update_data[field])

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
                origin_quantity=Decimal(str(record_data.get('origin_quantity', 0))),
                origin_weight_kg=Decimal(str(record_data.get('origin_weight_kg', 0))),
                origin_price_per_unit=Decimal(str(record_data.get('origin_price_per_unit', 0))),
                total_amount=Decimal(str(record_data.get('total_amount', 0))),
                currency_id=record_data.get('currency_id'),
                notes=record_data.get('notes'),
                images=record_data.get('images', []),
                origin_coordinates=record_data.get('origin_coordinates'),
                destination_coordinates=record_data.get('destination_coordinates'),
                hazardous_level=record_data.get('hazardous_level', 0),
                treatment_method=record_data.get('treatment_method'),
                disposal_method=record_data.get('disposal_method'),
                transaction_date=transaction_date,  # Add transaction_date
                created_by_id=record_data.get('created_by_id')
            )

            # Calculate total amount if not provided
            if not transaction_record.total_amount:
                transaction_record.calculate_total_value()

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
        valid_methods = ['origin', 'transport', 'transform']
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

        # Validate destination location exists (if provided)
        if data.get('destination_id'):
            destination = self.db.query(UserLocation).filter(
                UserLocation.id == data['destination_id'],
                UserLocation.is_active == True
            ).first()
            if not destination:
                errors.append('Destination location not found or inactive')

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

            transaction.weight_kg = total_weight
            transaction.total_amount = total_amount

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

        destination_location = None
        if hasattr(transaction, 'destination') and transaction.destination:
            destination_location = {
                'id': transaction.destination.id,
                'name_en': transaction.destination.name_en if hasattr(transaction.destination, 'name_en') else None,
                'name_th': transaction.destination.name_th if hasattr(transaction.destination, 'name_th') else None,
                'display_name': transaction.destination.display_name if hasattr(transaction.destination, 'display_name') else None
            }

        return {
            'id': transaction.id,
            'transaction_records': transaction.transaction_records,
            'transaction_method': transaction.transaction_method,
            'status': transaction.status.value if transaction.status else None,
            'organization_id': transaction.organization_id,
            'origin_id': transaction.origin_id,
            'destination_id': transaction.destination_id,
            'origin_location': origin_location,
            'destination_location': destination_location,
            'weight_kg': float(transaction.weight_kg) if transaction.weight_kg else 0,
            'total_amount': float(transaction.total_amount) if transaction.total_amount else 0,
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
            'origin_quantity': float(record.origin_quantity) if record.origin_quantity else 0,
            'origin_weight_kg': float(record.origin_weight_kg) if record.origin_weight_kg else 0,
            'origin_price_per_unit': float(record.origin_price_per_unit) if record.origin_price_per_unit else 0,
            'total_amount': float(record.total_amount) if record.total_amount else 0,
            'currency_id': record.currency_id,
            'notes': record.notes,
            'images': record.images,
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