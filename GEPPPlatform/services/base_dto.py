"""
Base DTO Classes and Utilities
Common data transfer object patterns and validation utilities
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime
import json


class BaseDTO(ABC):
    """
    Abstract base class for all DTOs
    Provides common functionality for data transfer objects
    """

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary for API responses or database operations"""
        pass

    def to_json(self) -> str:
        """Convert DTO to JSON string"""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Create DTO instance from dictionary"""
        # Filter out None values and unknown fields
        valid_fields = {k: v for k, v in data.items()
                       if v is not None and k in cls.__annotations__}
        return cls(**valid_fields)

    def validate(self) -> List[str]:
        """Validate DTO data and return list of error messages"""
        errors = []
        # Override in subclasses for specific validation logic
        return errors

    def is_valid(self) -> bool:
        """Check if DTO data is valid"""
        return len(self.validate()) == 0


@dataclass
class PaginationMeta:
    """Standard pagination metadata"""
    page: int
    size: int
    total: int
    has_more: bool
    total_pages: Optional[int] = None

    def __post_init__(self):
        if self.total_pages is None:
            self.total_pages = (self.total + self.size - 1) // self.size if self.size > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'page': self.page,
            'size': self.size,
            'total': self.total,
            'hasMore': self.has_more,
            'totalPages': self.total_pages
        }


@dataclass
class ApiResponseDTO:
    """
    Standard API response format DTO
    Maps to frontend ApiResponse interface
    """
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    errors: Optional[List[str]] = None
    meta: Optional[PaginationMeta] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {'success': self.success}

        if self.data is not None:
            # Handle different data types
            if hasattr(self.data, 'to_dict'):
                result['data'] = self.data.to_dict()
            elif isinstance(self.data, list):
                result['data'] = [
                    item.to_dict() if hasattr(item, 'to_dict') else item
                    for item in self.data
                ]
            else:
                result['data'] = self.data

        if self.message:
            result['message'] = self.message
        if self.errors:
            result['errors'] = self.errors
        if self.meta:
            result['meta'] = self.meta.to_dict()

        return result


@dataclass
class ErrorDTO:
    """Standard error response DTO"""
    code: str
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'code': self.code,
            'message': self.message
        }
        if self.field:
            result['field'] = self.field
        if self.details:
            result['details'] = self.details
        return result


class DTOValidationMixin:
    """Mixin class providing common validation methods"""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format"""
        import re
        # Thai phone number pattern
        pattern = r'^(\+66|0)[0-9]{8,9}$'
        return bool(re.match(pattern, phone.replace('-', '').replace(' ', '')))

    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
        """Validate that required fields are present and not empty"""
        errors = []
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                errors.append(f"Field '{field}' is required")
        return errors

    @staticmethod
    def validate_date_format(date_str: str, format_str: str = "%Y-%m-%d") -> bool:
        """Validate date string format"""
        try:
            datetime.strptime(date_str, format_str)
            return True
        except ValueError:
            return False


class DTOFactory:
    """Factory class for creating DTOs from various data sources"""

    @staticmethod
    def create_success_response(data: Any, message: str = None, meta: PaginationMeta = None) -> ApiResponseDTO:
        """Create a successful API response DTO"""
        return ApiResponseDTO(
            success=True,
            data=data,
            message=message,
            meta=meta
        )

    @staticmethod
    def create_error_response(errors: List[str], message: str = "Operation failed") -> ApiResponseDTO:
        """Create an error API response DTO"""
        return ApiResponseDTO(
            success=False,
            message=message,
            errors=errors
        )

    @staticmethod
    def create_pagination_meta(page: int, size: int, total: int) -> PaginationMeta:
        """Create pagination metadata"""
        has_more = (page * size) < total
        return PaginationMeta(
            page=page,
            size=size,
            total=total,
            has_more=has_more
        )


# Utility functions for DTO operations
def sanitize_dict(data: Dict[str, Any], allowed_keys: List[str] = None) -> Dict[str, Any]:
    """Remove None values and optionally filter by allowed keys"""
    if allowed_keys:
        data = {k: v for k, v in data.items() if k in allowed_keys}
    return {k: v for k, v in data.items() if v is not None}


def merge_dtos(*dtos) -> Dict[str, Any]:
    """Merge multiple DTOs into a single dictionary"""
    result = {}
    for dto in dtos:
        if hasattr(dto, 'to_dict'):
            result.update(dto.to_dict())
        elif isinstance(dto, dict):
            result.update(dto)
    return result


def validate_dto_list(dtos: List[BaseDTO]) -> List[str]:
    """Validate a list of DTOs and return all error messages"""
    all_errors = []
    for i, dto in enumerate(dtos):
        errors = dto.validate()
        if errors:
            all_errors.extend([f"Item {i}: {error}" for error in errors])
    return all_errors