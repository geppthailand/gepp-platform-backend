"""
Example usage of Transaction Service
Demonstrates how to use the transaction service for CRUD operations
"""

from datetime import datetime
from sqlalchemy.orm import Session

from .transaction_service import TransactionService
from .dto.transaction_requests import CreateTransactionRequest, CreateTransactionRecordRequest, UpdateTransactionRequest
from .dto.transaction_responses import TransactionResponse, TransactionListResponse


def example_create_transaction_with_records(db_session: Session):
    """
    Example: Create a transaction with multiple transaction records
    This demonstrates the typical workflow for creating a new waste transaction
    """

    # Initialize the service
    transaction_service = TransactionService(db_session)

    # Create transaction records (materials being transported)
    record_1 = CreateTransactionRecordRequest(
        main_material_id=1,  # PET Plastic
        category_id=1,       # Recyclable Materials
        unit="kg",
        origin_quantity=100.0,
        origin_weight_kg=100.0,
        origin_price_per_unit=2.5,
        transaction_type="manual_input",
        tags=[[1, 2], [3, 5]],  # [(group_id, tag_id)] - e.g., color=red, quality=good
        notes="Good quality PET bottles, sorted and cleaned",
        hazardous_level=0
    )

    record_2 = CreateTransactionRecordRequest(
        main_material_id=2,  # HDPE Plastic
        category_id=1,       # Recyclable Materials
        unit="kg",
        origin_quantity=75.0,
        origin_weight_kg=75.0,
        origin_price_per_unit=1.8,
        transaction_type="manual_input",
        tags=[[1, 3], [3, 4]],  # [(group_id, tag_id)] - e.g., color=blue, quality=fair
        notes="Mixed HDPE containers, need additional sorting",
        hazardous_level=0
    )

    # Create main transaction
    transaction_request = CreateTransactionRequest(
        origin_id=123,           # Source location
        destination_id=456,      # Destination location
        transaction_method="transport",
        status="draft",
        transaction_date=datetime.now(),
        notes="Weekly pickup from Collection Center A to Sorting Facility B",
        vehicle_info={
            "license_plate": "ABC-123",
            "type": "truck",
            "capacity_kg": 5000,
            "driver_name": "John Smith"
        },
        hazardous_level=0,
        transaction_records=[record_1, record_2]
    )

    # Convert to dict for service call
    transaction_data = transaction_request.to_dict()
    records_data = [record.to_dict() for record in transaction_request.transaction_records]

    # Call service to create transaction
    result = transaction_service.create_transaction(
        transaction_data,
        records_data
    )

    if result['success']:
        print(f"✅ Transaction created successfully!")
        print(f"   Transaction ID: {result['transaction']['id']}")
        print(f"   Status: {result['transaction']['status']}")
        print(f"   Total Weight: {result['transaction']['weight_kg']} kg")
        print(f"   Total Amount: ${result['transaction']['total_amount']}")
        print(f"   Number of Records: {result['transaction_records_count']}")
        return result['transaction']['id']
    else:
        print(f"❌ Failed to create transaction: {result['message']}")
        print(f"   Errors: {result.get('errors', [])}")
        return None


def example_get_transaction_with_records(db_session: Session, transaction_id: int):
    """
    Example: Retrieve a transaction with its associated records
    """

    transaction_service = TransactionService(db_session)

    # Get transaction with records
    result = transaction_service.get_transaction(
        transaction_id=transaction_id,
        include_records=True
    )

    if result['success']:
        transaction = result['transaction']
        print(f"✅ Transaction retrieved successfully!")
        print(f"   ID: {transaction['id']}")
        print(f"   Status: {transaction['status']}")
        print(f"   Method: {transaction['transaction_method']}")
        print(f"   Origin ID: {transaction['origin_id']}")
        print(f"   Destination ID: {transaction['destination_id']}")
        print(f"   Total Weight: {transaction['weight_kg']} kg")
        print(f"   Total Amount: ${transaction['total_amount']}")

        # Display records if included
        if 'records' in transaction:
            print(f"   Records ({len(transaction['records'])}):")
            for i, record in enumerate(transaction['records'], 1):
                print(f"     {i}. Material ID: {record['main_material_id']}")
                print(f"        Quantity: {record['origin_quantity']} {record['unit']}")
                print(f"        Weight: {record['origin_weight_kg']} kg")
                print(f"        Amount: ${record['total_amount']}")

        return TransactionResponse.from_dict(transaction)
    else:
        print(f"❌ Failed to retrieve transaction: {result['message']}")
        return None


def example_list_transactions_with_filtering(db_session: Session, organization_id: int):
    """
    Example: List transactions with filtering and pagination
    """

    transaction_service = TransactionService(db_session)

    # List transactions with filters
    result = transaction_service.list_transactions(
        organization_id=organization_id,
        status="draft",                    # Filter by status
        page=1,
        page_size=10,
        include_records=False              # Don't include records for list view
    )

    if result['success']:
        print(f"✅ Found {result['pagination']['total']} transactions")
        print(f"   Showing page {result['pagination']['page']} of {result['pagination']['pages']}")
        print(f"   Transactions on this page: {len(result['transactions'])}")

        for transaction in result['transactions']:
            print(f"   - ID: {transaction['id']}, Status: {transaction['status']}, "
                  f"Weight: {transaction['weight_kg']} kg, Amount: ${transaction['total_amount']}")

        return TransactionListResponse.from_service_response(result)
    else:
        print(f"❌ Failed to list transactions: {result['message']}")
        return None


