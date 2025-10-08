"""
Reports Service - Business logic for reports and analytics
Handles data retrieval and processing for various reports
"""

from typing import List, Optional, Dict, Any
from GEPPPlatform.models.cores.references import Material
from GEPPPlatform.models.users.user_location import UserLocation
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging

from ....models.transactions.transactions import Transaction
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
            # Base query: Join transaction_records with transactions
            query = self.db.query(TransactionRecord).join(
                Transaction,
                TransactionRecord.created_transaction_id == Transaction.id
            ).filter(
                Transaction.organization_id == organization_id,
                TransactionRecord.is_active == True
            )
            
            # Apply additional filters if provided
            if filters:
                # Filter by material
                if filters.get('material_id'):
                    query = query.filter(TransactionRecord.material_id == filters['material_id'])
                
                # Filter by origin_id
                if filters.get('origin_id'):
                    query = query.filter(Transaction.origin_id == filters['origin_id'])
                
                # Filter by date range
                if filters.get('date_from'):
                    query = query.filter(TransactionRecord.created_date >= filters['date_from'])
                
                if filters.get('date_to'):
                    query = query.filter(TransactionRecord.created_date <= filters['date_to'])
            
            # Execute query
            transaction_records = query.all()
            
            # If report_type is 'overview', fetch material data for each record
            materials_map = {}
            if report_type == 'overview':
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
                    
                    # Create a mapping of material_id to material data
                    for material in materials:
                        materials_map[material.id] = self._material_to_dict(material)
            
            # Convert to dict
            records_data = []
            for record in transaction_records:
                record_dict = self._transaction_record_to_dict(record)
                
                # Add material data if report_type is overview
                if report_type == 'overview' and record.material_id:
                    record_dict['material'] = materials_map.get(record.material_id)
                
                records_data.append(record_dict)
            
            return {
                'success': True,
                'data': records_data,
                'total': len(records_data),
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

    def get_origin_by_organization(self, organization_id: int) -> Dict[str, Any]:
        """
        Get all active origins for a specific organization
        
        Args:
            organization_id: The organization ID to filter by
            
        Returns:
            Dict with origin data and metadata
        """

        try:
            # Base query: Join origins with user_locations
            query = self.db.query(UserLocation).filter(
                UserLocation.organization_id == organization_id,
                UserLocation.is_active == True,
                UserLocation.is_location == True
            )

            # Execute query
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
    
    def get_material_by_organization(self, organization_id: int) -> Dict[str, Any]:
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