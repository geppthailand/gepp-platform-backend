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

    def create_gri306_1_records(self, organization_id: int, user_id: int, records_data: List[Dict[str, Any]], delete_records: List[int] = None, affected_ids: List[int] = None, global_year: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Create, update, or delete multiple GRI 306-1 records in bulk
        Also cascades soft delete to linked GRI 306-2 records
        and can clear management fields in GRI 306-2 when 306-1 records are affected.
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

            # 2. Handle affected_ids: clear related management fields in GRI 306-2
            if affected_ids:
                gri2_to_clear = (
                    self.db.query(Gri306_2)
                    .filter(
                        Gri306_2.organization == organization_id,
                        Gri306_2.is_active == True,
                        Gri306_2.approached_id.in_(affected_ids),
                    )
                    .all()
                )

                for g2 in gri2_to_clear:
                    g2.prevention_action = None
                    g2.verify_method = None
                    g2.collection_method = None
                    g2.updated_date = datetime.now()

            # 3. Handle Create/Update
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
                        if 'value_chain_position' in data: record.value_chain_position = data.get('value_chain_position')
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
                            value_chain_position=data.get('value_chain_position'),
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
        Create, update, or delete multiple GRI 306-2 records in bulk
        Also cascades soft delete to linked GRI 306-1 records
        """
        processed_records = []
        try:
            # 1. Handle Deletions - Logic restored for robustness if needed, but not strictly required by user
            # If delete_records is sent, we process it.
            if delete_records:
                for del_id in delete_records:
                    record_to_delete = self.db.query(Gri306_2).filter(
                        Gri306_2.approached_id == del_id,
                        Gri306_2.organization == organization_id,
                        Gri306_2.is_active == True
                    ).first()
                    
                    if record_to_delete:
                        record_to_delete.is_active = False
                        record_to_delete.deleted_date = datetime.now()
                        
                        # CASCADE DELETE to GRI 306-1
                        if record_to_delete.approached_id:
                            linked_gri1 = self.db.query(Gri306_1).filter(
                                Gri306_1.id == record_to_delete.approached_id,
                                Gri306_1.organization == organization_id,
                                Gri306_1.is_active == True
                            ).first()
                            
                            if linked_gri1:
                                linked_gri1.is_active = False
                                linked_gri1.deleted_date = datetime.now()

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
                    record_year = data.get('record_year') or global_year or data.get('year')
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
            # Ensure record_year is a string for comparison with to_char result
            record_year_str = str(record_year) if record_year else None
            query = query.filter(func.to_char(Transaction.transaction_date, 'YYYY') == record_year_str)

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
            # Ensure record_year is a string for comparison with String column
            record_year_str = str(record_year) if record_year else None
            gri_query = gri_query.filter(Gri306_1.record_year == record_year_str)

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

    def get_gri306_2_records(self, organization_id: int, record_year: Optional[str] = None, approached_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Get GRI 306-2 records joined with GRI 306-1
        Optionally filter by approached_ids (GRI 306-1 IDs)
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
            # Ensure record_year is a string for comparison with String column
            record_year_str = str(record_year) if record_year else None
            query_2 = query_2.filter(Gri306_2.record_year == record_year_str)
            
        if approached_ids:
            query_2 = query_2.filter(Gri306_2.approached_id.in_(approached_ids))
            
        records_2 = query_2.order_by(desc(Gri306_2.created_date)).all()
        
        # 2. Get GRI 306-1 records that are NOT used in any active GRI 306-2
        # If approached_ids provided, only show those specific IDs
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
            # Ensure record_year is a string for comparison with String column
            record_year_str = str(record_year) if record_year else None
            query_1_unused = query_1_unused.filter(Gri306_1.record_year == record_year_str)
            
        if approached_ids:
            query_1_unused = query_1_unused.filter(Gri306_1.id.in_(approached_ids))
            
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
            # Ensure record_year is a string for comparison with String column
            record_year_str = str(record_year) if record_year else None
            query = query.filter(Gri306_3.record_year == record_year_str)
            
        records = query.order_by(desc(Gri306_3.created_date)).all()
        return [self._serialize_gri306_3(record) for record in records]

    def get_gri_export_data(self, organization_id: int, record_year: str, version_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get aggregated GRI export data for all standards
        """
        return {
            "organization_id": organization_id,
            "year": record_year,
            "version_name": version_name,
            "generated_at": datetime.now().isoformat(),
            "gri306_1": self.get_gri306_1_records(organization_id, record_year),
            "gri306_2": self.get_gri306_2_records(organization_id, record_year),
            "gri306_3": self.get_gri306_3_records(organization_id, record_year)
        }

    def calculate_gri_export_data(self, organization_id: int, record_year: Optional[str] = None, gri_1_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Calculate GRI export data:
        - Waste Generated: Total weight from GRI-1
        - Diverted from Disposal: Sum of weights by method
        - Directed to Disposal: Sum of weights by method
        - Total Spills: Sum of volumes from GRI-3
        - Waste Composition: Breakdown by material category
        
        Args:
            organization_id: Organization ID
            record_year: Optional year filter
            gri_1_ids: Optional list of GRI-1 IDs to filter by. If None, uses all records. If empty list, skips GRI-1 data entirely.
        """
        WASTE_MANAGEMENT_GROUPS = {
            "Diverted from Disposal": [
                "Preparation for reuse",
                "Recycling (Own)",
                "Other recover operation",
                "Recycle",
            ],
            "Directed to Disposal": [
                "Composted by municipality",
                "Municipality receive",
                "Incineration without energy",
                "Incineration with energy",
            ],
        }

        # Get GRI-3 data (always fetched, independent of GRI-1)
        gri306_3_data = self.get_gri306_3_records(organization_id, record_year)
        
        # Handle GRI-1 data based on gri_1_ids
        if gri_1_ids is None or len(gri_1_ids) == 0:
            # None or empty list means skip GRI-1 data entirely
            gri_records = []
        else:
            # Get GRI-1 data and filter by provided IDs
            gri306_1_data = self.get_gri306_1_records(organization_id, record_year)
            all_gri_records = gri306_1_data.get("gri_records", [])
            
            # Filter by provided GRI-1 IDs
            gri_1_ids_set = set(gri_1_ids)
            gri_records = [record for record in all_gri_records if record.get("id") in gri_1_ids_set]
        
        # Total weight from filtered GRI records
        total_gri_weight = sum(record.get("weight", 0.0) for record in gri_records)
        
        # Waste Generated = total from filtered GRI records
        waste_generated = total_gri_weight
        
        # Group by method: Diverted vs Directed
        diverted_weight = 0.0
        directed_weight = 0.0
        
        # Waste composition by category
        category_composition = {}
        
        # Process GRI records by category
        for record in gri_records:
            method = record.get("method", "")
            weight = record.get("weight", 0.0) or 0.0
            
            # Get category from record
            output_category = record.get("output_category")
            category_name = "Unknown"
            
            # Try to get category name from enriched data
            if isinstance(output_category, dict):
                category_id = output_category.get("id")
                category_name = output_category.get("name_en") or output_category.get("name_th") or "Unknown"
            elif output_category:
                category_id = output_category
                # Fetch category name from database
                category = self.db.query(MaterialCategory).filter(MaterialCategory.id == category_id).first()
                if category:
                    category_name = category.name_en or category.name_th or "Unknown"
            else:
                category_id = None
            
            # Add to totals
            if method in WASTE_MANAGEMENT_GROUPS["Diverted from Disposal"]:
                diverted_weight += weight
            elif method in WASTE_MANAGEMENT_GROUPS["Directed to Disposal"]:
                directed_weight += weight
            
            # Add to category composition
            if category_id:
                key = f"{category_id}"
                if key not in category_composition:
                    category_composition[key] = {
                        "category_id": category_id,
                        "category_name": category_name,
                        "generated": 0.0,
                        "diverted": 0.0,
                        "directed": 0.0
                    }
                else:
                    # Update category name if we have a better one and it was "Unknown"
                    if category_composition[key]["category_name"] == "Unknown" and category_name != "Unknown":
                        category_composition[key]["category_name"] = category_name
                
                category_composition[key]["generated"] += weight
                
                if method in WASTE_MANAGEMENT_GROUPS["Diverted from Disposal"]:
                    category_composition[key]["diverted"] += weight
                elif method in WASTE_MANAGEMENT_GROUPS["Directed to Disposal"]:
                    category_composition[key]["directed"] += weight
        
        # Calculate totals for all categories
        total_category_generated = sum(cat["generated"] for cat in category_composition.values())
        total_category_diverted = sum(cat["diverted"] for cat in category_composition.values())
        total_category_directed = sum(cat["directed"] for cat in category_composition.values())
        
        # Total spills = sum of volumes from GRI-3
        total_spills = sum(record.get("volume", 0.0) or 0.0 for record in gri306_3_data)
        
        # Calculate diverted_data by hazardous/non-hazardous
        diverted_data = {
            "hazardous": {},
            "non_hazardous": {}
        }
        
        # Initialize all diverted methods for both categories
        for method in WASTE_MANAGEMENT_GROUPS["Diverted from Disposal"]:
            diverted_data["hazardous"][method] = {
                "onsite": 0.0,
                "offsite": 0.0,
                "total": 0.0
            }
            diverted_data["non_hazardous"][method] = {
                "onsite": 0.0,
                "offsite": 0.0,
                "total": 0.0
            }
        
        # Helper function to check if category is hazardous
        # Hazardous categories: "Hazardous Waste", "Bio-Hazardous Waste"
        # All other categories are non-hazardous
        def is_hazardous_category(category_name):
            if not category_name:
                return False
            category_name_lower = category_name.lower().strip()
            # Check for exact hazardous category names
            return (
                category_name_lower == "hazardous waste" or
                category_name_lower == "bio-hazardous waste"
            )
        
        # Process GRI records for diverted_data
        for record in gri_records:
            method = record.get("method", "")
            weight = record.get("weight", 0.0) or 0.0
            onsite = record.get("onsite", False)
            
            # Only process diverted methods
            if method not in WASTE_MANAGEMENT_GROUPS["Diverted from Disposal"]:
                continue
            
            # Get category from record
            output_category = record.get("output_category")
            category_name = "Unknown"
            
            # Try to get category name from enriched data
            if isinstance(output_category, dict):
                category_name = output_category.get("name_en") or output_category.get("name_th") or "Unknown"
            elif output_category:
                # Fetch category name from database
                category = self.db.query(MaterialCategory).filter(MaterialCategory.id == output_category).first()
                if category:
                    category_name = category.name_en or category.name_th or "Unknown"
            
            # Determine if hazardous or non-hazardous
            is_hazardous = is_hazardous_category(category_name)
            category_key = "hazardous" if is_hazardous else "non_hazardous"
            
            # Add to diverted_data
            if method in diverted_data[category_key]:
                if onsite:
                    diverted_data[category_key][method]["onsite"] += weight
                else:
                    diverted_data[category_key][method]["offsite"] += weight
                diverted_data[category_key][method]["total"] += weight
        
        # Convert to float for all values
        for category_key in ["hazardous", "non_hazardous"]:
            for method in diverted_data[category_key]:
                diverted_data[category_key][method]["onsite"] = float(diverted_data[category_key][method]["onsite"])
                diverted_data[category_key][method]["offsite"] = float(diverted_data[category_key][method]["offsite"])
                diverted_data[category_key][method]["total"] = float(diverted_data[category_key][method]["total"])
        
        # Calculate directed_data by hazardous/non-hazardous
        directed_data = {
            "hazardous": {},
            "non_hazardous": {}
        }
        
        # Initialize all directed methods for both categories
        for method in WASTE_MANAGEMENT_GROUPS["Directed to Disposal"]:
            directed_data["hazardous"][method] = {
                "onsite": 0.0,
                "offsite": 0.0,
                "total": 0.0
            }
            directed_data["non_hazardous"][method] = {
                "onsite": 0.0,
                "offsite": 0.0,
                "total": 0.0
            }
        
        # Process GRI records for directed_data
        for record in gri_records:
            method = record.get("method", "")
            weight = record.get("weight", 0.0) or 0.0
            onsite = record.get("onsite", False)
            
            # Only process directed methods
            if method not in WASTE_MANAGEMENT_GROUPS["Directed to Disposal"]:
                continue
            
            # Get category from record
            output_category = record.get("output_category")
            category_name = "Unknown"
            
            # Try to get category name from enriched data
            if isinstance(output_category, dict):
                category_name = output_category.get("name_en") or output_category.get("name_th") or "Unknown"
            elif output_category:
                # Fetch category name from database
                category = self.db.query(MaterialCategory).filter(MaterialCategory.id == output_category).first()
                if category:
                    category_name = category.name_en or category.name_th or "Unknown"
            
            # Determine if hazardous or non-hazardous
            is_hazardous = is_hazardous_category(category_name)
            category_key = "hazardous" if is_hazardous else "non_hazardous"
            
            # Add to directed_data
            if method in directed_data[category_key]:
                if onsite:
                    directed_data[category_key][method]["onsite"] += weight
                else:
                    directed_data[category_key][method]["offsite"] += weight
                directed_data[category_key][method]["total"] += weight
        
        # Convert to float for all values
        for category_key in ["hazardous", "non_hazardous"]:
            for method in directed_data[category_key]:
                directed_data[category_key][method]["onsite"] = float(directed_data[category_key][method]["onsite"])
                directed_data[category_key][method]["offsite"] = float(directed_data[category_key][method]["offsite"])
                directed_data[category_key][method]["total"] = float(directed_data[category_key][method]["total"])
        
        # Map spill data from GRI-3
        spill_data = []
        total_spill_volume = 0.0
        total_spill_cleanup_cost = 0.0
        
        for record in gri306_3_data:
            spill_record = {
                "spill_type": record.get("material_type", ""),
                "surface_type": record.get("surface_type", ""),
                "location": record.get("location", ""),
                "volume": float(record.get("volume", 0.0) or 0.0),
                "cleanup_cost": float(record.get("cleanup_costs", 0.0) or 0.0)
            }
            spill_data.append(spill_record)
            
            # Add to totals
            total_spill_volume += spill_record["volume"]
            total_spill_cleanup_cost += spill_record["cleanup_cost"]
        
        return {
            "organization_id": organization_id,
            "year": record_year,
            "table_summary": {
                "waste_generated": float(waste_generated),
                "diverted_from_disposal": float(diverted_weight),
                "directed_to_disposal": float(directed_weight),
                "total_spills": float(total_spills)
            },
            "waste_composition": {
                "categories": [
                    {
                        "category_id": cat["category_id"],
                        "category_name": cat["category_name"],
                        "generated": float(cat["generated"]),
                        "diverted": float(cat["diverted"]),
                        "directed": float(cat["directed"])
                    }
                    for cat in category_composition.values()
                ],
                "totals": {
                    "generated": float(total_category_generated),
                    "diverted": float(total_category_diverted),
                    "directed": float(total_category_directed)
                }
            },
            "diverted_data": diverted_data,
            "directed_data": directed_data,
            "spill_data": {
                "records": spill_data,
                "totals": {
                    "total_volume": float(total_spill_volume),
                    "total_cleanup_cost": float(total_spill_cleanup_cost)
                }
            }
        }

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
            "value_chain_position": record.value_chain_position,
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

    def _generate_view_presigned_url(
        self,
        s3_url: str,
        organization_id: int,
        user_id: int,
        expiration_seconds: int = 3600
    ) -> str:
        """
        Generate a presigned URL for viewing an S3 file
        Similar to UserService._generate_view_presigned_url

        Args:
            s3_url: The S3 URL to generate a presigned URL for
            organization_id: Organization ID for access control
            user_id: User ID for audit trail
            expiration_seconds: URL expiration time (default: 1 hour)

        Returns:
            Presigned URL string for viewing the file
        """
        try:
            from ..transactions.presigned_url_service import TransactionPresignedUrlService

            # Initialize presigned URL service
            presigned_service = TransactionPresignedUrlService()

            # Generate presigned URL for viewing
            result = presigned_service.get_transaction_file_view_presigned_urls(
                file_urls=[s3_url],
                organization_id=organization_id,
                user_id=user_id,
                expiration_seconds=expiration_seconds
            )

            if result.get('success') and result.get('presigned_urls'):
                return result['presigned_urls'][0]['view_url']
            else:
                # If presigned URL generation fails, return original URL
                # (fallback for public files or development)
                return s3_url

        except Exception as e:
            # If there's an error, log it and return the original URL
            logger.warning(f"Error generating presigned URL for viewing: {str(e)}")
            return s3_url