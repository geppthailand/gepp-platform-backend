"""
GRI Service
Handles logic for GRI 306 standards
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc, func, outerjoin

from ....models.gri import (
    Gri306_1,
    Gri306_2,
    Gri306_3,
    Gri306Export
)
from ....models.transactions.transactions import Transaction
from ....models.transactions.transaction_records import TransactionRecord
from ....models.cores.references import Material, MaterialCategory

from ....exceptions import (
    NotFoundException,
    ValidationException,
    BadRequestException
)

logger = logging.getLogger(__name__)

class GriService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_gri306_1_records(self, organization_id: int, user_id: int, records_data: List[Dict[str, Any]], delete_records: List[int] = None, global_year: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Create, update, or delete multiple GRI 306-1 records in bulk
        Also cascades soft delete to linked GRI 306-2 records
        """
        processed_records = []
        try:
            # 1. Handle Deletions first
            if delete_records:
                for del_id in delete_records:
                    record_to_delete = self.db.query(Gri306_1).filter(
                        Gri306_1.id == del_id,
                        Gri306_1.organization == organization_id,
                        Gri306_1.is_active == True
                    ).first()
                    
                    if record_to_delete:
                        record_to_delete.is_active = False
                        record_to_delete.deleted_date = datetime.now()
                        
                        # CASCADE DELETE to GRI 306-2
                        linked_gri2 = self.db.query(Gri306_2).filter(
                            Gri306_2.approached_id == del_id,
                            Gri306_2.is_active == True
                        ).all()
                        
                        for g2 in linked_gri2:
                            g2.is_active = False
                            g2.deleted_date = datetime.now()

            # 2. Handle Create/Update
            if records_data:
                for data in records_data:
                    # Use record specific year or global year
                    record_year = data.get('record_year') or global_year
                    
                    output_material_val = data.get('output_material')
                    output_category_val = data.get('output_category')
                    
                    def clean_id(val):
                        if not val: return None
                        if isinstance(val, int): return val
                        if isinstance(val, str) and val.isdigit(): return int(val)
                        return None 

                    record_id = data.get('id')
                    record = None

                    if record_id:
                        record = self.db.query(Gri306_1).filter(
                            Gri306_1.id == record_id,
                            Gri306_1.organization == organization_id,
                            Gri306_1.is_active == True
                        ).first()
                        
                        if not record:
                            continue
                            
                        if 'input_material' in data: record.input_material = data.get('input_material')
                        if 'activity' in data: record.activity = data.get('activity')
                        if 'output_material' in data: record.output_material = clean_id(output_material_val)
                        if 'output_category' in data: record.output_category = clean_id(output_category_val)
                        if 'method' in data: record.method = data.get('method')
                        if 'onsite' in data: record.onsite = data.get('onsite')
                        if 'weight' in data: record.weight = data.get('weight')
                        if 'description' in data: record.description = data.get('description')
                        if record_year: record.record_year = str(record_year)
                        record.updated_date = datetime.now()

                    else:
                        record = Gri306_1(
                            organization=organization_id,
                            created_by=user_id,
                            input_material=data.get('input_material'),
                            activity=data.get('activity'),
                            output_material=clean_id(output_material_val),
                            output_category=clean_id(output_category_val),
                            method=data.get('method'),
                            onsite=data.get('onsite'),
                            weight=data.get('weight'),
                            description=data.get('description'),
                            record_year=str(record_year) if record_year else None
                        )
                        self.db.add(record)
                    
                    processed_records.append(record)
                
            self.db.commit()
            for record in processed_records:
                self.db.refresh(record)
            return [self._serialize_gri306_1(record) for record in processed_records]
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing GRI 306-1 records: {str(e)}")
            raise BadRequestException(f"Failed to process GRI records: {str(e)}")

    def create_gri306_2_records(self, organization_id: int, user_id: int, records_data: List[Dict[str, Any]], delete_records: List[int] = None, global_year: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Create or update multiple GRI 306-2 records in bulk
        """
        processed_records = []
        try:
            # 1. Handle Deletions - Logic restored for robustness if needed, but not strictly required by user
            # If delete_records is sent, we process it.
            if delete_records:
                for del_id in delete_records:
                    record_to_delete = self.db.query(Gri306_2).filter(
                        Gri306_2.id == del_id,
                        Gri306_2.organization == organization_id,
                        Gri306_2.is_active == True
                    ).first()
                    
                    if record_to_delete:
                        record_to_delete.is_active = False
                        record_to_delete.deleted_date = datetime.now()

            # 2. Handle Create/Update
            if records_data:
                for data in records_data:
                    record_year = data.get('record_year') or global_year
                    record_id = data.get('id')
                    
                    prevention_action = data.get('prevention_action')
                    if isinstance(prevention_action, list):
                        prevention_action = ", ".join(prevention_action)
                        
                    verify_method = data.get('verify_method')
                    if isinstance(verify_method, list):
                        verify_method = ", ".join(verify_method)

                    record = None
                    if record_id:
                        record = self.db.query(Gri306_2).filter(
                            Gri306_2.id == record_id,
                            Gri306_2.organization == organization_id,
                            Gri306_2.is_active == True
                        ).first()
                        
                        if not record:
                            continue
                            
                        if 'approached_id' in data: record.approached_id = data.get('approached_id')
                        if 'prevention_action' in data: record.prevention_action = prevention_action
                        if 'verify_method' in data: record.verify_method = verify_method
                        if 'collection_method' in data: record.collection_method = data.get('collection_method')
                        if record_year: record.record_year = str(record_year)
                        record.updated_date = datetime.now()
                    else:
                        record = Gri306_2(
                            organization=organization_id,
                            created_by=user_id,
                            approached_id=data.get('approached_id'),
                            prevention_action=prevention_action,
                            verify_method=verify_method,
                            collection_method=data.get('collection_method'),
                            record_year=str(record_year) if record_year else None
                        )
                        self.db.add(record)
                    
                    processed_records.append(record)
            
            self.db.commit()
            for record in processed_records:
                self.db.refresh(record)
            return [self._serialize_gri306_2(record) for record in processed_records]
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing GRI 306-2 records: {str(e)}")
            raise BadRequestException(f"Failed to process GRI 306-2 records: {str(e)}")

    def create_gri306_3_records(self, organization_id: int, user_id: int, records_data: List[Dict[str, Any]], delete_records: List[int] = None, global_year: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Create, update, or delete multiple GRI 306-3 records (Spills) in bulk
        """
        processed_records = []
        try:
            # 1. Handle Deletions
            if delete_records:
                for del_id in delete_records:
                    record_to_delete = self.db.query(Gri306_3).filter(
                        Gri306_3.id == del_id,
                        Gri306_3.organization == organization_id,
                        Gri306_3.is_active == True
                    ).first()
                    
                    if record_to_delete:
                        record_to_delete.is_active = False
                        record_to_delete.deleted_date = datetime.now()

            # 2. Handle Create/Update
            if records_data:
                for data in records_data:
                    record_year = data.get('record_year') or global_year or data.get('year') # Handle nested or root year
                    record_id = data.get('id')
                    
                    record = None
                    if record_id:
                        record = self.db.query(Gri306_3).filter(
                            Gri306_3.id == record_id,
                            Gri306_3.organization == organization_id,
                            Gri306_3.is_active == True
                        ).first()
                        
                        if not record:
                            continue
                            
                        # Map JSON fields to Model fields
                        if 'material_type' in data: record.spill_type = data.get('material_type')
                        if 'surface_type' in data: record.surface_type = data.get('surface_type')
                        if 'location' in data: record.location = data.get('location')
                        if 'volume' in data: record.volume = data.get('volume')
                        if 'unit' in data: record.unit = data.get('unit')
                        if 'cleanup_costs' in data: record.cleanup_cost = data.get('cleanup_costs')
                        if record_year: record.record_year = str(record_year)
                        
                        record.updated_date = datetime.now()
                    else:
                        record = Gri306_3(
                            organization=organization_id,
                            created_by=user_id,
                            spill_type=data.get('material_type'),
                            surface_type=data.get('surface_type'),
                            location=data.get('location'),
                            volume=data.get('volume'),
                            unit=data.get('unit'),
                            cleanup_cost=data.get('cleanup_costs'),
                            record_year=str(record_year) if record_year else None
                        )
                        self.db.add(record)
                    
                    processed_records.append(record)
            
            self.db.commit()
            for record in processed_records:
                self.db.refresh(record)
            return [self._serialize_gri306_3(record) for record in processed_records]
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing GRI 306-3 records: {str(e)}")
            raise BadRequestException(f"Failed to process GRI 306-3 records: {str(e)}")

    def get_gri306_1_records(self, organization_id: int, record_year: Optional[str] = None) -> Dict[str, Any]:
        """
        Get GRI 306-1 records for an organization
        Aggregates transaction records by material and fetches GRI 306-1 manual entries
        """
        # --- Part 1: Aggregated Transaction Data ---
        # Base query for transactions
        query = (
            self.db.query(
                TransactionRecord.material_id,
                Material.name_th,
                Material.name_en,
                MaterialCategory.id.label('category_id'),
                MaterialCategory.name_en.label('category_name_en'),
                MaterialCategory.name_th.label('category_name_th'),
                func.sum(TransactionRecord.origin_quantity * Material.unit_weight).label('total_weight')
            )
            .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
            .join(Material, TransactionRecord.material_id == Material.id)
            .join(MaterialCategory, Material.category_id == MaterialCategory.id)
            .filter(
                Transaction.organization_id == organization_id,
                Transaction.is_active == True
            )
        )

        # Apply year filter if provided
        if record_year:
            # Extract year from transaction_date
            query = query.filter(func.to_char(Transaction.transaction_date, 'YYYY') == record_year)

        results = query.group_by(
            TransactionRecord.material_id,
            Material.name_th,
            Material.name_en,
            MaterialCategory.id,
            MaterialCategory.name_en,
            MaterialCategory.name_th
        ).all()
        
        # Process aggregated transaction data
        aggregated_data = []
        for row in results:
             aggregated_data.append({
                "material_id": row.material_id,
                "material_name": row.name_en or row.name_th,
                "category_id": row.category_id,
                "category_name": row.category_name_en or row.category_name_th,
                "value": float(row.total_weight) if row.total_weight else 0.0
            })

        # --- Part 2: Fetch GRI 306-1 Manual Entries ---
        gri_query = self.db.query(Gri306_1).filter(
            Gri306_1.organization == organization_id,
            Gri306_1.is_active == True
        )

        if record_year:
            gri_query = gri_query.filter(Gri306_1.record_year == record_year)

        gri_records = gri_query.order_by(desc(Gri306_1.created_date)).all()
        
        # Manually enrich records with material/category names
        gri_data = []
        for record in gri_records:
            serialized = self._serialize_gri306_1(record)
            self._enrich_gri_1_names(record, serialized)
            gri_data.append(serialized)

        # Return both sets of data
        return {
            "material_data": aggregated_data,
            "gri_records": gri_data
        }

    def get_gri306_2_records(self, organization_id: int, record_year: Optional[str] = None) -> Dict[str, Any]:
        """
        Get GRI 306-2 records joined with GRI 306-1
        """
        # 1. Get existing GRI 306-2 records
        query_2 = (
            self.db.query(Gri306_2)
            .join(Gri306_1, Gri306_2.approached_id == Gri306_1.id)
            .filter(
                Gri306_2.organization == organization_id,
                Gri306_2.is_active == True
            )
        )
        
        if record_year:
            query_2 = query_2.filter(Gri306_2.record_year == record_year)
            
        records_2 = query_2.order_by(desc(Gri306_2.created_date)).all()
        
        # 2. Get GRI 306-1 records that are NOT used in any active GRI 306-2
        query_1_unused = (
            self.db.query(Gri306_1)
            .outerjoin(
                Gri306_2, 
                (Gri306_1.id == Gri306_2.approached_id) & (Gri306_2.is_active == True)
            )
            .filter(
                Gri306_1.organization == organization_id,
                Gri306_1.is_active == True,
                Gri306_2.id == None # This ensures we only get records NOT in gri306_2
            )
        )
        
        if record_year:
            query_1_unused = query_1_unused.filter(Gri306_1.record_year == record_year)
            
        records_1_unused = query_1_unused.order_by(desc(Gri306_1.created_date)).all()
        
        # 3. Serialize and return combined data
        
        # Process GRI 2 records
        gri_2_data = []
        for record in records_2:
            serialized = self._serialize_gri306_2(record)
            if record.approached_item:
                self._enrich_gri_1_names(record.approached_item, serialized['approached_item'])
            gri_2_data.append(serialized)
            
        # Process Unused GRI 1 records
        gri_1_unused_data = []
        for record in records_1_unused:
            serialized = self._serialize_gri306_1(record)
            self._enrich_gri_1_names(record, serialized)
            gri_1_unused_data.append(serialized)
            
        return {
            "gri306_2_records": gri_2_data,
            "available_gri306_1_records": gri_1_unused_data
        }

    def get_gri306_3_records(self, organization_id: int, record_year: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get GRI 306-3 records
        """
        query = self.db.query(Gri306_3).filter(
            Gri306_3.organization == organization_id,
            Gri306_3.is_active == True
        )
        
        if record_year:
            query = query.filter(Gri306_3.record_year == record_year)
            
        records = query.order_by(desc(Gri306_3.created_date)).all()
        return [self._serialize_gri306_3(record) for record in records]

    def _enrich_gri_1_names(self, record, serialized_data):
        """Helper to enrich output material/category names in serialized data"""
        if record.output_material:
            material = self.db.query(Material).filter(Material.id == record.output_material).first()
            if material:
                serialized_data['output_material'] = {
                    "id": material.id,
                    "name_th": material.name_th,
                    "name_en": material.name_en
                }
        
        if record.output_category:
            category = self.db.query(MaterialCategory).filter(MaterialCategory.id == record.output_category).first()
            if category:
                serialized_data['output_category'] = {
                    "id": category.id,
                    "name_th": category.name_th,
                    "name_en": category.name_en
                }

    def _serialize_gri306_1(self, record: Gri306_1) -> Dict[str, Any]:
        """Serialize GRI 306-1 record"""
        return {
            "id": record.id,
            "input_material": record.input_material,
            "activity": record.activity,
            "output_material": record.output_material,
            "output_category": record.output_category,
            "method": record.method,
            "onsite": record.onsite,
            "weight": float(record.weight) if record.weight else 0.0,
            "description": record.description,
            "record_year": record.record_year,
            "organization": record.organization,
            "created_by": record.created_by,
            "created_date": record.created_date.isoformat() if record.created_date else None
        }

    def _serialize_gri306_2(self, record: Gri306_2) -> Dict[str, Any]:
        """Serialize GRI 306-2 record including 306-1 data"""
        prev_action = record.prevention_action.split(", ") if record.prevention_action else []
        ver_method = record.verify_method.split(", ") if record.verify_method else []
        
        data = {
            "id": record.id,
            "approached_id": record.approached_id,
            "prevention_action": prev_action,
            "verify_method": ver_method,
            "collection_method": record.collection_method,
            "record_year": record.record_year,
            "created_date": record.created_date.isoformat() if record.created_date else None,
            "updated_date": record.updated_date.isoformat() if record.updated_date else None
        }
        
        if record.approached_item:
            gri1_data = self._serialize_gri306_1(record.approached_item)
            data["approached_item"] = gri1_data
            
        return data

    def _serialize_gri306_3(self, record: Gri306_3) -> Dict[str, Any]:
        """Serialize GRI 306-3 record"""
        return {
            "id": record.id,
            "material_type": record.spill_type, # mapped back to json format
            "surface_type": record.surface_type,
            "location": record.location,
            "volume": float(record.volume) if record.volume else 0.0,
            "unit": record.unit,
            "cleanup_costs": float(record.cleanup_cost) if record.cleanup_cost else 0.0,
            "record_year": record.record_year,
            "organization": record.organization,
            "created_by": record.created_by,
            "created_date": record.created_date.isoformat() if record.created_date else None
        }