def example_update_transaction_status(db_session: Session, transaction_id: int):
    """
    Example: Update transaction status and add vehicle information
    """

    transaction_service = TransactionService(db_session)

    # Create update request
    update_request = UpdateTransactionRequest(
        status="in_progress",
        vehicle_info={
            "license_plate": "XYZ-789",
            "type": "truck",
            "capacity_kg": 8000,
            "driver_name": "Jane Doe",
            "departure_time": datetime.now().isoformat()
        },
        notes="Pickup completed, vehicle en route to destination"
    )

    # Update transaction
    result = transaction_service.update_transaction(
        transaction_id=transaction_id,
        update_data=update_request.to_dict(),
        updated_by_id=100  # User ID making the update
    )

    if result['success']:
        transaction = result['transaction']
        print(f"✅ Transaction updated successfully!")
        print(f"   ID: {transaction['id']}")
        print(f"   New Status: {transaction['status']}")
        print(f"   Updated: {transaction['updated_date']}")
        return TransactionResponse.from_dict(transaction)
    else:
        print(f"❌ Failed to update transaction: {result['message']}")
        print(f"   Errors: {result.get('errors', [])}")
        return None


def example_delete_transaction(db_session: Session, transaction_id: int, soft_delete: bool = True):
    """
    Example: Delete a transaction (soft delete by default)
    """

    transaction_service = TransactionService(db_session)

    # Delete transaction
    result = transaction_service.delete_transaction(
        transaction_id=transaction_id,
        soft_delete=soft_delete
    )

    if result['success']:
        print(f"✅ Transaction {'soft deleted' if soft_delete else 'deleted'} successfully!")
        print(f"   Message: {result['message']}")
        return True
    else:
        print(f"❌ Failed to delete transaction: {result['message']}")
        print(f"   Errors: {result.get('errors', [])}")
        return False


def example_complete_workflow(db_session: Session):
    """
    Example: Complete workflow from creation to completion
    Demonstrates the full lifecycle of a waste transaction
    """

    print("🚛 Starting Complete Transaction Workflow Example")
    print("=" * 60)

    # Step 1: Create transaction
    print("\n📝 Step 1: Creating transaction with records...")
    transaction_id = example_create_transaction_with_records(db_session)

    if not transaction_id:
        print("❌ Workflow stopped - failed to create transaction")
        return

    # Step 2: Retrieve transaction to verify
    print(f"\n🔍 Step 2: Retrieving transaction {transaction_id}...")
    transaction = example_get_transaction_with_records(db_session, transaction_id)

    if not transaction:
        print("❌ Workflow stopped - failed to retrieve transaction")
        return

    # Step 3: Update transaction status to scheduled
    print(f"\n📅 Step 3: Scheduling transaction...")
    update_data = {"status": "scheduled", "notes": "Pickup scheduled for tomorrow 9:00 AM"}
    transaction_service = TransactionService(db_session)
    result = transaction_service.update_transaction(transaction_id, update_data, 100)

    if result['success']:
        print(f"✅ Transaction scheduled successfully")
    else:
        print(f"❌ Failed to schedule transaction: {result['message']}")

    # Step 4: Update to in_progress
    print(f"\n🚚 Step 4: Starting pickup...")
    updated_transaction = example_update_transaction_status(db_session, transaction_id)

    if not updated_transaction:
        print("❌ Workflow stopped - failed to update status")
        return

    # Step 5: List transactions to show current state
    print(f"\n📋 Step 5: Listing all transactions...")
    organization_id = transaction.organization_id
    transactions_list = example_list_transactions_with_filtering(db_session, organization_id)

    # Step 6: Mark as completed
    print(f"\n✅ Step 6: Completing transaction...")
    completion_data = {
        "status": "completed",
        "notes": "Delivery completed successfully, all materials verified"
    }
    result = transaction_service.update_transaction(transaction_id, completion_data, 100)

    if result['success']:
        print(f"✅ Transaction completed successfully")
        print(f"   Final Status: {result['transaction']['status']}")
    else:
        print(f"❌ Failed to complete transaction: {result['message']}")

    print("\n🎉 Complete Transaction Workflow Example Finished!")
    print("=" * 60)

    return transaction_id


if __name__ == "__main__":
    # Example usage - replace with actual database session
    print("This is an example module - import these functions to use with a real database session")
    print("\nAvailable examples:")
    print("- example_create_transaction_with_records()")
    print("- example_get_transaction_with_records()")
    print("- example_list_transactions_with_filtering()")
    print("- example_update_transaction_status()")
    print("- example_delete_transaction()")
    print("- example_complete_workflow()")