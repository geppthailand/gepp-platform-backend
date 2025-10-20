"""
Transaction Audit API handlers for AI-based audit operations
"""

from typing import Dict, Any
import logging
import traceback
import os
from sqlalchemy import and_, desc

from .transaction_audit_service import TransactionAuditService
from ....models.logs.transaction_audit_history import TransactionAuditHistory
from ....models.transactions.transactions import Transaction, TransactionStatus, AIAuditStatus

logger = logging.getLogger(__name__)
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_transaction_audit_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for transaction audit routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    # Get Gemini API key from environment
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise APIException('Gemini API key not configured')

    transaction_audit_service = TransactionAuditService(gemini_api_key)

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')

    try:
        # Route to specific handlers
        if path == '/api/transaction_audit/sync_ai_audit' and method == 'POST':
            return handle_sync_ai_audit(
                transaction_audit_service,
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path == '/api/transaction_audit/audit_history' and method == 'GET':
            return handle_get_audit_history(
                db_session,
                query_params,
                current_user_organization_id
            )

        elif path == '/api/transaction_audit/reset_all' and method == 'POST':
            return handle_reset_all_transactions(
                db_session,
                data,
                current_user_organization_id
            )

        elif path == '/api/transaction_audit/add_ai_audit_queue' and method == 'POST':
            return handle_add_ai_audit_queue(
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path == '/api/transaction_audit/process_queue' and method == 'POST':
            return handle_process_audit_queue(db_session)

        elif path == '/api/transaction_audit/audit_report' and method == 'GET':
            return handle_get_audit_report(
                db_session,
                query_params,
                current_user_organization_id
            )

        else:
            # Route not found
            raise NotFoundException(f'Transaction audit route not found: {method} {path}')

    except APIException:
        # Re-raise API exceptions as-is
        raise
    except ValidationException:
        # Re-raise validation exceptions as-is
        raise
    except Exception as e:
        # Log unexpected errors and return generic API error
        logger.error(f'Unexpected error in transaction audit handler: {str(e)}')
        logger.error(f'Traceback: {traceback.format_exc()}')
        raise APIException(f'Internal server error: {str(e)}')


def handle_sync_ai_audit(
    service: TransactionAuditService,
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/sync_ai_audit - Perform synchronous AI audit

    Expected payload:
    {
        "organization_id": <optional_int>,  # Override for multi-org users
        "filter_options": {                 # Optional filtering
            "date_from": "2025-09-01",
            "date_to": "2025-09-30",
            "transaction_ids": [1, 2, 3]   # Specific transactions to audit
        }
    }
    """
    try:
        logger.info(f"AI audit request from user {current_user_id} for organization {organization_id}")

        # Parse request data
        request_org_id = data.get('organization_id', organization_id)
        filter_options = data.get('filter_options', {})

        # Authorization check - ensure user can audit for the requested organization
        if request_org_id != organization_id and organization_id is not None:
            raise UnauthorizedException('You can only audit transactions for your own organization')

        # Perform synchronous AI audit
        audit_result = service.sync_ai_audit(
            db=db_session,
            organization_id=request_org_id
        )

        # Log audit activity
        logger.info(f"AI audit completed for organization {request_org_id}. "
                   f"Processed: {audit_result.get('processed_transactions', 0)} transactions")

        return {
            'success': audit_result['success'],
            'message': audit_result.get('message', 'AI audit completed'),
            'data': {
                'total_transactions': audit_result.get('total_transactions', 0),
                'processed_transactions': audit_result.get('processed_transactions', 0),
                'updated_transactions': audit_result.get('updated_transactions', 0),
                'audit_results': audit_result.get('audit_results', []),
                'organization_id': request_org_id,
                'audited_by_user_id': current_user_id
            },
            'error': audit_result.get('error') if not audit_result['success'] else None
        }

    except ValidationException as e:
        logger.warning(f"Validation error in AI audit: {str(e)}")
        return {
            'success': False,
            'message': 'Validation error',
            'error': str(e),
            'data': None
        }

    except UnauthorizedException as e:
        logger.warning(f"Authorization error in AI audit: {str(e)}")
        raise  # Re-raise authorization errors

    except Exception as e:
        logger.error(f"Error in AI audit handler: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': 'AI audit failed',
            'error': f'Internal server error: {str(e)}',
            'data': {
                'total_transactions': 0,
                'processed_transactions': 0,
                'updated_transactions': 0,
                'audit_results': [],
                'organization_id': organization_id,
                'audited_by_user_id': current_user_id
            }
        }


def handle_get_audit_history(
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transaction_audit/audit_history - Get audit history for organization

    Query parameters:
    - page: int (default: 1)
    - page_size: int (default: 20)
    - status: str (optional filter by status)
    """
    try:
        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('page_size', 20))
        status_filter = query_params.get('status')

        logger.info(f"Fetching audit history for organization {organization_id}")

        # Build query
        query = db_session.query(TransactionAuditHistory).filter(
            and_(
                TransactionAuditHistory.organization_id == organization_id,
                TransactionAuditHistory.deleted_date.is_(None)
            )
        )

        # Apply status filter if provided
        if status_filter:
            query = query.filter(TransactionAuditHistory.status == status_filter)

        # Order by most recent first
        query = query.order_by(desc(TransactionAuditHistory.created_date))

        # Get total count
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        audit_histories = query.offset(offset).limit(page_size).all()

        # Serialize results
        history_data = [history.to_dict() for history in audit_histories]

        return {
            'success': True,
            'data': history_data,
            'meta': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_more': offset + page_size < total_count
            }
        }

    except Exception as e:
        logger.error(f"Error fetching audit history: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to fetch audit history: {str(e)}')


def handle_reset_all_transactions(
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/reset_all - Reset all transactions to pending status

    Resets all transactions back to pending status and ai_audit_status to null for the organization
    """
    try:
        logger.info(f"Resetting all transactions for organization {organization_id}")

        # Query ALL transactions for the organization (not just non-pending ones)
        all_transactions = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None)
            )
        ).all()

        updated_count = 0

        # Reset each transaction
        for transaction in all_transactions:
            # Reset transaction status to pending
            transaction.status = TransactionStatus.pending

            # Reset AI audit status to null
            transaction.ai_audit_status = AIAuditStatus.null
            transaction.ai_audit_note = None
            transaction.reject_triggers = []  # Clear reject triggers
            transaction.warning_triggers = []  # Clear warning triggers

            updated_count += 1

        # Commit changes
        db_session.commit()

        logger.info(f"Reset {updated_count} transactions to pending status with ai_audit_status null")

        return {
            'success': True,
            'message': f'Successfully reset {updated_count} transactions to pending status',
            'data': {
                'updated_count': updated_count,
                'organization_id': organization_id
            }
        }

    except Exception as e:
        db_session.rollback()
        logger.error(f"Error resetting transactions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to reset transactions: {str(e)}')


def handle_add_ai_audit_queue(
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int = None
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/add_ai_audit_queue - Queue transactions for AI audit

    Changes all transactions with ai_audit_status='null' to 'queued' for the organization.
    Creates an audit history record with 'in_progress' status to be processed by cron later.

    Expected payload:
    {
        "transaction_ids": [1, 2, 3]  # Optional: specific transactions to queue
    }
    """
    try:
        logger.info(f"Adding transactions to AI audit queue for organization {organization_id}")

        # Get optional transaction IDs filter
        transaction_ids = data.get('transaction_ids', None)

        # Get Gemini API key from environment
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            raise APIException('Gemini API key not configured')

        # Initialize service
        transaction_audit_service = TransactionAuditService(gemini_api_key)

        # Call service function to queue transactions
        result = transaction_audit_service.add_transaction_to_ai_audit_queue(
            db=db_session,
            organization_id=organization_id,
            user_id=current_user_id,
            transaction_ids=transaction_ids
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'data': {
                    'queued_count': result['queued_count'],
                    'organization_id': result['organization_id'],
                    'audit_history_id': result['audit_history_id'],
                    'transaction_ids': result.get('transaction_ids')
                }
            }
        else:
            return {
                'success': False,
                'message': result.get('message', 'Failed to queue transactions'),
                'error': result.get('error')
            }

    except APIException:
        # Re-raise API exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error queueing transactions for AI audit: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to queue transactions for AI audit: {str(e)}')


def handle_process_audit_queue(db_session: Any) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/process_queue - Process in_progress audit batches

    This endpoint manually triggers the processing of queued audit batches.
    Normally this would be called by a cron job, but can also be triggered manually for testing.

    Returns processing results including number of batches processed.
    """
    try:
        from .cron_process_audit_queue import process_audit_queue

        logger.info("Manual trigger: Processing audit queue")

        result = process_audit_queue(db_session)

        return {
            'success': result.get('success', False),
            'message': result.get('message', 'Queue processing completed'),
            'data': {
                'processed_batches': result.get('processed_batches', 0),
                'failed_batches': result.get('failed_batches', 0),
                'total_batches': result.get('total_batches', 0)
            },
            'error': result.get('error')
        }

    except Exception as e:
        logger.error(f"Error processing audit queue: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to process audit queue: {str(e)}')


def handle_get_audit_report(
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transaction_audit/audit_report - Get comprehensive audit report with filters

    Query parameters:
    - search: str - Partial match search for transaction ID
    - date_from: str (ISO date) - Filter transactions from this date
    - date_to: str (ISO date) - Filter transactions to this date
    - district: str - Filter by district node ID (level 3)
    - sub_district: str - Filter by sub-district node ID (level 4)
    - status: str - Filter by transaction status (not ai_audit_status)
    - page: int - Page number for pagination (default: 1)
    - page_size: int - Items per page (default: 100, max: 100)

    Returns comprehensive report including:
    - Summary statistics (total, approved, rejected counts and percentages) - based on ALL filtered transactions
    - Monthly trend data for charts - based on ALL filtered transactions
    - Rejection reasons breakdown - based on ALL filtered transactions
    - List of transactions with audit details - PAGINATED (100 per page, sorted by id)
    - Pagination metadata (total pages, current page, etc.)
    - Filter options for dropdowns
    """
    try:
        import json
        from datetime import datetime
        from sqlalchemy import func, extract, String
        from collections import Counter
        from ....models.subscriptions.organizations import OrganizationSetup

        logger.info(f"Generating audit report for organization {organization_id} with filters: {query_params}")

        # Log pagination parameters for debugging
        page = int(query_params.get('page', 1))
        page_size = min(int(query_params.get('page_size', 100)), 100)
        logger.info(f"PAGINATION DEBUG: Requested page={page}, page_size={page_size}")

        # Build base query for transactions
        query = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None)
            )
        )

        # Apply filters
        search = query_params.get('search')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        district = query_params.get('district')
        sub_district = query_params.get('sub_district')
        status = query_params.get('status')

        # Ensure page is at least 1
        if page < 1:
            page = 1

        # Search filter - partial match on transaction ID
        if search:
            query = query.filter(Transaction.id.cast(String).contains(search))

        # Date filters
        if date_from:
            query = query.filter(Transaction.transaction_date >= date_from)

        if date_to:
            query = query.filter(Transaction.transaction_date <= date_to)

        # District and sub-district filtering based on organization_setup
        # Skip filtering if district is 'all'
        if (district and district != 'all') or (sub_district and sub_district != 'all'):
            # Get organization setup to access root_nodes
            org_setup = db_session.query(OrganizationSetup).filter(
                and_(
                    OrganizationSetup.organization_id == organization_id,
                    OrganizationSetup.deleted_date.is_(None)
                )
            ).order_by(OrganizationSetup.created_date.desc()).first()

            if org_setup and org_setup.root_nodes:
                allowed_origin_ids = []

                # Convert district and sub_district to int if they're not 'all'
                district_int = int(district) if district and district != 'all' else None
                sub_district_int = int(sub_district) if sub_district and sub_district != 'all' else None

                # Helper function to recursively extract node IDs
                def extract_node_ids(nodes, target_level, current_level=1, parent_match=False):
                    node_ids = []
                    for node in nodes if isinstance(nodes, list) else []:
                        node_id = node.get('nodeId')
                        children = node.get('children', [])

                        # If filtering by district (level 3)
                        if district_int and current_level == 3:
                            if node_id == district_int:
                                # Found matching district, collect this and all children
                                node_ids.append(node_id)
                                node_ids.extend(extract_node_ids(children, target_level, current_level + 1, parent_match=True))
                        # If filtering by sub_district (level 4)
                        elif sub_district_int and current_level == 4:
                            if node_id == sub_district_int:
                                node_ids.append(node_id)
                        # If parent matched and we're collecting all descendants
                        elif parent_match:
                            node_ids.append(node_id)
                            if children:
                                node_ids.extend(extract_node_ids(children, target_level, current_level + 1, parent_match=True))
                        # Otherwise keep traversing
                        elif children:
                            node_ids.extend(extract_node_ids(children, target_level, current_level + 1, parent_match=False))

                    return node_ids

                # Extract allowed origin IDs based on filters
                if sub_district_int:
                    allowed_origin_ids = extract_node_ids(org_setup.root_nodes, 4)
                elif district_int:
                    allowed_origin_ids = extract_node_ids(org_setup.root_nodes, 3)

                # Apply filter if we found matching nodes
                if allowed_origin_ids:
                    query = query.filter(Transaction.origin_id.in_(allowed_origin_ids))
                else:
                    # No matching nodes found, return empty result
                    query = query.filter(Transaction.id == -1)

        # Status filter (transaction status, not ai_audit_status)
        if status:
            query = query.filter(Transaction.status == status)

        # Get all matching transactions for statistics (without pagination)
        all_transactions = query.all()

        # Get total count for pagination
        total_count = len(all_transactions)
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0

        # Get paginated transactions sorted by id
        paginated_query = query.order_by(Transaction.id)
        offset = (page - 1) * page_size
        logger.info(f"PAGINATION DEBUG: Applying offset={offset}, limit={page_size} to query")
        paginated_transactions = paginated_query.offset(offset).limit(page_size).all()
        logger.info(f"PAGINATION DEBUG: Retrieved {len(paginated_transactions)} transactions")

        # Calculate summary statistics (based on ALL filtered transactions)
        total_transactions = len(all_transactions)
        approved_transactions = [t for t in all_transactions if t.ai_audit_status == AIAuditStatus.approved]
        rejected_transactions = [t for t in all_transactions if t.ai_audit_status == AIAuditStatus.rejected]

        approved_count = len(approved_transactions)
        rejected_count = len(rejected_transactions)

        approved_percentage = round((approved_count / total_transactions * 100), 2) if total_transactions > 0 else 0
        rejected_percentage = round((rejected_count / total_transactions * 100), 2) if total_transactions > 0 else 0

        # Monthly trend data (for stacked bar chart)
        # Initialize all months for current year with zero values
        from datetime import datetime
        current_year = datetime.now().year
        monthly_data = {}

        # Initialize all 12 months with zero values
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for i in range(1, 13):
            month_key = f"{current_year}-{i:02d}"
            monthly_data[month_key] = {'approved': 0, 'rejected': 0, 'month_name': month_names[i-1]}

        # Count transactions by month (based on ALL filtered transactions)
        for transaction in all_transactions:
            if transaction.transaction_date:
                month_key = transaction.transaction_date.strftime('%Y-%m')
                # Only count if it's from current year
                if transaction.transaction_date.year == current_year:
                    if month_key in monthly_data:
                        if transaction.ai_audit_status == AIAuditStatus.approved:
                            monthly_data[month_key]['approved'] += 1
                        elif transaction.ai_audit_status == AIAuditStatus.rejected:
                            monthly_data[month_key]['rejected'] += 1

        # Sort by month and format for frontend
        monthly_trends = []
        for month in sorted(monthly_data.keys()):
            monthly_trends.append({
                'month': monthly_data[month]['month_name'],
                'approved': monthly_data[month]['approved'],
                'rejected': monthly_data[month]['rejected']
            })

        # Rejection reasons breakdown (for pie chart)
        # Extract all reject_triggers and count occurrences
        rejection_reasons = []
        for transaction in rejected_transactions:
            if transaction.reject_triggers and isinstance(transaction.reject_triggers, list):
                rejection_reasons.extend(transaction.reject_triggers)

        # Count frequency of each rejection reason
        reason_counts = Counter(rejection_reasons)

        # Fetch rule names from audit_rules table
        from ....models.audit_rules import AuditRule
        rule_ids = list(reason_counts.keys())
        audit_rules = db_session.query(AuditRule).filter(AuditRule.rule_id.in_(rule_ids)).all()
        rule_name_map = {rule.rule_id: rule.rule_name for rule in audit_rules}

        rejection_breakdown = [
            {
                'rule_id': rule_id,
                'rule_name': rule_name_map.get(rule_id, rule_id),  # Fallback to rule_id if name not found
                'count': count
            }
            for rule_id, count in reason_counts.most_common()
        ]

        # Prepare transaction list for รายละเอียดการตรวจสอบ (PAGINATED)
        transaction_list = []
        for transaction in paginated_transactions:
            # Parse ai_audit_note if it's JSON
            audit_details = None
            reject_messages = []

            if transaction.ai_audit_note:
                try:
                    audit_details = json.loads(transaction.ai_audit_note)

                    # Extract reject_messages from compact format
                    if isinstance(audit_details, dict) and 's' in audit_details and 'v' in audit_details:
                        # Compact format: extract messages from violations
                        for violation in audit_details.get('v', []):
                            msg = violation.get('m', '')
                            if msg:
                                reject_messages.append(msg)
                except:
                    audit_details = {'note': transaction.ai_audit_note}

            transaction_list.append({
                'id': transaction.id,
                'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
                'status': transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status),
                'ai_audit_status': transaction.ai_audit_status.value if hasattr(transaction.ai_audit_status, 'value') else None,
                'weight_kg': float(transaction.weight_kg) if transaction.weight_kg else 0,
                'total_amount': float(transaction.total_amount) if transaction.total_amount else 0,
                'reject_triggers': transaction.reject_triggers if transaction.reject_triggers else [],
                'warning_triggers': transaction.warning_triggers if transaction.warning_triggers else [],
                'reject_messages': reject_messages if reject_messages else [],
                'audit_details': audit_details
            })

        # Build filter options for frontend
        # Get organization setup to extract districts and sub-districts
        from ....models.users.user_location import UserLocation

        org_setup = db_session.query(OrganizationSetup).filter(
            and_(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.deleted_date.is_(None)
            )
        ).order_by(OrganizationSetup.created_date.desc()).first()

        districts = []
        sub_districts = []

        if org_setup and org_setup.root_nodes:
            # Collect all district (level 3) and sub-district (level 4) IDs from root_nodes
            # Also maintain the parent-child relationship
            district_ids = []
            district_subdistrict_map = {}  # {district_id: [subdistrict_ids]}

            def extract_location_hierarchy(nodes, current_level=1, parent_district_id=None):
                for node in nodes if isinstance(nodes, list) else []:
                    node_id = node.get('nodeId')
                    children = node.get('children', [])

                    if current_level == 3:  # District level
                        district_ids.append(node_id)
                        district_subdistrict_map[node_id] = []
                        # Recursively process children with this district as parent
                        if children:
                            extract_location_hierarchy(children, current_level + 1, parent_district_id=node_id)
                    elif current_level == 4:  # Sub-district level
                        # Add this sub-district to its parent district's list
                        if parent_district_id and parent_district_id in district_subdistrict_map:
                            district_subdistrict_map[parent_district_id].append(node_id)
                    else:
                        # Continue traversing for other levels
                        if children:
                            extract_location_hierarchy(children, current_level + 1, parent_district_id)

            extract_location_hierarchy(org_setup.root_nodes)

            # Fetch actual district names from user_locations table
            if district_ids:
                district_records = db_session.query(UserLocation).filter(
                    UserLocation.id.in_(district_ids)
                ).all()
                districts = [
                    {'id': str(d.id), 'name': d.name_en or d.name_th or d.display_name or str(d.id)}
                    for d in district_records
                ]

            # Fetch all sub-district IDs
            all_subdistrict_ids = []
            for subdistrict_list in district_subdistrict_map.values():
                all_subdistrict_ids.extend(subdistrict_list)

            # Fetch actual sub-district names from user_locations table
            subdistrict_records_dict = {}
            if all_subdistrict_ids:
                sub_district_records = db_session.query(UserLocation).filter(
                    UserLocation.id.in_(all_subdistrict_ids)
                ).all()
                # Create a dict for quick lookup
                subdistrict_records_dict = {
                    str(sd.id): {'id': str(sd.id), 'name': sd.name_en or sd.name_th or sd.display_name or str(sd.id)}
                    for sd in sub_district_records
                }

            # Build sub_districts structure: {district_id: [subdistrict objects]}
            sub_districts = {}
            for district_id, subdistrict_ids in district_subdistrict_map.items():
                sub_districts[str(district_id)] = [
                    subdistrict_records_dict[str(sd_id)]
                    for sd_id in subdistrict_ids
                    if str(sd_id) in subdistrict_records_dict
                ]

        # Status options
        statuses = [
            {'value': 'pending', 'label': 'รอดำเนินการ'},
            {'value': 'approved', 'label': 'อนุมัติ'},
            {'value': 'rejected', 'label': 'ไม่อนุมัติ'}
        ]

        # Sort districts by name
        districts_sorted = sorted(districts, key=lambda x: x['name'])

        # Add 'all' option to districts at the beginning
        districts_with_all = [{'id': 'all', 'name': 'ทั้งหมด'}] + districts_sorted

        # Sort sub_districts within each district and add 'all' option
        sub_districts_sorted = {}
        for district_id, subdistrict_list in sub_districts.items():
            sorted_list = sorted(subdistrict_list, key=lambda x: x['name'])
            # Add 'all' option for each district's sub-district list
            sub_districts_sorted[district_id] = [{'id': 'all', 'name': 'ทั้งหมด'}] + sorted_list

        filter_options = {
            'districts': districts_with_all,
            'sub_districts': sub_districts_sorted,
            'statuses': statuses
        }

        # Compile final report
        report = {
            'summary': {
                'total_transactions': total_transactions,
                'approved_count': approved_count,
                'rejected_count': rejected_count,
                'approved_percentage': approved_percentage,
                'rejected_percentage': rejected_percentage
            },
            'monthly_trends': monthly_trends,
            'rejection_breakdown': rejection_breakdown,
            'transactions': transaction_list,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'filters_applied': {
                'search': search,
                'date_from': date_from,
                'date_to': date_to,
                'district': district,
                'sub_district': sub_district,
                'status': status
            },
            'filter_options': filter_options
        }

        logger.info(f"Successfully generated audit report with {total_transactions} total transactions (page {page}/{total_pages}, showing {len(transaction_list)} transactions)")

        return {
            'success': True,
            'message': 'Audit report generated successfully',
            'data': report
        }

    except Exception as e:
        logger.error(f"Error generating audit report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to generate audit report: {str(e)}')