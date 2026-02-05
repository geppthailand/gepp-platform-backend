"""
Reports Service - Business logic for reports and analytics
Handles data retrieval and processing for various reports
"""

from typing import List, Optional, Dict, Any
from GEPPPlatform.models.cores.references import Material, MaterialTag
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserLocationTag, UserTenant
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, and_
from datetime import datetime, timedelta, timezone
import logging

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
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
        report_type: str = None
    ) -> Dict[str, Any]:
        """
        Get all active transaction records for a specific organization
        
        Args:
            organization_id: The organization ID to filter by
            filters: Optional filters (e.g., status, date range, material type)
            report_type: Optional report type. If 'overview', includes material data in each record
            
        Returns:
            Dict with transaction records data and metadata
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
                TransactionRecord.is_active == True,
                Transaction.status != TransactionStatus.rejected
            )
            
            # Track applied filters for logging
            applied_filters = {}
            
            # Apply additional filters if provided
            if filters:
                # Filter by material_ids (supports multiple)
                if filters.get('material_ids'):
                    query = query.filter(TransactionRecord.material_id.in_(filters['material_ids']))
                    applied_filters['material_ids'] = filters['material_ids']
                
                # Filter by origin_combos (multiple composites: "2507||1,2507|46|")
                # If "origin only" (oid, None, None) is selected for an origin, include ALL rows for that origin.
                if filters.get('origin_combos'):
                    combos = filters['origin_combos']
                    origin_only_origin_ids = {oid for (oid, tag_id, tenant_id) in combos if tag_id is None and tenant_id is None}
                    conditions = []
                    for oid in origin_only_origin_ids:
                        conditions.append(Transaction.origin_id == oid)
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
                    # Filter by origin_ids (supports multiple)
                    if filters.get('origin_ids'):
                        query = query.filter(Transaction.origin_id.in_(filters['origin_ids']))
                        applied_filters['origin_ids'] = filters['origin_ids']
                    # Filter by location_tag_id (when single composite origin selected)
                    if filters.get('location_tag_id') is not None:
                        query = query.filter(Transaction.location_tag_id == filters['location_tag_id'])
                        applied_filters['location_tag_id'] = filters['location_tag_id']
                    # Filter by tenant_id (when single composite origin selected)
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
                    # Apply clamping (max 3 years, date_to <= today)
                    try:
                        MAX_DAYS = 365 * 3
                        now = datetime.now(timezone.utc)
                        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                        df = datetime.fromisoformat(date_from) if isinstance(date_from, str) else date_from
                        dt = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                        if dt and dt > end_of_today:
                            dt = end_of_today
                        if df and dt and (dt - df).days > MAX_DAYS:
                            df = dt - timedelta(days=MAX_DAYS)
                        if df:
                            query = query.filter(TransactionRecord.transaction_date >= df.isoformat() if isinstance(date_from, str) else df)
                        if dt:
                            query = query.filter(TransactionRecord.transaction_date <= dt.isoformat() if isinstance(date_to, str) else dt)
                    except Exception:
                        # If parsing fails, fall back to original filters
                        if date_from:
                            query = query.filter(TransactionRecord.transaction_date >= date_from)
                        if date_to:
                            try:
                                parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                                now = datetime.now(timezone.utc)
                                end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                                if parsed and parsed > end_of_today:
                                    parsed = end_of_today
                                query = query.filter(TransactionRecord.transaction_date <= parsed.isoformat() if isinstance(date_to, str) else parsed)
                            except Exception:
                                query = query.filter(TransactionRecord.transaction_date <= date_to)
            
            # Print applied filters before executing query
            if applied_filters:
                print(
                    f"Applied filters for organization_id {organization_id}: {applied_filters}"
                )
            
            # Execute query
            transaction_records = query.all()
            
            # Preload transaction statuses for included records
            transaction_ids = {record.created_transaction_id for record in transaction_records}
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
                
                # Include origin_id from the created transaction for downstream aggregations
                try:
                    record_dict['origin_id'] = record.created_transaction.origin_id if record.created_transaction else None
                except Exception:
                    record_dict['origin_id'] = None

                # Mark rejection status for downstream filtering
                try:
                    tx_status = status_map.get(record.created_transaction_id)
                    record_dict['is_rejected'] = (tx_status == TransactionStatus.rejected)
                except Exception:
                    record_dict['is_rejected'] = False
                
                records_data.append(record_dict)
            
            # Prepare result summary for logging
            result_summary = {
                'organization_id': organization_id,
                'report_type': report_type,
                'total_records': len(records_data),
                'transactions_total': transactions_total,
                'transactions_approved': transactions_approved,
                'filters_applied': applied_filters if applied_filters else None
            }
            
            # Print results
            print(
                f"get_transaction_records_by_organization results - "
                f"organization_id: {organization_id}, "
                f"report_type: {report_type}, "
                f"total_records: {len(records_data)}, "
                f"transactions_total: {transactions_total}, "
                f"transactions_approved: {transactions_approved}"
            )
            
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

    def get_origin_by_organization(self, organization_id: int, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get origin filter options with composite origin+tag+tenant combinations from existing transaction data.
        Returns options: origin only, origin·tag, origin·tenant, origin·tag·tenant (per-origin tags/tenants).
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
                    TransactionRecord.is_active == True
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
                    try:
                        MAX_DAYS = 365 * 3
                        now = datetime.now(timezone.utc)
                        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                        df = datetime.fromisoformat(date_from) if isinstance(date_from, str) else date_from
                        dt = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                        if dt and dt > end_of_today:
                            dt = end_of_today
                        if df and dt and (dt - df).days > MAX_DAYS:
                            df = dt - timedelta(days=MAX_DAYS)
                        if df:
                            tr_query = tr_query.filter(TransactionRecord.transaction_date >= (df.isoformat() if isinstance(date_from, str) else df))
                        if dt:
                            tr_query = tr_query.filter(TransactionRecord.transaction_date <= (dt.isoformat() if isinstance(date_to, str) else dt))
                    except Exception:
                        if date_from:
                            tr_query = tr_query.filter(TransactionRecord.transaction_date >= date_from)
                        if date_to:
                            try:
                                parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                                end_of_today = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)
                                if parsed and parsed > end_of_today:
                                    parsed = end_of_today
                                tr_query = tr_query.filter(TransactionRecord.transaction_date <= (parsed.isoformat() if isinstance(date_to, str) else parsed))
                            except Exception:
                                tr_query = tr_query.filter(TransactionRecord.transaction_date <= date_to)
                combos_result = tr_query.distinct().all()
            else:
                combos_result = self.db.query(
                    Transaction.origin_id,
                    Transaction.location_tag_id,
                    Transaction.tenant_id
                ).filter(*base_filter).distinct().all()

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

            origin_options: List[Dict[str, Any]] = []
            if not origin_ids:
                return {
                    'success': True,
                    'data': [],
                    'total': 0,
                    'organization_id': organization_id,
                    'message': 'Origins retrieved successfully'
                }

            origin_locations = self.db.query(UserLocation).filter(UserLocation.id.in_(origin_ids)).all()
            origin_name_by_id = {
                loc.id: loc.display_name or loc.name_en or loc.name_th or f"Location {loc.id}"
                for loc in origin_locations
            }
            tag_name_by_id: Dict[int, str] = {}
            if tag_ids:
                tags = self.db.query(UserLocationTag).filter(
                    UserLocationTag.id.in_(tag_ids),
                    UserLocationTag.organization_id == organization_id,
                    UserLocationTag.is_active == True,
                    UserLocationTag.deleted_date.is_(None)
                ).all()
                tag_name_by_id = {t.id: (t.name or f"Tag {t.id}") for t in tags}
            tenant_name_by_id: Dict[int, str] = {}
            if tenant_ids:
                tenants = self.db.query(UserTenant).filter(
                    UserTenant.id.in_(tenant_ids),
                    UserTenant.organization_id == organization_id,
                    UserTenant.is_active == True,
                    UserTenant.deleted_date.is_(None)
                ).all()
                tenant_name_by_id = {t.id: (t.name or f"Tenant {t.id}") for t in tenants}

            location_paths: Dict[int, str] = {}
            org_setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            ).first() or self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id
            ).order_by(OrganizationSetup.created_date.desc()).first()
            if org_setup and org_setup.root_nodes:
                all_locations = self.db.query(UserLocation).filter(
                    UserLocation.organization_id == organization_id,
                    UserLocation.is_active == True,
                    UserLocation.deleted_date.is_(None)
                ).all()
                location_names = {loc.id: loc.display_name or loc.name_en or loc.name_th or f"Location {loc.id}" for loc in all_locations}
                parent_map: Dict[int, int] = {}
                root_nodes = org_setup.root_nodes if isinstance(org_setup.root_nodes, list) else []

                def _build_parent_map(nodes, parent_id=None):
                    for node in nodes:
                        nid = node.get('nodeId')
                        if nid is not None:
                            nid = int(nid) if isinstance(nid, str) else nid
                            if parent_id is not None:
                                parent_map[nid] = parent_id
                            if node.get('children'):
                                _build_parent_map(node.get('children', []), nid)
                _build_parent_map(root_nodes, None)

                def _collect_all_node_ids(nodes):
                    ids = set()
                    for node in nodes:
                        nid = node.get('nodeId')
                        if nid is not None:
                            ids.add(int(nid) if isinstance(nid, str) else nid)
                        if node.get('children'):
                            ids |= _collect_all_node_ids(node.get('children', []))
                    return ids
                all_node_ids = _collect_all_node_ids(root_nodes)

                def _get_ancestors(loc_id, visited=None):
                    visited = visited or set()
                    if loc_id in visited:
                        return []
                    visited.add(loc_id)
                    pid = parent_map.get(loc_id)
                    if pid is None:
                        return []
                    return _get_ancestors(pid, visited) + [location_names.get(pid, f"Location {pid}")]
                for loc in origin_locations:
                    loc_id = int(loc.id)
                    location_paths[loc_id] = ', '.join(_get_ancestors(loc_id)) if loc_id in all_node_ids else ''

            # Build options: location, location·tag, location·tenant, location·tag·tenant
            # Per origin: show all 4 types using tags/tenants that appear with that origin.
            # Only show location·tag·tenant when that exact combo exists in combos_result.
            combos_set = {(r[0], r[1], r[2]) for r in combos_result}
            seen_ids: set = set()

            for origin_id in origin_ids:
                origin_name = origin_name_by_id.get(origin_id, f"Location {origin_id}")
                path = location_paths.get(origin_id, '')
                origin_tag_ids = list(tags_by_origin.get(origin_id, []))
                origin_tenant_ids = list(tenants_by_origin.get(origin_id, []))
                # 1) Location only
                oid = f"{origin_id}||"
                if oid not in seen_ids:
                    seen_ids.add(oid)
                    origin_options.append({'id': oid, 'origin_id': origin_id, 'name': origin_name, 'display_name': origin_name, 'path': path})
                # 2) Location · tag
                for tag_id in origin_tag_ids:
                    tname = tag_name_by_id.get(tag_id)
                    if tname:
                        oid = f"{origin_id}|{tag_id}|"
                        if oid not in seen_ids:
                            seen_ids.add(oid)
                            origin_options.append({'id': oid, 'origin_id': origin_id, 'name': f"{origin_name} · {tname}", 'display_name': f"{origin_name} · {tname}", 'path': path})
                # 3) Location · tenant
                for tenant_id in origin_tenant_ids:
                    tname = tenant_name_by_id.get(tenant_id)
                    if tname:
                        oid = f"{origin_id}||{tenant_id}"
                        if oid not in seen_ids:
                            seen_ids.add(oid)
                            origin_options.append({'id': oid, 'origin_id': origin_id, 'name': f"{origin_name} · {tname}", 'display_name': f"{origin_name} · {tname}", 'path': path})
                # 4) Location · tag · tenant - only when that combo exists in data
                for tag_id in origin_tag_ids:
                    for tenant_id in origin_tenant_ids:
                        if (origin_id, tag_id, tenant_id) in combos_set:
                            tname = tag_name_by_id.get(tag_id)
                            tnt = tenant_name_by_id.get(tenant_id)
                            if tname and tnt:
                                oid = f"{origin_id}|{tag_id}|{tenant_id}"
                                if oid not in seen_ids:
                                    seen_ids.add(oid)
                                    origin_options.append({'id': oid, 'origin_id': origin_id, 'name': f"{origin_name} · {tname} · {tnt}", 'display_name': f"{origin_name} · {tname} · {tnt}", 'path': path})

            sorted_options = sorted(origin_options, key=lambda x: x['name'])
            origins_data = sorted_options
            return {
                'success': True,
                'data': origins_data,
                'total': len(origins_data),
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
    
    def get_material_by_organization(self, organization_id: int, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get all active materials for a specific organization based on transaction records
        
        Args:
            organization_id: The organization ID to filter by
            
        Returns:
            Dict with material data and metadata
        """
        try:
            # Step 1: Get transaction records that belong to this organization
            transaction_records_query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                TransactionRecord.is_active == True,
                Transaction.status != TransactionStatus.rejected
            )
            # Apply optional filters
            if filters:
                # Origin combos (multiple composites: "2507||1,2507|46|")
                # If "origin only" (oid, None, None) is selected, include ALL rows for that origin.
                if filters.get('origin_combos'):
                    combos = filters['origin_combos']
                    origin_only_origin_ids = {oid for (oid, tag_id, tenant_id) in combos if tag_id is None and tenant_id is None}
                    conditions = []
                    for oid in origin_only_origin_ids:
                        conditions.append(Transaction.origin_id == oid)
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
                    # Origin filter: restrict to specific origins if provided
                    origin_ids = (filters.get('origin_ids') or [])
                    if origin_ids:
                        try:
                            oids = [int(o) for o in origin_ids]
                            if oids:
                                transaction_records_query = transaction_records_query.filter(Transaction.origin_id.in_(oids))
                        except Exception:
                            pass
                    # Location tag filter (when single composite origin selected)
                    if filters.get('location_tag_id') is not None:
                        transaction_records_query = transaction_records_query.filter(
                            Transaction.location_tag_id == filters['location_tag_id']
                        )
                    # Tenant filter (when single composite origin selected)
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
                # Date range filter (clamped)
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                try:
                    MAX_DAYS = 365 * 3
                    now = datetime.utcnow()
                    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                    df = datetime.fromisoformat(date_from) if isinstance(date_from, str) else date_from
                    dt = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                    if dt and dt > end_of_today:
                        dt = end_of_today
                    if df and dt and (dt - df).days > MAX_DAYS:
                        df = dt - timedelta(days=MAX_DAYS)
                    if df:
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date >= df.isoformat() if isinstance(date_from, str) else df)
                    if dt:
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date <= dt.isoformat() if isinstance(date_to, str) else dt)
                except Exception:
                    if date_from:
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date >= date_from)
                    if date_to:
                        try:
                            parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                            now = datetime.utcnow()
                            end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                            if parsed and parsed > end_of_today:
                                parsed = end_of_today
                            transaction_records_query = transaction_records_query.filter(TransactionRecord.transaction_date <= parsed.isoformat() if isinstance(date_to, str) else parsed)
                        except Exception:
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
            
            # Query for active organization setup
            setup = self.db.query(OrganizationSetup).filter(
                OrganizationSetup.organization_id == organization_id,
                OrganizationSetup.is_active == True
            ).first()
            
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