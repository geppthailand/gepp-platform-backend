"""
BMA Integration Service - Business logic for BMA transaction integration
Handles transaction creation/updates from BMA system
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from dateutil.parser import parse as parse_date
import logging

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.subscriptions.organizations import Organization
from ....models.subscriptions.subscription_models import Subscription
from ....exceptions import BadRequestException, ValidationException

logger = logging.getLogger(__name__)

# Material mapping configuration
BMA_MATERIAL_MAPPING = {
    "general": {
        "material_id": 94,
        "main_material_id": 11,
        "category_id": 4,
        "type": "general"
    },
    "organic": {
        "material_id": 77,
        "main_material_id": 10,
        "category_id": 3,
        "type": "organic"
    },
    "recyclable": {
        "material_id": 298,
        "main_material_id": 33,
        "category_id": 1,
        "type": "recyclable"
    },
    "hazardous": {
        "material_id": 113,
        "main_material_id": 25,
        "category_id": 5,
        "type": "hazardous"
    }
}


class BMAIntegrationService:
    """
    Service for handling BMA transaction integration
    """

    def __init__(self, db: Session):
        self.db = db

    def process_bma_transaction_batch(
        self,
        batch_data: Dict[str, Any],
        organization_id: int
    ) -> Dict[str, Any]:
        """
        Process BMA transaction batch data

        Expected format:
        {
            "batch": {
                "<transaction_version>": {
                    "<origin_id>": {
                        "<house_id>": {
                            "timestamp": "datestring_with_timezone",
                            "material": {
                                "<mat_type>": {
                                    "image_url": "<url>"
                                }
                            }
                        }
                    }
                }
            }
        }

        Args:
            batch_data: BMA batch data
            organization_id: Organization ID for the transactions

        Returns:
            Dict with processing results
        """
        try:
            if 'batch' not in batch_data:
                raise BadRequestException('Missing "batch" field in request')

            # Get organization owner_id to use as created_by_id
            organization = self.db.query(Organization).filter(
                Organization.id == organization_id,
                Organization.is_active == True
            ).first()

            if not organization:
                raise BadRequestException(f'Organization {organization_id} not found')

            if not organization.owner_id:
                raise BadRequestException(f'Organization {organization_id} does not have an owner')

            organization_owner_id = organization.owner_id

            # Check subscription limits
            subscription = self.db.query(Subscription).filter(
                Subscription.organization_id == organization_id,
                Subscription.is_active == True
            ).first()

            if not subscription:
                raise BadRequestException(f'No active subscription found for organization {organization_id}')

            # Check if user has reached transaction creation limit
            if subscription.create_transaction_usage >= subscription.create_transaction_limit:
                raise BadRequestException(
                    f'Transaction creation limit reached. Usage: {subscription.create_transaction_usage}/{subscription.create_transaction_limit}'
                )

            batch = batch_data['batch']
            results = {
                'processed': 0,
                'created': 0,
                'updated': 0,
                'errors': [],
                'transactions_created_count': 0  # Track new transactions for usage increment
            }

            # Iterate through transaction versions
            for transaction_version, origins in batch.items():
                # Iterate through origin IDs
                for origin_id_str, houses in origins.items():
                    # Validate origin_id is 2170
                    try:
                        origin_id = int(origin_id_str)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid origin_id format: {origin_id_str}")
                        results['errors'].append({
                            'transaction_version': transaction_version,
                            'origin_id': origin_id_str,
                            'error': 'Invalid origin_id format. Must be an integer.'
                        })
                        continue

                    if origin_id != 2170:
                        logger.error(f"Invalid origin_id: {origin_id}. Only 2170 is allowed.")
                        results['errors'].append({
                            'transaction_version': transaction_version,
                            'origin_id': origin_id,
                            'error': 'Invalid origin_id. Only origin_id 2170 is allowed for BMA integration.'
                        })
                        continue

                    # Iterate through house IDs
                    for house_id, house_data in houses.items():
                        try:
                            result = self._process_house_transaction(
                                transaction_version=transaction_version,
                                origin_id=origin_id,
                                house_id=house_id,
                                house_data=house_data,
                                organization_id=organization_id,
                                created_by_id=organization_owner_id
                            )

                            results['processed'] += 1
                            if result['action'] == 'created':
                                results['created'] += 1
                                results['transactions_created_count'] += 1
                            elif result['action'] == 'updated':
                                results['updated'] += 1

                        except Exception as e:
                            logger.error(f"Error processing house {house_id}: {str(e)}")
                            results['errors'].append({
                                'transaction_version': transaction_version,
                                'origin_id': origin_id,
                                'house_id': house_id,
                                'error': str(e)
                            })

            # Increment subscription usage by the number of NEW transactions created
            if results['transactions_created_count'] > 0:
                subscription.create_transaction_usage += results['transactions_created_count']

            self.db.commit()

            # Remove internal tracking field from results before returning
            results.pop('transactions_created_count', 0)

            return {
                'success': True,
                'message': f"Processed {results['processed']} transactions",
                'results': results,
                'subscription_usage': {
                    'create_transaction_limit': subscription.create_transaction_limit,
                    'create_transaction_usage': subscription.create_transaction_usage,
                    'ai_audit_limit': subscription.ai_audit_limit,
                    'ai_audit_usage': subscription.ai_audit_usage
                }
            }

        except BadRequestException:
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error processing BMA batch: {str(e)}")
            raise ValidationException(f"Database error: {str(e)}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Unexpected error processing BMA batch: {str(e)}")
            raise

    def _process_house_transaction(
        self,
        transaction_version: str,
        origin_id: int,
        house_id: str,
        house_data: Dict[str, Any],
        organization_id: int,
        created_by_id: int
    ) -> Dict[str, Any]:
        """
        Process a single house transaction

        Args:
            transaction_version: Transaction version (ext_id_1)
            origin_id: Origin location ID (must be 2170)
            house_id: House ID (ext_id_2)
            house_data: House transaction data
            organization_id: Organization ID

        Returns:
            Dict with action taken ('created' or 'updated')
        """
        # Parse timestamp
        try:
            transaction_date = parse_date(house_data['timestamp'])
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{house_data['timestamp']}': {str(e)}")
            transaction_date = datetime.now()

        # Find existing transaction with matching ext_id_1 and ext_id_2
        existing_transaction = self.db.query(Transaction).filter(
            Transaction.ext_id_1 == transaction_version,
            Transaction.ext_id_2 == house_id,
            Transaction.organization_id == organization_id,
            Transaction.is_active == True
        ).first()

        materials_data = house_data.get('material', {})

        if existing_transaction:
            # Update existing transaction
            return self._update_transaction_with_materials(
                transaction=existing_transaction,
                origin_id=origin_id,
                materials_data=materials_data,
                transaction_date=transaction_date,
                created_by_id=created_by_id
            )
        else:
            # Create new transaction
            return self._create_transaction_with_materials(
                transaction_version=transaction_version,
                origin_id=origin_id,
                house_id=house_id,
                materials_data=materials_data,
                transaction_date=transaction_date,
                organization_id=organization_id,
                created_by_id=created_by_id
            )

    def _create_transaction_with_materials(
        self,
        transaction_version: str,
        origin_id: int,
        house_id: str,
        materials_data: Dict[str, Any],
        transaction_date: datetime,
        organization_id: int,
        created_by_id: int
    ) -> Dict[str, Any]:
        """
        Create a new transaction with material records
        """
        # Create transaction
        transaction = Transaction(
            ext_id_1=transaction_version,
            ext_id_2=house_id,
            organization_id=organization_id,
            origin_id=origin_id,  # Set origin location ID (2170)
            transaction_date=transaction_date,
            transaction_method='origin',
            status=TransactionStatus.pending,
            weight_kg=0,
            total_amount=0,
            images=[],
            created_by_id=created_by_id  # Set to organization owner
        )

        self.db.add(transaction)
        self.db.flush()  # Get transaction ID

        # Create transaction records for each material
        transaction_record_ids = []
        all_images = []
        for material_type, material_info in materials_data.items():
            if material_type in BMA_MATERIAL_MAPPING:
                record = self._create_material_record(
                    transaction_id=transaction.id,
                    material_type=material_type,
                    material_info=material_info,
                    transaction_date=transaction_date,
                    created_by_id=created_by_id
                )
                if record:
                    transaction_record_ids.append(record.id)
                    # Collect images from record
                    if record.images:
                        all_images.extend(record.images)

        # Update transaction with record IDs and collected images
        transaction.transaction_records = transaction_record_ids
        transaction.images = all_images

        logger.info(f"Created transaction {transaction.id} with {len(transaction_record_ids)} records and {len(all_images)} images")

        return {
            'action': 'created',
            'transaction_id': transaction.id,
            'records_created': len(transaction_record_ids)
        }

    def _update_transaction_with_materials(
        self,
        transaction: Transaction,
        origin_id: int,
        materials_data: Dict[str, Any],
        transaction_date: datetime,
        created_by_id: int
    ) -> Dict[str, Any]:
        """
        Update an existing transaction with new material data
        """
        # Update transaction date and origin_id
        transaction.transaction_date = transaction_date
        transaction.origin_id = origin_id

        # Get existing transaction records by querying created_transaction_id
        existing_records = self.db.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == transaction.id,
            TransactionRecord.is_active == True
        ).all()

        # Create a map of material_id to record
        existing_records_map = {
            record.material_id: record for record in existing_records
        }

        records_updated = 0
        records_created = 0

        # Process each material
        for material_type, material_info in materials_data.items():
            if material_type not in BMA_MATERIAL_MAPPING:
                continue

            material_config = BMA_MATERIAL_MAPPING[material_type]
            material_id = material_config['material_id']
            image_url = material_info.get('image_url')

            if material_id in existing_records_map:
                # Update existing record
                record = existing_records_map[material_id]

                # Update transaction date
                record.transaction_date = transaction_date

                # Update image URL if provided - replace with new data
                if image_url:
                    record.images = [image_url]

                records_updated += 1
            else:
                # Create new record
                record = self._create_material_record(
                    transaction_id=transaction.id,
                    material_type=material_type,
                    material_info=material_info,
                    transaction_date=transaction_date,
                    created_by_id=created_by_id
                )
                if record:
                    # Add to transaction records array
                    current_records = transaction.transaction_records or []
                    if record.id not in current_records:
                        current_records.append(record.id)
                        transaction.transaction_records = current_records
                    records_created += 1

        # Collect all images from all transaction records and update transaction.images
        # This ensures images are visible in transaction list
        all_records = self.db.query(TransactionRecord).filter(
            TransactionRecord.created_transaction_id == transaction.id,
            TransactionRecord.is_active == True
        ).all()

        all_images = []
        for record in all_records:
            if record.images:
                all_images.extend(record.images)

        transaction.images = all_images

        logger.info(f"Updated transaction {transaction.id}: {records_updated} records updated, {records_created} records created, {len(all_images)} total images collected")

        return {
            'action': 'updated',
            'transaction_id': transaction.id,
            'records_updated': records_updated,
            'records_created': records_created
        }

    def _create_material_record(
        self,
        transaction_id: int,
        material_type: str,
        material_info: Dict[str, Any],
        transaction_date: datetime,
        created_by_id: int
    ) -> Optional[TransactionRecord]:
        """
        Create a transaction record for a material
        """
        material_config = BMA_MATERIAL_MAPPING[material_type]
        image_url = material_info.get('image_url')

        record = TransactionRecord(
            # Required fields
            created_transaction_id=transaction_id,
            transaction_type='iot',  # BMA integration is considered IoT
            material_id=material_config['material_id'],
            main_material_id=material_config['main_material_id'],
            category_id=material_config['category_id'],
            unit='kg',
            origin_quantity=0,  # BMA doesn't provide quantity
            origin_weight_kg=0,
            origin_price_per_unit=0,
            total_amount=0,
            created_by_id=created_by_id,  # Use organization owner

            # Optional fields
            transaction_date=transaction_date,
            images=[image_url] if image_url else [],
            status='pending',
            tags=[],
            hazardous_level=0
        )

        self.db.add(record)
        self.db.flush()

        logger.info(f"Created transaction record {record.id} for material {material_type}")

        return record

    def get_subscription_usage(self, organization_id: int) -> Dict[str, Any]:
        """
        Get subscription usage information for an organization

        Args:
            organization_id: Organization ID

        Returns:
            Dict with subscription usage information
        """
        try:
            # Get subscription for organization
            subscription = self.db.query(Subscription).filter(
                Subscription.organization_id == organization_id,
                Subscription.is_active == True
            ).first()

            if not subscription:
                raise BadRequestException(f'No active subscription found for organization {organization_id}')

            return {
                'success': True,
                'data': {
                    'subscription_usage': {
                        'create_transaction_limit': subscription.create_transaction_limit,
                        'create_transaction_usage': subscription.create_transaction_usage,
                        'ai_audit_limit': subscription.ai_audit_limit,
                        'ai_audit_usage': subscription.ai_audit_usage
                    }
                }
            }

        except BadRequestException:
            raise
        except Exception as e:
            logger.error(f"Error getting subscription usage: {str(e)}")
            raise ValidationException(f"Failed to get subscription usage: {str(e)}")

    def get_audit_status_summary(self, organization_id: int) -> Dict[str, Any]:
        """
        Get audit status summary for transactions in the past year

        Args:
            organization_id: Organization ID

        Returns:
            Dict with audit status summary
        """
        try:
            from datetime import timedelta
            from sqlalchemy import func

            # Calculate start date (today - 1 year)
            today = datetime.now()
            start_date = today - timedelta(days=365)

            # Query transactions from the past year for this organization
            transactions = self.db.query(Transaction).filter(
                Transaction.organization_id == organization_id,
                Transaction.created_date >= start_date,
                Transaction.deleted_date.is_(None),
                Transaction.is_active == True
            ).all()

            # Count total transactions
            num_transactions = len(transactions)

            # Initialize counters for AI audit status
            ai_audit_counts = {
                'not_audit': 0,
                'queued': 0,
                'approved': 0,
                'rejected': 0
            }

            # Initialize counters for actual status
            actual_status_counts = {
                'pending': 0,
                'rejected': 0,
                'approved': 0
            }

            # Count transactions by status
            for transaction in transactions:
                # Count AI audit status
                ai_status = transaction.ai_audit_status
                if ai_status is None or (hasattr(ai_status, 'value') and ai_status.value == 'null'):
                    ai_audit_counts['not_audit'] += 1
                elif hasattr(ai_status, 'value'):
                    status_value = ai_status.value
                    if status_value in ai_audit_counts:
                        ai_audit_counts[status_value] += 1

                # Count actual status
                actual_status = transaction.status
                if actual_status and hasattr(actual_status, 'value'):
                    status_value = actual_status.value
                    if status_value in actual_status_counts:
                        actual_status_counts[status_value] += 1

            return {
                'success': True,
                'data': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'num_transactions': num_transactions,
                    'ai_audit': ai_audit_counts,
                    'actual_status': actual_status_counts
                }
            }

        except Exception as e:
            logger.error(f"Error getting audit status summary: {str(e)}")
            raise ValidationException(f"Failed to get audit status summary: {str(e)}")

    def add_transactions_to_audit_queue(self, organization_id: int) -> Dict[str, Any]:
        """
        Add all transactions with ai_audit_status = 'null' to the audit queue
        Updates ai_audit_status to 'queued' for all matching transactions

        Args:
            organization_id: Organization ID

        Returns:
            Dict with number of transactions added to queue
        """
        try:
            from sqlalchemy import text

            # Use raw SQL for optimized bulk update
            sql = text("""
                UPDATE transactions
                SET ai_audit_status = 'queued',
                    updated_date = NOW()
                WHERE organization_id = :org_id
                AND ai_audit_status = 'null'
                AND deleted_date IS NULL
                AND is_active = true
                RETURNING id
            """)

            # Execute the update and get the count of updated rows
            result = self.db.execute(sql, {'org_id': organization_id})
            updated_ids = [row[0] for row in result]
            updated_count = len(updated_ids)

            # Commit the changes
            self.db.commit()

            logger.info(f"Added {updated_count} transactions to audit queue for organization {organization_id}")

            return {
                'success': True,
                'data': {
                    'transactions_queued': updated_count,
                    'message': f"Successfully added {updated_count} transactions to audit queue"
                }
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding transactions to audit queue: {str(e)}")
            raise ValidationException(f"Failed to add transactions to audit queue: {str(e)}")
