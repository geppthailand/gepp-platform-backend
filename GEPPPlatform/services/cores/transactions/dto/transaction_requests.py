"""
Transaction Request DTOs
Data transfer objects for transaction-related API requests
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .....services.base_dto import BaseDTO


@dataclass
class CreateTransactionRecordRequest(BaseDTO):
    """DTO for creating a transaction record"""
    main_material_id: int
    category_id: int
    unit: str
    origin_quantity: float = 0
    origin_weight_kg: float = 0
    origin_price_per_unit: float = 0
    total_amount: Optional[float] = None

    # Optional fields
    status: str = 'pending'
    transaction_type: str = 'manual_input'
    material_id: Optional[int] = None
    tags: List[List[int]] = None  # [(tag_group_id, tag_id), ...]
    currency_id: Optional[int] = None
    notes: Optional[str] = None
    images: List[str] = None
    origin_coordinates: Optional[Dict[str, float]] = None  # {lat: float, lng: float}
    destination_coordinates: Optional[Dict[str, float]] = None
    hazardous_level: int = 0
    treatment_method: Optional[str] = None
    disposal_method: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.images is None:
            self.images = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API processing"""
        return {
            'status': self.status,
            'transaction_type': self.transaction_type,
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
            'disposal_method': self.disposal_method
        }

    def validate(self) -> List[str]:
        """Validate request data"""
        errors = []

        # Required fields
        if not self.main_material_id:
            errors.append('main_material_id is required')
        if not self.category_id:
            errors.append('category_id is required')
        if not self.unit:
            errors.append('unit is required')

        # Validate numeric fields
        if self.origin_quantity < 0:
            errors.append('origin_quantity must be non-negative')
        if self.origin_weight_kg < 0:
            errors.append('origin_weight_kg must be non-negative')
        if self.origin_price_per_unit < 0:
            errors.append('origin_price_per_unit must be non-negative')
        if self.total_amount is not None and self.total_amount < 0:
            errors.append('total_amount must be non-negative')

        # Validate hazardous level
        if not isinstance(self.hazardous_level, int) or self.hazardous_level < 0 or self.hazardous_level > 5:
            errors.append('hazardous_level must be an integer between 0 and 5')

        # Validate transaction type
        valid_types = ['manual_input', 'rewards', 'iot']
        if self.transaction_type not in valid_types:
            errors.append(f'transaction_type must be one of: {", ".join(valid_types)}')

        return errors


@dataclass
class CreateTransactionRequest(BaseDTO):
    """DTO for creating a new transaction"""
    origin_id: int

    # Optional fields
    transaction_method: str = 'origin'
    status: str = 'pending'
    destination_id: Optional[int] = None
    transaction_date: Optional[datetime] = None
    arrival_date: Optional[datetime] = None
    origin_coordinates: Optional[Dict[str, float]] = None  # {lat: float, lng: float}
    destination_coordinates: Optional[Dict[str, float]] = None
    notes: Optional[str] = None
    images: List[str] = None
    vehicle_info: Optional[Dict[str, Any]] = None
    driver_info: Optional[Dict[str, Any]] = None
    hazardous_level: int = 0
    treatment_method: Optional[str] = None
    disposal_method: Optional[str] = None

    # Transaction records to create with this transaction
    transaction_records: List[CreateTransactionRecordRequest] = None

    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.transaction_records is None:
            self.transaction_records = []
        if self.transaction_date is None:
            self.transaction_date = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API processing"""
        return {
            'origin_id': self.origin_id,
            'transaction_method': self.transaction_method,
            'status': self.status,
            'destination_id': self.destination_id,
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
            'disposal_method': self.disposal_method
        }

    def validate(self) -> List[str]:
        """Validate request data"""
        errors = []

        # Required fields
        if not self.origin_id:
            errors.append('origin_id is required')

        # Validate transaction method
        valid_methods = ['origin', 'transport', 'transform', 'qr_input', 'scale_input']
        if self.transaction_method not in valid_methods:
            errors.append(f'transaction_method must be one of: {", ".join(valid_methods)}')

        # Validate status
        valid_statuses = ['pending', 'scheduled', 'in_progress', 'in_transit', 'delivered', 'completed', 'cancelled', 'rejected']
        if self.status not in valid_statuses:
            errors.append(f'status must be one of: {", ".join(valid_statuses)}')

        # Validate hazardous level
        if not isinstance(self.hazardous_level, int) or self.hazardous_level < 0 or self.hazardous_level > 5:
            errors.append('hazardous_level must be an integer between 0 and 5')

        # Validate transaction records
        for i, record in enumerate(self.transaction_records):
            record_errors = record.validate()
            for error in record_errors:
                errors.append(f'Transaction record {i + 1}: {error}')

        return errors


@dataclass
class UpdateTransactionRequest(BaseDTO):
    """DTO for updating an existing transaction"""

    # Optional fields (only include what can be updated)
    transaction_method: Optional[str] = None
    status: Optional[str] = None
    destination_id: Optional[int] = None
    arrival_date: Optional[datetime] = None
    destination_coordinates: Optional[Dict[str, float]] = None
    notes: Optional[str] = None
    images: Optional[List[str]] = None
    vehicle_info: Optional[Dict[str, Any]] = None
    driver_info: Optional[Dict[str, Any]] = None
    hazardous_level: Optional[int] = None
    treatment_method: Optional[str] = None
    disposal_method: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API processing"""
        data = {}

        # Only include non-None values
        if self.transaction_method is not None:
            data['transaction_method'] = self.transaction_method
        if self.status is not None:
            data['status'] = self.status
        if self.destination_id is not None:
            data['destination_id'] = self.destination_id
        if self.arrival_date is not None:
            data['arrival_date'] = self.arrival_date
        if self.destination_coordinates is not None:
            data['destination_coordinates'] = self.destination_coordinates
        if self.notes is not None:
            data['notes'] = self.notes
        if self.images is not None:
            data['images'] = self.images
        if self.vehicle_info is not None:
            data['vehicle_info'] = self.vehicle_info
        if self.driver_info is not None:
            data['driver_info'] = self.driver_info
        if self.hazardous_level is not None:
            data['hazardous_level'] = self.hazardous_level
        if self.treatment_method is not None:
            data['treatment_method'] = self.treatment_method
        if self.disposal_method is not None:
            data['disposal_method'] = self.disposal_method

        return data

    def validate(self) -> List[str]:
        """Validate request data"""
        errors = []

        # Validate transaction method if provided
        if self.transaction_method is not None:
            valid_methods = ['origin', 'transport', 'transform', 'qr_input', 'scale_input']
            if self.transaction_method not in valid_methods:
                errors.append(f'transaction_method must be one of: {", ".join(valid_methods)}')

        # Validate status if provided
        if self.status is not None:
            valid_statuses = ['pending', 'scheduled', 'in_progress', 'in_transit', 'delivered', 'completed', 'cancelled', 'rejected']
            if self.status not in valid_statuses:
                errors.append(f'status must be one of: {", ".join(valid_statuses)}')

        # Validate hazardous level if provided
        if self.hazardous_level is not None:
            if not isinstance(self.hazardous_level, int) or self.hazardous_level < 0 or self.hazardous_level > 5:
                errors.append('hazardous_level must be an integer between 0 and 5')

        return errors