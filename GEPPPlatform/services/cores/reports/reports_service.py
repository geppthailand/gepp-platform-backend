"""
Reports Service - Business logic for reports and analytics
Handles data retrieval and processing for various reports
"""

from typing import List, Optional, Dict, Any
from GEPPPlatform.models.cores.references import Material, MaterialTag
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, and_, func, cast
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timedelta, timezone
import logging

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.subscriptions.subscription_models import OrganizationRole
from ....exceptions import ValidationException, NotFoundException

logger = logging.getLogger(__name__)


class ReportsService:
    """
    High-level reports service with business logic
    """

    def __init__(self, db: Session):
        self.db = db

    # ========== TRANSACTION RECORDS REPORTS ==========

    def get_transaction_records_by_organization(
        self,
        organization_id: int,
        filters: Optional[Dict[str, Any]] = None,
        report_type: str = None,
        current_user_id: Any = None
    ) -> Dict[str, Any]:
        """
        Get all active transaction records for a specific organization.
        If current_user_id is set and user is not admin and has a role, only records from transactions
        where the user is in origin/tag/tenant members.
        """
        try:
            # Print input parameters
            print(
                f"get_transaction_records_by_organization called - "
                f"organization_id: {organization_id}, "
                f"report_type: {report_type}, "
                f"filters: {filters}"
            )
            
            # Base query: Join transaction_records with transactions
            query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
                TransactionRecord.deleted_date.is_(None),
                or_(
                    TransactionRecord.status != 'rejected',
                    TransactionRecord.status.is_(None)
                ),
            )
            # Filter by active organization_setup locations
            query = self._apply_active_setup_filter(query, organization_id)

            # Log member filter: whether it's applied and for which user
            _apply_member = self._should_filter_reports_by_member(current_user_id)
            logger.info(
                f"[REPORTS] get_transaction_records_by_organization member_filter: current_user_id={current_user_id}, "
                f"apply_member_filter={_apply_member}, report_type={report_type}"
            )
            query = self._apply_member_filter_to_transaction_query(query, current_user_id, organization_id)

            # Track applied filters for logging
            applied_filters = {}
            
            # Apply additional filters if provided
            if filters:
                # Filter by material_ids (supports multiple)
                if filters.get('material_ids'):
                    query = query.filter(TransactionRecord.material_id.in_(filters['material_ids']))
                    applied_filters['material_ids'] = filters['material_ids']
                
                # New multi-select location filters (location_ids + descendants, tag/tenant intersect)
                query, new_filters_applied = self._apply_location_filters(query, filters, organization_id)
                if new_filters_applied:
                    if filters.get('location_ids'):
                        applied_filters['location_ids'] = filters['location_ids']
                    if filters.get('filter_tag_ids'):
                        applied_filters['filter_tag_ids'] = filters['filter_tag_ids']
                    if filters.get('filter_tenant_ids'):
                        applied_filters['filter_tenant_ids'] = filters['filter_tenant_ids']

                # Legacy origin_combos / origin_ids filters (when new filters not provided)
                if not new_filters_applied:
                    if filters.get('origin_combos'):
                        combos = filters['origin_combos']
                        origin_only_origin_ids = {oid for (oid, tag_id, tenant_id) in combos if tag_id is None and tenant_id is None}
                        expanded_origin_only = set()
                        for oid in origin_only_origin_ids:
                            expanded_origin_only.update(self._resolve_descendant_ids(organization_id, [oid]))
                        conditions = []
                        if expanded_origin_only:
                            conditions.append(Transaction.origin_id.in_(list(expanded_origin_only)))
                        for oid, tag_id, tenant_id in combos:
                            if oid in origin_only_origin_ids:
                                continue
                            c = (Transaction.origin_id == oid)
                            if tag_id is None:
                                c = and_(c, Transaction.location_tag_id.is_(None))
                            else:
                                c = and_(c, Transaction.location_tag_id == tag_id)
                            if tenant_id is None:
                                c = and_(c, Transaction.tenant_id.is_(None))
                            else:
                                c = and_(c, Transaction.tenant_id == tenant_id)
                            conditions.append(c)
                        if conditions:
                            query = query.filter(or_(*conditions))
                            applied_filters['origin_combos'] = combos
                    else:
                        if filters.get('origin_ids'):
                            expanded_ids = self._resolve_descendant_ids(organization_id, filters['origin_ids'])
                            query = query.filter(Transaction.origin_id.in_(expanded_ids))
                            applied_filters['origin_ids'] = expanded_ids
                        if filters.get('location_tag_id') is not None:
                            query = query.filter(Transaction.location_tag_id == filters['location_tag_id'])
                            applied_filters['location_tag_id'] = filters['location_tag_id']
                        if filters.get('tenant_id') is not None:
                            query = query.filter(Transaction.tenant_id == filters['tenant_id'])
                            applied_filters['tenant_id'] = filters['tenant_id']

                # Filter by date range
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if date_from:
                    applied_filters['date_from'] = date_from
                if date_to:
                    applied_filters['date_to'] = date_to
                if report_type == 'comparison':
                    # For comparison, use provided range as-is, no clamping
                    if date_from:
                        query = query.filter(TransactionRecord.transaction_date >= date_from)
                    if date_to:
                        query = query.filter(TransactionRecord.transaction_date <= date_to)
                else:
                    if date_from:
                        query = query.filter(TransactionRecord.transaction_date >= date_from)
                    if date_to:
                        query = query.filter(TransactionRecord.transaction_date <= date_to)
            
            # Print applied filters before executing query
            if applied_filters:
                print(
                    f"Applied filters for organization_id {organization_id}: {applied_filters}"
                )
            
            # Execute query
            transaction_records = query.all()

            # Preload transaction fields (origin_id, location_tag_id, tenant_id) for logging
            transaction_ids = {record.created_transaction_id for record in transaction_records}
            txn_meta_map: Dict[int, Dict[str, Any]] = {}
            if transaction_ids:
                txn_rows = self.db.query(
                    Transaction.id,
                    Transaction.origin_id,
                    Transaction.location_tag_id,
                    Transaction.tenant_id,
                    Transaction.weight_kg,
                ).filter(Transaction.id.in_(transaction_ids)).all()
                for row in txn_rows:
                    txn_meta_map[row[0]] = {
                        'origin_id': row[1],
                        'location_tag_id': row[2],
                        'tenant_id': row[3],
                        'weight_kg': float(row[4]) if row[4] is not None else None,
                    }

            # Log per-record data (weight, tag, tenant) for debugging report weight issues (first 20 only)
            logger.info(
                f"[REPORTS] get_transaction_records_by_organization fetched {len(transaction_records)} records "
                f"(org_id={organization_id}, report_type={report_type})"
            )
            _to_log = transaction_records[:20]
            for i, record in enumerate(_to_log):
                txn_meta = txn_meta_map.get(record.created_transaction_id) or {}
                logger.info(
                    f"[REPORTS] record[{i}] id={record.id} txn_id={record.created_transaction_id} "
                    f"origin_id={txn_meta.get('origin_id')} tag_id={txn_meta.get('location_tag_id')} "
                    f"tenant_id={txn_meta.get('tenant_id')} "
                    f"origin_weight_kg={getattr(record, 'origin_weight_kg', None)} "
                    f"origin_quantity={getattr(record, 'origin_quantity', None)} "
                    f"txn_weight_kg={txn_meta.get('weight_kg')} "
                    f"transaction_date={record.transaction_date}"
                )
            if len(transaction_records) > 20:
                logger.info(f"[REPORTS] ... and {len(transaction_records) - 20} more records (only first 20 logged)")

            # Preload transaction statuses for included records
            status_map: Dict[int, TransactionStatus] = {}
            if transaction_ids:
                transactions_rows = self.db.query(Transaction.id, Transaction.status).filter(
                    Transaction.id.in_(transaction_ids)
                ).all()
                for _id, status in transactions_rows:
                    status_map[_id] = status
                transactions_total = len(transactions_rows)
                transactions_approved = sum(1 for _id, status in transactions_rows if status == TransactionStatus.approved)
            else:
                transactions_total = 0
                transactions_approved = 0

            # If report_type is 'overview', 'diversion', 'performance', or 'materials', fetch material data for each record
            materials_map = {}
            if report_type in ('overview', 'diversion', 'performance', 'materials', 'comparison'):
                # Collect unique material_ids
                material_ids = set()
                for record in transaction_records:
                    if record.material_id:
                        material_ids.add(record.material_id)
                
                # Query all materials at once (efficient)
                if material_ids:
                    materials = self.db.query(Material).filter(
                        Material.id.in_(material_ids)
                    ).all()
                    # Resolve tag ids to names to detect plastics
                    tag_ids: set[int] = set()
                    for material in materials:
                        try:
                            for pair in material.tags or []:
                                if isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[1] is not None:
                                    tag_ids.add(int(pair[1]))
                        except Exception:
                            continue

                    tag_name_map: Dict[int, str] = {}
                    if tag_ids:
                        tags = self.db.query(MaterialTag).filter(MaterialTag.id.in_(tag_ids)).all()
                        for t in tags:
                            tag_name_map[t.id] = t.name or ""

                    # Create a mapping of material_id to material data with is_plastic flag
                    for material in materials:
                        m_dict = self._material_to_dict(material)
                        is_plastic = False
                        try:
                            for pair in material.tags or []:
                                if isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[1] is not None:
                                    name = tag_name_map.get(int(pair[1]), "")
                                    if 'plastic' in name.lower():
                                        is_plastic = True
                                        break
                        except Exception:
                            is_plastic = False
                        m_dict['is_plastic'] = is_plastic
                        materials_map[material.id] = m_dict
            
            # Convert to dict
            records_data = []
            for record in transaction_records:
                record_dict = self._transaction_record_to_dict(record)
                
                # Add material data if report_type needs it
                if report_type in ('overview', 'diversion', 'performance', 'materials', 'comparison') and record.material_id:
                    record_dict['material'] = materials_map.get(record.material_id)
                
                # Include origin_id, location_tag_id, tenant_id from the created transaction for downstream aggregations and tag/tenant handling
                try:
                    txn = record.created_transaction
                    if txn:
                        record_dict['origin_id'] = txn.origin_id
                        record_dict['location_tag_id'] = getattr(txn, 'location_tag_id', None)
                        record_dict['tenant_id'] = getattr(txn, 'tenant_id', None)
                    else:
                        record_dict['origin_id'] = None
                        record_dict['location_tag_id'] = None
                        record_dict['tenant_id'] = None
                except Exception:
                    record_dict['origin_id'] = None
                    record_dict['location_tag_id'] = None
                    record_dict['tenant_id'] = None

                # Mark rejection status for downstream filtering
                try:
                    tx_status = status_map.get(record.created_transaction_id)
                    record_dict['is_rejected'] = (tx_status == TransactionStatus.rejected)
                except Exception:
                    record_dict['is_rejected'] = False
                
                records_data.append(record_dict)

            # Summary log for weight/tag/tenant debugging
            with_weight = sum(1 for d in records_data if (d.get('origin_weight_kg') or 0) > 0)
            with_tag_or_tenant = 0
            for d in records_data:
                oid = d.get('origin_id')
                txn_meta = txn_meta_map.get(d.get('created_transaction_id')) if d.get('created_transaction_id') else {}
                if txn_meta and (txn_meta.get('location_tag_id') is not None or txn_meta.get('tenant_id') is not None):
                    with_tag_or_tenant += 1
            logger.info(
                f"[REPORTS] records_data summary: total={len(records_data)} "
                f"with_origin_weight_kg>0={with_weight} with_tag_or_tenant={with_tag_or_tenant}"
            )

            # Print full record data for overview so you can check weight (all report types)
            print("\n" + "=" * 60 + " [REPORTS] RECORDS DATA (check weight) " + "=" * 60)
            print(f"report_type={report_type} organization_id={organization_id} total_records={len(records_data)}\n")
            for i, d in enumerate(records_data):
                txn_id = d.get('created_transaction_id')
                txn_meta = txn_meta_map.get(txn_id) or {}
                print(f"--- record[{i}] ---")
                print(f"  id={d.get('id')}  created_transaction_id={txn_id}")
                print(f"  origin_id={d.get('origin_id')}  location_tag_id={txn_meta.get('location_tag_id')}  tenant_id={txn_meta.get('tenant_id')}")
                print(f"  origin_weight_kg={d.get('origin_weight_kg')}  origin_quantity={d.get('origin_quantity')}  total_amount={d.get('total_amount')}")
                print(f"  transaction_date={d.get('transaction_date')}  material_id={d.get('material_id')}")
                if d.get('material'):
                    mat = d['material']
                    print(f"  material: name={mat.get('name_en') or mat.get('name_th')} unit_weight={mat.get('unit_weight')}")
                print()
            print("=" * 60 + "\n")

            return {
                'success': True,
                'data': records_data,
                'total': len(records_data),
                'transactions_total': transactions_total,
                'transactions_approved': transactions_approved,
                'organization_id': organization_id,
                'message': 'Transaction records retrieved successfully'
            }

        except ValidationException as e:
            logger.error(f"Validation error in get_transaction_records_by_organization: {str(e)}")
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_transaction_records_by_organization: {str(e)}")
            raise Exception(f"Failed to retrieve transaction records: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_transaction_records_by_organization: {str(e)}")
            raise

    def get_overview_data(
        self,
        organization_id: int,
        filters: Optional[Dict[str, Any]] = None,
        current_user_id: Any = None,
        report_type: str = None
    ) -> Dict[str, Any]:
        """
        Optimized data fetch for overview/comparison/performance reports.
        Single SQL query selecting only needed columns — no N+1, no full ORM loading.
        Returns lightweight rows for fast Python-side aggregation.

        If report_type='comparison', date filtering is applied without clamping.
        """
        try:
            query = self.db.query(
                TransactionRecord.origin_quantity,          # 0
                TransactionRecord.transaction_date,         # 1
                TransactionRecord.created_transaction_id,   # 2
                Transaction.origin_id,                      # 3
                Transaction.status,                         # 4
                Material.unit_weight,                       # 5
                Material.calc_ghg,                          # 6
                Material.category_id,                       # 7
                Material.main_material_id,                  # 8
                Material.tags.label('material_tags'),       # 9
                TransactionRecord.origin_weight_kg,         # 10
                TransactionRecord.category_id.label('record_category_id'),          # 11
                TransactionRecord.main_material_id.label('record_main_material_id'),# 12
                TransactionRecord.material_id,              # 13
                Material.name_en.label('material_name_en'), # 14
                Material.name_th.label('material_name_th'), # 15
                TransactionRecord.disposal_method,          # 16
                TransactionRecord.status.label('record_status'),  # 17
                TransactionRecord.traceability_group_id,        # 18
                TransactionRecord.id.label('record_id'),        # 19
            ).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).outerjoin(
                Material,
                TransactionRecord.material_id == Material.id
            ).filter(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
                TransactionRecord.deleted_date.is_(None),
                or_(
                    TransactionRecord.status != 'rejected',
                    TransactionRecord.status.is_(None)
                ),
            )

            # Filter by active organization_setup locations
            query = self._apply_active_setup_filter(query, organization_id)

            # Apply filters
            if filters:
                # New multi-select location filters
                query, new_filters_applied = self._apply_location_filters(query, filters, organization_id)

                # Legacy origin_combos / origin_ids filters (when new filters not provided)
                if not new_filters_applied:
                    if filters.get('origin_combos'):
                        combos = filters['origin_combos']
                        origin_only = {oid for (oid, tid, tenid) in combos if tid is None and tenid is None}
                        expanded_origin_only = set()
                        for oid in origin_only:
                            expanded_origin_only.update(self._resolve_descendant_ids(organization_id, [oid]))
                        conditions = []
                        if expanded_origin_only:
                            conditions.append(Transaction.origin_id.in_(list(expanded_origin_only)))
                        for oid, tag_id, tenant_id in combos:
                            if oid in origin_only:
                                continue
                            c = (Transaction.origin_id == oid)
                            c = and_(c, Transaction.location_tag_id == tag_id) if tag_id else and_(c, Transaction.location_tag_id.is_(None))
                            c = and_(c, Transaction.tenant_id == tenant_id) if tenant_id else and_(c, Transaction.tenant_id.is_(None))
                            conditions.append(c)
                        if conditions:
                            query = query.filter(or_(*conditions))
                    else:
                        if filters.get('origin_ids'):
                            expanded_ids = self._resolve_descendant_ids(organization_id, filters['origin_ids'])
                            query = query.filter(Transaction.origin_id.in_(expanded_ids))
                        if filters.get('location_tag_id') is not None:
                            query = query.filter(Transaction.location_tag_id == filters['location_tag_id'])
                        if filters.get('tenant_id') is not None:
                            query = query.filter(Transaction.tenant_id == filters['tenant_id'])

                if filters.get('material_ids'):
                    query = query.filter(TransactionRecord.material_id.in_(filters['material_ids']))

                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if date_from or date_to:
                    if report_type == 'comparison':
                        # For comparison, use provided range as-is, no clamping
                        if date_from:
                            query = query.filter(TransactionRecord.transaction_date >= date_from)
                        if date_to:
                            query = query.filter(TransactionRecord.transaction_date <= date_to)
                    else:
                        if date_from:
                            query = query.filter(TransactionRecord.transaction_date >= date_from)
                        if date_to:
                            query = query.filter(TransactionRecord.transaction_date <= date_to)

            # Apply member-based filtering (non-admin users only see their own origins + descendants)
            query = self._apply_member_filter_to_transaction_query(query, current_user_id, organization_id)

            rows = query.all()

            return {
                'success': True,
                'rows': rows,
                'total_records': len(rows),
            }

        except Exception as e:
            logger.error(f"Error in get_overview_data: {str(e)}")
            raise

    def _should_filter_reports_by_member(self, current_user_id: Any) -> bool:
        """Return True if we should filter by origin/tag/tenant members (non-admin with a role)."""
        if current_user_id is None:
            return False
        try:
            user_id = int(current_user_id)
            user = self.db.query(UserLocation).options(
                joinedload(UserLocation.organization_role)
            ).filter(UserLocation.id == user_id).first()
            if not user:
                return True
            if user.organization_role_id is None:
                return False
            if user.organization_role and user.organization_role.key == 'admin':
                return False
            return True
        except Exception:
            return True

    def _get_active_setup_location_ids(self, organization_id: int) -> Optional[set]:
        """
        Get all location IDs from the active organization_setup (root_nodes + hub_node).
        Returns None if no active setup found (meaning no filtering should be applied).
        Returns a set of ints representing all nodeIds in the active setup.
        """
        setup = self.db.query(OrganizationSetup).filter(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.is_active == True,
            OrganizationSetup.deleted_date.is_(None)
        ).order_by(OrganizationSetup.created_date.desc()).first()

        if not setup:
            return None

        ids = set()

        def _collect_all_ids(nodes):
            if not nodes:
                return
            for node in nodes:
                nid = node.get('nodeId')
                if nid is not None:
                    ids.add(int(nid) if isinstance(nid, str) else nid)
                if node.get('children'):
                    _collect_all_ids(node['children'])

        root_nodes = setup.root_nodes if isinstance(setup.root_nodes, list) else []
        _collect_all_ids(root_nodes)

        hub_node = setup.hub_node if isinstance(setup.hub_node, dict) else {}
        if hub_node.get('children'):
            _collect_all_ids(hub_node['children'])

        return ids if ids else None

    def _apply_active_setup_filter(self, query, organization_id: int):
        """
        Filter query to only include transactions where origin_id is in the
        active organization_setup, and destination_id (on TransactionRecord) is
        either NULL or also in the active setup.
        """
        active_ids = self._get_active_setup_location_ids(organization_id)
        if active_ids is None:
            return query

        active_list = list(active_ids)
        logger.info(f"[REPORTS] Applying active setup filter: {len(active_list)} location IDs for org {organization_id}")

        query = query.filter(Transaction.origin_id.in_(active_list))
        query = query.filter(
            or_(
                TransactionRecord.destination_id.is_(None),
                TransactionRecord.destination_id.in_(active_list)
            )
        )
        return query

    def _resolve_descendant_ids(self, organization_id: int, origin_ids: List[int]) -> List[int]:
        """
        Given a list of origin_ids, expand each to include itself + all descendants
        from organization_setup.root_nodes tree.
        """
        setup = self.db.query(OrganizationSetup).filter(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.is_active == True
        ).first()
        if not setup or not setup.root_nodes:
            return origin_ids

        root_nodes = setup.root_nodes if isinstance(setup.root_nodes, list) else []
        target_set = set(origin_ids)
        expanded = set(origin_ids)

        def _collect_descendants(nodes):
            ids = set()
            for node in nodes:
                nid = node.get('nodeId')
                if nid is not None:
                    nid = int(nid) if isinstance(nid, str) else nid
                    ids.add(nid)
                if node.get('children'):
                    ids |= _collect_descendants(node['children'])
            return ids

        def _find_and_expand(nodes):
            for node in nodes:
                nid = node.get('nodeId')
                if nid is not None:
                    nid = int(nid) if isinstance(nid, str) else nid
                if nid in target_set and node.get('children'):
                    expanded.update(_collect_descendants(node['children']))
                if node.get('children'):
                    _find_and_expand(node['children'])

        _find_and_expand(root_nodes)
        return list(expanded)

    def _apply_location_filters(self, query, filters: Dict[str, Any], organization_id: int):
        """
        Apply new location_ids/filter_tag_ids/filter_tenant_ids filters to a query.
        location_ids: filter by these locations + their descendants (union).
        filter_tag_ids: intersect with location results (Transaction.location_tag_id IN ...).
        filter_tenant_ids: intersect with location results (Transaction.tenant_id IN ...).
        Returns (query, applied) where applied=True if new filters were used.
        """
        applied = False
        if filters.get('location_ids'):
            expanded_ids = self._resolve_descendant_ids(organization_id, filters['location_ids'])
            query = query.filter(Transaction.origin_id.in_(expanded_ids))
            applied = True
        if filters.get('filter_tag_ids'):
            query = query.filter(Transaction.location_tag_id.in_(filters['filter_tag_ids']))
            applied = True
        if filters.get('filter_tenant_ids'):
            query = query.filter(Transaction.tenant_id.in_(filters['filter_tenant_ids']))
            applied = True
        return query, applied

    def _apply_member_filter_to_transaction_query(self, query, current_user_id: Any, organization_id: Optional[int] = None):
        """
        Filter transactions to those from the user's assigned locations (3-tier model).
        Owners see all transactions; members see only assigned locations + descendants.
        """
        if current_user_id is None or organization_id is None:
            return query

        from ..users.user_service import UserService
        user_service = UserService(self.db)
        locations = user_service.crud.get_user_locations(organization_id=organization_id)
        tiers = user_service._resolve_location_tiers(locations, int(organization_id), int(current_user_id))

        if tiers['is_owner']:
            return query

        assigned_ids = tiers['assigned_ids']
        if not assigned_ids:
            return query.filter(Transaction.origin_id.is_(None))

        return query.filter(Transaction.origin_id.in_(list(assigned_ids)))

    def get_origin_by_organization(self, organization_id: int, filters: Optional[Dict[str, Any]] = None, current_user_id: Any = None) -> Dict[str, Any]:
        """
        Get origin filter options with composite origin+tag+tenant combinations from existing transaction data.
        If current_user_id is set and user is not admin and has a role, only origins from transactions where
        the user is in origin/tag/tenant members. Returns only the most specific (leaf) level per origin.
        """
        try:
            # Query distinct (origin_id, location_tag_id, tenant_id) from Transaction (with filters)
            base_filter = [
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
                Transaction.status != TransactionStatus.rejected,
                Transaction.origin_id.isnot(None)
            ]
            if filters and (filters.get('date_from') or filters.get('date_to') or filters.get('material_ids')):
                tr_query = self.db.query(
                    Transaction.origin_id,
                    Transaction.location_tag_id,
                    Transaction.tenant_id
                ).join(
                    TransactionRecord,
                    TransactionRecord.created_transaction_id == Transaction.id
                ).filter(
                    *base_filter,
                    TransactionRecord.deleted_date.is_(None)
                )
                material_ids = (filters.get('material_ids') or [])
                if material_ids:
                    try:
                        mids = [int(m) for m in material_ids]
                        if mids:
                            tr_query = tr_query.filter(TransactionRecord.material_id.in_(mids))
                    except Exception:
                        pass
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if date_from or date_to:
                    if date_from:
                        tr_query = tr_query.filter(TransactionRecord.transaction_date >= date_from)
                    if date_to:
                        tr_query = tr_query.filter(TransactionRecord.transaction_date <= date_to)
                tr_query = self._apply_member_filter_to_transaction_query(tr_query, current_user_id, organization_id)
                combos_result = tr_query.distinct().all()
            else:
                combos_query = self.db.query(
                    Transaction.origin_id,
                    Transaction.location_tag_id,
                    Transaction.tenant_id
                ).filter(*base_filter)
                combos_result = self._apply_member_filter_to_transaction_query(combos_query, current_user_id, organization_id).distinct().all()

            # Expand member-filtered origins to also include their descendants
            if self._should_filter_reports_by_member(current_user_id):
                member_origin_ids = list({row[0] for row in combos_result if row[0] is not None})
                if member_origin_ids:
                    expanded_ids = self._resolve_descendant_ids(organization_id, member_origin_ids)
                    new_ids = set(expanded_ids) - set(member_origin_ids)
                    if new_ids:
                        extra_combos = self.db.query(
                            Transaction.origin_id,
                            Transaction.location_tag_id,
                            Transaction.tenant_id
                        ).filter(
                            *base_filter,
                            Transaction.origin_id.in_(list(new_ids))
                        ).distinct().all()
                        combos_result = list(combos_result) + list(extra_combos)

            # Filter combos to only include origins in the active organization_setup
            active_setup_ids = self._get_active_setup_location_ids(organization_id)
            if active_setup_ids is not None:
                combos_result = [row for row in combos_result if row[0] in active_setup_ids]

            origin_ids = list({row[0] for row in combos_result if row[0] is not None})
            tag_ids = list({row[1] for row in combos_result if row[1] is not None})
            tenant_ids = list({row[2] for row in combos_result if row[2] is not None})
            tags_by_origin: Dict[int, set] = {}
            tenants_by_origin: Dict[int, set] = {}
            for origin_id, tag_id, tenant_id in combos_result:
                if origin_id is None:
                    continue
                if origin_id not in tags_by_origin:
                    tags_by_origin[origin_id] = set()
                if tag_id is not None:
                    tags_by_origin[origin_id].add(tag_id)
                if origin_id not in tenants_by_origin:
                    tenants_by_origin[origin_id] = set()
                if tenant_id is not None:
                    tenants_by_origin[origin_id].add(tenant_id)

            # Build location hierarchy (branches, buildings, floors, rooms) with parent/child relationships
            origin_locations = self.db.query(UserLocation).filter(UserLocation.id.in_(origin_ids)).all() if origin_ids else []

            location_filter: Dict[str, Any] = {
                'branch_level_name': None,
                'building_level_name': None,
                'floor_level_name': None,
                'room_level_name': None,
                'branches': [],
                'buildings': [],
                'floors': [],
                'rooms': []
            }
            tags_filter: List[Dict[str, Any]] = []
            tenants_filter: List[Dict[str, Any]] = []

            org_setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            ).first() or self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id
            ).order_by(OrganizationSetup.created_date.desc()).first()

            if org_setup:
                location_filter['branch_level_name'] = org_setup.branch_level_name or 'Branch'
                location_filter['building_level_name'] = org_setup.building_level_name or 'Building'
                location_filter['floor_level_name'] = org_setup.floor_level_name or 'Floor'
                location_filter['room_level_name'] = org_setup.room_level_name or 'Room'

            if org_setup and org_setup.root_nodes:
                all_locations = self.db.query(UserLocation).filter(
                    UserLocation.organization_id == organization_id,
                    UserLocation.is_active == True,
                    UserLocation.deleted_date.is_(None)
                ).all()
                location_names = {loc.id: loc.display_name or loc.name_en or loc.name_th or f"Location {loc.id}" for loc in all_locations}

                parent_map: Dict[int, int] = {}
                level_map: Dict[int, int] = {}
                tree_children_map: Dict[int, list] = {}
                root_nodes = org_setup.root_nodes if isinstance(org_setup.root_nodes, list) else []

                def _build_tree_maps(nodes, parent_id=None, level=0):
                    for node in nodes:
                        nid = node.get('nodeId')
                        if nid is not None:
                            nid = int(nid) if isinstance(nid, str) else nid
                            if parent_id is not None:
                                parent_map[nid] = parent_id
                            level_map[nid] = level
                            tree_children_map[nid] = []
                            if parent_id is not None and parent_id in tree_children_map:
                                tree_children_map[parent_id].append(nid)
                            children = node.get('children', [])
                            if children:
                                _build_tree_maps(children, nid, level + 1)
                _build_tree_maps(root_nodes, None)

                def _get_ancestor_path(loc_id, visited=None):
                    visited = visited or set()
                    if loc_id in visited:
                        return []
                    visited.add(loc_id)
                    pid = parent_map.get(loc_id)
                    if pid is None:
                        return []
                    return _get_ancestor_path(pid, visited) + [location_names.get(pid, f"Location {pid}")]

                # Collect needed IDs: origins from transactions + their ancestors (not descendants)
                needed_ids = set()
                for oid in origin_ids:
                    oid_int = int(oid)
                    if oid_int in level_map:
                        needed_ids.add(oid_int)
                        current = oid_int
                        while current in parent_map:
                            needed_ids.add(parent_map[current])
                            current = parent_map[current]

                # Group by level (0=branch, 1=building, 2=floor, 3=room)
                level_groups: Dict[int, list] = {0: [], 1: [], 2: [], 3: []}
                for loc_id in needed_ids:
                    level = level_map.get(loc_id)
                    if level is not None and level in level_groups:
                        children_in_result = [
                            cid for cid in tree_children_map.get(loc_id, [])
                            if cid in needed_ids
                        ]
                        ancestors = _get_ancestor_path(loc_id)
                        level_groups[level].append({
                            'id': loc_id,
                            'name': location_names.get(loc_id, f"Location {loc_id}"),
                            'parent_id': parent_map.get(loc_id),
                            'children_ids': children_in_result,
                            'path': ', '.join(ancestors) if ancestors else ''
                        })

                for level in level_groups:
                    level_groups[level].sort(key=lambda x: x['name'])

                location_filter['branches'] = level_groups[0]
                location_filter['buildings'] = level_groups[1]
                location_filter['floors'] = level_groups[2]
                location_filter['rooms'] = level_groups[3]
            else:
                # No tree structure - put all origins as branches
                for loc in origin_locations:
                    location_filter['branches'].append({
                        'id': loc.id,
                        'name': loc.display_name or loc.name_en or loc.name_th or str(loc.id),
                        'parent_id': None,
                        'children_ids': [],
                        'path': ''
                    })

            # Build tags filter
            if tag_ids:
                tags_db = self.db.query(UserLocationTag).filter(
                    UserLocationTag.id.in_(tag_ids),
                    UserLocationTag.organization_id == organization_id,
                    UserLocationTag.is_active == True,
                    UserLocationTag.deleted_date.is_(None)
                ).all()
                for t in tags_db:
                    tag_entry: Dict[str, Any] = {
                        'id': t.id,
                        'name': t.name or f"Tag {t.id}",
                        'location_ids': [oid for oid in origin_ids if t.id in tags_by_origin.get(oid, set())]
                    }
                    if t.start_date is not None or t.end_date is not None:
                        tag_entry['start_date'] = t.start_date.isoformat() if t.start_date else None
                        tag_entry['end_date'] = t.end_date.isoformat() if t.end_date else None
                    tags_filter.append(tag_entry)
                tags_filter.sort(key=lambda x: x['name'])

            # Build tenants filter
            if tenant_ids:
                tenants_db = self.db.query(UserTenant).filter(
                    UserTenant.id.in_(tenant_ids),
                    UserTenant.organization_id == organization_id,
                    UserTenant.is_active == True,
                    UserTenant.deleted_date.is_(None)
                ).all()
                for t in tenants_db:
                    tenant_entry: Dict[str, Any] = {
                        'id': t.id,
                        'name': t.name or f"Tenant {t.id}",
                        'location_ids': [oid for oid in origin_ids if t.id in tenants_by_origin.get(oid, set())]
                    }
                    if t.start_date is not None or t.end_date is not None:
                        tenant_entry['start_date'] = t.start_date.isoformat() if t.start_date else None
                        tenant_entry['end_date'] = t.end_date.isoformat() if t.end_date else None
                    tenants_filter.append(tenant_entry)
                tenants_filter.sort(key=lambda x: x['name'])

            return {
                'success': True,
                'data': {
                    'location': location_filter,
                    'tags': tags_filter,
                    'tenants': tenants_filter
                },
                'organization_id': organization_id,
                'message': 'Origins retrieved successfully'
            }

        except ValidationException as e:
            logger.error(f"Validation error in get_origin_by_organization: {str(e)}")
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_origin_by_organization: {str(e)}")
            raise Exception(f"Failed to retrieve origins: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_origin_by_organization: {str(e)}")
            raise
    
    def get_material_by_organization(self, organization_id: int, filters: Optional[Dict[str, Any]] = None, current_user_id: Any = None) -> Dict[str, Any]:
        """
        Get all active materials for a specific organization based on transaction records.
        If current_user_id is set and user is not admin and has a role, only materials from transactions
        where the user is in origin/tag/tenant members.
        """
        try:
            # Step 1: Get transaction records that belong to this organization
            transaction_records_query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
                TransactionRecord.deleted_date.is_(None),
                or_(
                    TransactionRecord.status != 'rejected',
                    TransactionRecord.status.is_(None)
                ),
            )
            transaction_records_query = self._apply_member_filter_to_transaction_query(transaction_records_query, current_user_id, organization_id)
            # Filter by active organization_setup locations
            transaction_records_query = self._apply_active_setup_filter(transaction_records_query, organization_id)
            # Apply optional filters
            if filters:
                # New multi-select location filters
                transaction_records_query, new_filters_applied = self._apply_location_filters(transaction_records_query, filters, organization_id)

                # Legacy origin_combos / origin_ids filters (when new filters not provided)
                if not new_filters_applied:
                    if filters.get('origin_combos'):
                        combos = filters['origin_combos']
                        origin_only_origin_ids = {oid for (oid, tag_id, tenant_id) in combos if tag_id is None and tenant_id is None}
                        expanded_origin_only = set()
                        for oid in origin_only_origin_ids:
                            expanded_origin_only.update(self._resolve_descendant_ids(organization_id, [oid]))
                        conditions = []
                        if expanded_origin_only:
                            conditions.append(Transaction.origin_id.in_(list(expanded_origin_only)))
                        for oid, tag_id, tenant_id in combos:
                            if oid in origin_only_origin_ids:
                                continue
                            c = (Transaction.origin_id == oid)
                            if tag_id is None:
                                c = and_(c, Transaction.location_tag_id.is_(None))
                            else:
                                c = and_(c, Transaction.location_tag_id == tag_id)
                            if tenant_id is None:
                                c = and_(c, Transaction.tenant_id.is_(None))
                            else:
                                c = and_(c, Transaction.tenant_id == tenant_id)
                            conditions.append(c)
                        if conditions:
                            transaction_records_query = transaction_records_query.filter(or_(*conditions))
                    else:
                        origin_ids = (filters.get('origin_ids') or [])
                        if origin_ids:
                            try:
                                oids = [int(o) for o in origin_ids]
                                if oids:
                                    oids = self._resolve_descendant_ids(organization_id, oids)
                                    transaction_records_query = transaction_records_query.filter(Transaction.origin_id.in_(oids))
                            except Exception:
                                pass
                        if filters.get('location_tag_id') is not None:
                            transaction_records_query = transaction_records_query.filter(
                                Transaction.location_tag_id == filters['location_tag_id']
                            )
                        if filters.get('tenant_id') is not None:
                            transaction_records_query = transaction_records_query.filter(
                                Transaction.tenant_id == filters['tenant_id']
                            )
                # Material filter (optional intersection)
                material_ids = (filters.get('material_ids') or [])
                if material_ids:
                    try:
                        mids = [int(m) for m in material_ids]
                        if mids:
                            transaction_records_query = transaction_records_query.filter(TransactionRecord.material_id.in_(mids))
                    except Exception:
                        pass
                # Date range filter
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if date_from:
                    transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date >= date_from)
                if date_to:
                    transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date <= date_to)
            
            transaction_records = transaction_records_query.all()
            
            # Step 2: Extract unique material_ids from transaction records
            material_ids = set()
            for record in transaction_records:
                if record.material_id:  # Only add if material_id is not None
                    material_ids.add(record.material_id)
            
            # Step 3: Get materials from those IDs
            if material_ids:
                materials_query = self.db.query(Material).filter(
                    Material.id.in_(material_ids),
                    Material.is_active == True
                )
                materials = materials_query.all()
            else:
                materials = []
            
            # Convert to dict
            materials_data = []
            for material in materials:
                materials_data.append(self._material_to_dict(material))
            
            return {
                'success': True,
                'data': materials_data,
                'total': len(materials_data),
                'organization_id': organization_id,
                'message': 'Materials retrieved successfully'
            }
            
        except ValidationException as e:
            logger.error(f"Validation error in get_material_by_organization: {str(e)}")
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_material_by_organization: {str(e)}")
            raise Exception(f"Failed to retrieve materials: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_material_by_organization: {str(e)}")
            raise

    def get_organization_setup(self, organization_id: int) -> Dict[str, Any]:
        """
        Get active organization setup with root_nodes

        Args:
            organization_id: The organization ID to filter by

        Returns:
            Dict with organization setup data (only active setup with root_nodes)
        """
        try:

            # Query for active organization setup (not soft-deleted)
            setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True,
                OrganizationSetup.deleted_date.is_(None)
            ).order_by(OrganizationSetup.created_date.desc()).first()

            # Fallback: if no active setup, get the latest version regardless of is_active
            if not setup:
                setup = self.db.query(OrganizationSetup).filter(
                    OrganizationSetup.organization_id == organization_id,
                    OrganizationSetup.deleted_date.is_(None)
                ).order_by(OrganizationSetup.created_date.desc()).first()

            if not setup:
                return {
                    'success': True,
                    'data': None,
                    'organization_id': organization_id,
                    'message': 'No active organization setup found'
                }
            
            # Return only root_nodes
            return {
                'success': True,
                'data': {
                    'version': setup.version,
                    'root_nodes': setup.root_nodes,
                },
                'message': 'Organization setup retrieved successfully'
            }
            
        except ValidationException as e:
            logger.error(f"Validation error in get_organization_setup: {str(e)}")
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_organization_setup: {str(e)}")
            raise Exception(f"Failed to retrieve organization setup: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_organization_setup: {str(e)}")
            raise

    # ========== HELPER METHODS ==========

    def _transaction_record_to_dict(self, record: TransactionRecord) -> Dict[str, Any]:
        """
        Convert a TransactionRecord model to a dictionary
        
        Args:
            record: TransactionRecord model instance
            
        Returns:
            Dictionary representation of the transaction record
        """
        return {
            'id': record.id,
            'status': record.status,
            'created_transaction_id': record.created_transaction_id,
            'transaction_type': record.transaction_type,
            'material_id': record.material_id,
            'main_material_id': record.main_material_id,
            'category_id': record.category_id,
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
            'completed_date': record.completed_date.isoformat() if record.completed_date else None,
            'transaction_date': record.transaction_date.isoformat() if record.transaction_date else None,
            'updated_date': record.updated_date.isoformat() if record.updated_date else None,
            'is_active': record.is_active,
            'traceability': record.traceability
        }

    def _origin_to_dict(self, origin: UserLocation) -> Dict[str, Any]:
        """
        Convert a UserLocation model to a dictionary
        
        Args:
            origin: UserLocation model instance
            
        Returns:
            Dictionary representation of the origin
        """
        return {
            'id': origin.id,
            'name_th': origin.name_th,
            'name_en': origin.name_en,
            'display_name': origin.display_name,
        }

    def _material_to_dict(self, material: Material) -> Dict[str, Any]:
        """
        Convert a Material model to a dictionary
        
        Args:
            material: Material model instance
            
        Returns:
            Dictionary representation of the material
        """
        return {
            'id': material.id,
            'name_th': material.name_th,
            'name_en': material.name_en,
            'category_id': material.category_id,
            'main_material_id': material.main_material_id,
            'tags': material.tags,
            'unit_name_th': material.unit_name_th,
            'unit_name_en': material.unit_name_en,
            'unit_weight': float(material.unit_weight) if material.unit_weight else 0,
            'color': material.color,
            'calc_ghg': float(material.calc_ghg) if material.calc_ghg else 0,
            'is_global': material.is_global,
            'organization_id': material.organization_id,
            'is_active': material.is_active,
            'created_date': material.created_date.isoformat() if material.created_date else None,
            'updated_date': material.updated_date.isoformat() if material.updated_date else None,
        }