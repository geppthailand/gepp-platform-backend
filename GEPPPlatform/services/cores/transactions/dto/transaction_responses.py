"""
Transaction Response DTOs
Data transfer objects for transaction-related API responses
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .....services.base_dto import BaseDTO, PaginationMeta


@dataclass
class TransactionRecordResponse(BaseDTO):
    """DTO for transaction record response data"""
    id: int
    status: str
    created_transaction_id: int
    traceability: List[int]
    transaction_type: str
    transaction_type_id: Optional[int]
    material_id: Optional[int]
    main_material_id: int
    category_id: int
    tags: List[List[int]]
    unit: str
    origin_quantity: float
    origin_weight_kg: float
    origin_price_per_unit: float
    total_amount: float
    currency_id: Optional[int]
    notes: Optional[str]
    images: List[str]
    origin_coordinates: Optional[Dict[str, float]]
    destination_coordinates: Optional[Dict[str, float]]
    hazardous_level: int
    treatment_method: Optional[str]
    disposal_method: Optional[str]
    created_by_id: int
    approved_by_id: Optional[int]
    completed_date: Optional[str]  # ISO format
    is_active: bool
    created_date: str  # ISO format
    updated_date: str  # ISO format
    deleted_date: Optional[str]  # ISO format

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'status': self.status,
            'created_transaction_id': self.created_transaction_id,
            'traceability': self.traceability,
            'transaction_type': self.transaction_type,
            'transaction_type_id': self.transaction_type_id,
            'material_id': self.material_id,
            'main_material_id': self.main_material_id,
            'category_id': self.category_id,
            'tags': self.tags,
            'unit': self.unit,
            'origin_quantity': self.origin_quantity,
            'origin_weight_kg': self.origin_weight_kg,
            'origin_price_per_unit': self.origin_price_per_unit,
            'total_amount': self.total_amount,
            'currency_id': self.currency_id,
            'notes': self.notes,
            'images': self.images,
            'origin_coordinates': self.origin_coordinates,
            'destination_coordinates': self.destination_coordinates,
            'hazardous_level': self.hazardous_level,
            'treatment_method': self.treatment_method,
            'disposal_method': self.disposal_method,
            'created_by_id': self.created_by_id,
            'approved_by_id': self.approved_by_id,
            'completed_date': self.completed_date,
            'is_active': self.is_active,
            'created_date': self.created_date,
            'updated_date': self.updated_date,
            'deleted_date': self.deleted_date
        }

    def validate(self) -> List[str]:
        """Validate response data"""
        return []  # Response DTOs typically don't need validation

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransactionRecordResponse':
        """Create instance from service response data"""
        return cls(
            id=data['id'],
            status=data['status'],
            created_transaction_id=data['created_transaction_id'],
            traceability=data.get('traceability', []),
            transaction_type=data['transaction_type'],
            transaction_type_id=data.get('transaction_type_id'),
            material_id=data.get('material_id'),
            main_material_id=data['main_material_id'],
            category_id=data['category_id'],
            tags=data.get('tags', []),
            unit=data['unit'],
            origin_quantity=data.get('origin_quantity', 0),
            origin_weight_kg=data.get('origin_weight_kg', 0),
            origin_price_per_unit=data.get('origin_price_per_unit', 0),
            total_amount=data.get('total_amount', 0),
            currency_id=data.get('currency_id'),
            notes=data.get('notes'),
            images=data.get('images', []),
            origin_coordinates=data.get('origin_coordinates'),
            destination_coordinates=data.get('destination_coordinates'),
            hazardous_level=data.get('hazardous_level', 0),
            treatment_method=data.get('treatment_method'),
            disposal_method=data.get('disposal_method'),
            created_by_id=data['created_by_id'],
            approved_by_id=data.get('approved_by_id'),
            completed_date=data.get('completed_date'),
            is_active=data.get('is_active', True),
            created_date=data.get('created_date'),
            updated_date=data.get('updated_date'),
            deleted_date=data.get('deleted_date')
        )


@dataclass
class TransactionResponse(BaseDTO):
    """DTO for transaction response data"""
    id: int
    transaction_records: List[int]
    transaction_method: str
    transaction_method_id: Optional[int]
    status: str
    organization_id: int
    origin_id: int
    destination_id: Optional[int]
    weight_kg: float
    total_amount: float
    transaction_date: str  # ISO format
    arrival_date: Optional[str]  # ISO format
    origin_coordinates: Optional[Dict[str, float]]
    destination_coordinates: Optional[Dict[str, float]]
    notes: Optional[str]
    images: List[str]
    vehicle_info: Optional[Dict[str, Any]]
    driver_info: Optional[Dict[str, Any]]
    hazardous_level: int
    treatment_method: Optional[str]
    disposal_method: Optional[str]
    created_by_id: int
    updated_by_id: Optional[int]
    approved_by_id: Optional[int]
    is_active: bool
    created_date: str  # ISO format
    updated_date: str  # ISO format
    deleted_date: Optional[str]  # ISO format

    # Optional: Include transaction record details if requested
    records: Optional[List[TransactionRecordResponse]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        data = {
            'id': self.id,
            'transaction_records': self.transaction_records,
            'transaction_method': self.transaction_method,
            'transaction_method_id': self.transaction_method_id,
            'status': self.status,
            'organization_id': self.organization_id,
            'origin_id': self.origin_id,
            'destination_id': self.destination_id,
            'weight_kg': self.weight_kg,
            'total_amount': self.total_amount,
            'transaction_date': self.transaction_date,
            'arrival_date': self.arrival_date,
            'origin_coordinates': self.origin_coordinates,
            'destination_coordinates': self.destination_coordinates,
            'notes': self.notes,
            'images': self.images,
            'vehicle_info': self.vehicle_info,
            'driver_info': self.driver_info,
            'hazardous_level': self.hazardous_level,
            'treatment_method': self.treatment_method,
            'disposal_method': self.disposal_method,
            'created_by_id': self.created_by_id,
            'updated_by_id': self.updated_by_id,
            'approved_by_id': self.approved_by_id,
            'is_active': self.is_active,
            'created_date': self.created_date,
            'updated_date': self.updated_date,
            'deleted_date': self.deleted_date
        }

        # Include records if present
        if self.records is not None:
            data['records'] = [record.to_dict() for record in self.records]

        return data

    def validate(self) -> List[str]:
        """Validate response data"""
        return []  # Response DTOs typically don't need validation

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransactionResponse':
        """Create instance from service response data"""
        # Convert record data if present
        records = None
        if 'records' in data:
            records = [TransactionRecordResponse.from_dict(record) for record in data['records']]

        return cls(
            id=data['id'],
            transaction_records=data.get('transaction_records', []),
            transaction_method=data['transaction_method'],
            transaction_method_id=data.get('transaction_method_id'),
            status=data['status'],
            organization_id=data['organization_id'],
            origin_id=data['origin_id'],
            destination_id=data.get('destination_id'),
            weight_kg=data.get('weight_kg', 0),
            total_amount=data.get('total_amount', 0),
            transaction_date=data.get('transaction_date'),
            arrival_date=data.get('arrival_date'),
            origin_coordinates=data.get('origin_coordinates'),
            destination_coordinates=data.get('destination_coordinates'),
            notes=data.get('notes'),
            images=data.get('images', []),
            vehicle_info=data.get('vehicle_info'),
            driver_info=data.get('driver_info'),
            hazardous_level=data.get('hazardous_level', 0),
            treatment_method=data.get('treatment_method'),
            disposal_method=data.get('disposal_method'),
            created_by_id=data['created_by_id'],
            updated_by_id=data.get('updated_by_id'),
            approved_by_id=data.get('approved_by_id'),
            is_active=data.get('is_active', True),
            created_date=data.get('created_date'),
            updated_date=data.get('updated_date'),
            deleted_date=data.get('deleted_date'),
            records=records
        )


@dataclass
class TransactionListResponse(BaseDTO):
    """DTO for paginated transaction list response"""
    transactions: List[TransactionResponse]
    pagination: PaginationMeta

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'transactions': [transaction.to_dict() for transaction in self.transactions],
            'pagination': self.pagination.to_dict()
        }

    def validate(self) -> List[str]:
        """Validate response data"""
        return []  # Response DTOs typically don't need validation

    @classmethod
    def from_service_response(cls, service_result: Dict[str, Any]) -> 'TransactionListResponse':
        """Create instance from service response data"""
        transactions = [
            TransactionResponse.from_dict(transaction_data)
            for transaction_data in service_result['transactions']
        ]

        pagination_data = service_result['pagination']
        pagination = PaginationMeta(
            page=pagination_data['page'],
            page_size=pagination_data['page_size'],
            total=pagination_data['total'],
            pages=pagination_data['pages'],
            has_next=pagination_data['has_next'],
            has_prev=pagination_data['has_prev']
        )

        return cls(
            transactions=transactions,
            pagination=pagination
        )