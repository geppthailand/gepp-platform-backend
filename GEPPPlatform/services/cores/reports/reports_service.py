"""
Reports Service - Business logic for reports and analytics
Handles data retrieval and processing for various reports
"""

from typing import List, Optional, Dict, Any
from GEPPPlatform.models.cores.references import Material, MaterialTag
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, case, extract, and_
from datetime import datetime, timedelta
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

    # ========== OPTIMIZED OVERVIEW REPORT ==========

    def get_overview_aggregated(
        self,
        organization_id: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated overview data using SQL aggregation for better performance

        Args:
            organization_id: The organization ID to filter by
            filters: Optional filters (e.g., date range, material type)

        Returns:
            Dict with aggregated overview data
        """
        try:
            # Build base query with filters
            base_query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                TransactionRecord.is_active == True,
                Transaction.status != TransactionStatus.rejected  # Exclude rejected
            )

            # Apply date filters
            if filters:
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if date_from or date_to:
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
                            base_query = base_query.filter(TransactionRecord.created_date >= df)
                        if dt:
                            base_query = base_query.filter(TransactionRecord.created_date <= dt)
                    except Exception as e:
                        logger.warning(f"Date filter error: {e}")
                        if date_from:
                            base_query = base_query.filter(TransactionRecord.created_date >= date_from)
                        if date_to:
                            base_query = base_query.filter(TransactionRecord.created_date <= date_to)

            # This method returns pre-aggregated data that can be used directly
            # Instead of loading all records into memory
            return {
                'success': True,
                'use_aggregated': True,
                'organization_id': organization_id,
                'base_query': base_query  # Return query for further processing in handler
            }

        except Exception as e:
            logger.error(f"Error in get_overview_aggregated: {str(e)}")
            raise

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
            # Base query: Join transaction_records with transactions
            query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                TransactionRecord.is_active == True,
                Transaction.deleted_date.is_(None),
                Transaction.is_active == True
            )
            
            # Apply additional filters if provided
            if filters:
                # Filter by material_ids (supports multiple)
                if filters.get('material_ids'):
                    query = query.filter(TransactionRecord.material_id.in_(filters['material_ids']))
                
                # Filter by origin_ids (supports multiple)
                if filters.get('origin_ids'):
                    query = query.filter(Transaction.origin_id.in_(filters['origin_ids']))
                
                # Filter by date range
                date_from = filters.get('date_from')
                date_to = filters.get('date_to')
                if report_type == 'comparison':
                    # For comparison, use provided range as-is, no clamping
                    if date_from:
                        query = query.filter(TransactionRecord.created_date >= date_from)
                    if date_to:
                        query = query.filter(TransactionRecord.created_date <= date_to)
                else:
                    # Apply clamping (max 3 years, date_to <= today)
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
                            query = query.filter(TransactionRecord.created_date >= df.isoformat() if isinstance(date_from, str) else df)
                        if dt:
                            query = query.filter(TransactionRecord.created_date <= dt.isoformat() if isinstance(date_to, str) else dt)
                    except Exception:
                        # If parsing fails, fall back to original filters
                        if date_from:
                            query = query.filter(TransactionRecord.created_date >= date_from)
                        if date_to:
                            try:
                                parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                                now = datetime.utcnow()
                                end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                                if parsed and parsed > end_of_today:
                                    parsed = end_of_today
                                query = query.filter(TransactionRecord.created_date <= parsed.isoformat() if isinstance(date_to, str) else parsed)
                            except Exception:
                                query = query.filter(TransactionRecord.created_date <= date_to)
            
            # Execute query with optional limit for performance
            # For overview reports with large date ranges, we should limit results
            max_records = filters.get('max_records') if filters else None

            # Apply automatic limit for overview/diversion reports to prevent timeouts
            if report_type in ('overview', 'diversion') and not max_records:
                max_records = 50000  # Hard limit for overview to prevent memory issues
                logger.info(f"Auto-limiting {report_type} report to {max_records} records for performance")

            if max_records:
                # Order by created_date DESC to get most recent records first
                query = query.order_by(TransactionRecord.created_date.desc()).limit(max_records)

            transaction_records = query.all()

            # Log performance warning for large result sets
            record_count = len(transaction_records)
            if record_count > 10000:
                logger.warning(f"Large result set: {record_count} transaction records loaded into memory for report_type={report_type}")
            
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

                # Include origin_id and transaction_date from the created transaction for downstream aggregations
                try:
                    if record.created_transaction:
                        record_dict['origin_id'] = record.created_transaction.origin_id
                        record_dict['transaction_date'] = record.created_transaction.transaction_date.isoformat() if record.created_transaction.transaction_date else None
                    else:
                        record_dict['origin_id'] = None
                        record_dict['transaction_date'] = None
                except Exception:
                    record_dict['origin_id'] = None
                    record_dict['transaction_date'] = None

                # Mark rejection status for downstream filtering
                try:
                    tx_status = status_map.get(record.created_transaction_id)
                    record_dict['is_rejected'] = (tx_status == TransactionStatus.rejected)
                except Exception:
                    record_dict['is_rejected'] = False

                records_data.append(record_dict)
            
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
        Get all active origins for a specific organization
        
        Args:
            organization_id: The organization ID to filter by
            
        Returns:
            Dict with origin data and metadata
        """

        try:
            # If date filters provided, restrict origins to those that appear in transactions within the range
            origin_ids_in_range: Optional[set] = None
            if filters and (filters.get('date_from') or filters.get('date_to')):
                tr_query = self.db.query(Transaction.origin_id).join(
                    TransactionRecord,
                    TransactionRecord.created_transaction_id == Transaction.id,
                ).filter(
                    Transaction.organization_id == organization_id,
                    TransactionRecord.is_active == True,
                    Transaction.deleted_date.is_(None)
                )
                # Clamp and apply date range
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
                        tr_query = tr_query.filter(TransactionRecord.created_date >= df.isoformat() if isinstance(date_from, str) else df)
                    if dt:
                        tr_query = tr_query.filter(TransactionRecord.created_date <= dt.isoformat() if isinstance(date_to, str) else dt)
                except Exception:
                    if date_from:
                        tr_query = tr_query.filter(TransactionRecord.created_date >= date_from)
                    if date_to:
                        try:
                            parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                            now = datetime.utcnow()
                            end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                            if parsed and parsed > end_of_today:
                                parsed = end_of_today
                            tr_query = tr_query.filter(TransactionRecord.created_date <= parsed.isoformat() if isinstance(date_to, str) else parsed)
                        except Exception:
                            tr_query = tr_query.filter(TransactionRecord.created_date <= date_to)
                rows = tr_query.distinct().all()
                origin_ids_in_range = {row[0] for row in rows if row and row[0] is not None}

            # Base origins query
            query = self.db.query(UserLocation).filter(
                UserLocation.organization_id == organization_id,
                UserLocation.is_active == True,
                UserLocation.is_location == True,
                UserLocation.type.notin_(['hub', 'hub-main'])
            )
            if origin_ids_in_range is not None:
                if not origin_ids_in_range:
                    origins = []
                else:
                    query = query.filter(UserLocation.id.in_(list(origin_ids_in_range)))
                    origins = query.all()
            else:
                origins = query.all()

            # Convert to dict
            origins_data = []
            for origin in origins:
                origins_data.append(self._origin_to_dict(origin))

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
                TransactionRecord.is_active == True
            )
            # Apply optional date range filter (clamped)
            if filters:
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
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.created_date >= df.isoformat() if isinstance(date_from, str) else df)
                    if dt:
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.created_date <= dt.isoformat() if isinstance(date_to, str) else dt)
                except Exception:
                    if date_from:
                        transaction_records_query = transaction_records_query.filter(TransactionRecord.created_date >= date_from)
                    if date_to:
                        try:
                            parsed = datetime.fromisoformat(date_to) if isinstance(date_to, str) else date_to
                            now = datetime.utcnow()
                            end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                            if parsed and parsed > end_of_today:
                                parsed = end_of_today
                            transaction_records_query = transaction_records_query.filter(TransactionRecord.created_date <= parsed.isoformat() if isinstance(date_to, str) else parsed)
                        except Exception:
                            transaction_records_query = transaction_records_query.filter(TransactionRecord.created_date <= date_to)
            
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
            'created_date': record.created_date.isoformat() if record.created_date else None,
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