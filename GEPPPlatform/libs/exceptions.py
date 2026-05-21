"""
Custom exceptions for standardized API error handling
"""

class APIException(Exception):
    """Base exception for API errors"""
    def __init__(self, message: str, status_code: int = 500, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)

class UnauthorizedException(APIException):
    """401 Unauthorized"""
    def __init__(self, message: str = "Unauthorized", error_code: str = "UNAUTHORIZED"):
        super().__init__(message, 401, error_code)

class ForbiddenException(APIException):
    """403 Forbidden"""
    def __init__(self, message: str = "Forbidden", error_code: str = "FORBIDDEN"):
        super().__init__(message, 403, error_code)

class NotFoundException(APIException):
    """404 Not Found"""
    def __init__(self, message: str = "Resource not found", error_code: str = "NOT_FOUND"):
        super().__init__(message, 404, error_code)

class BadRequestException(APIException):
    """400 Bad Request"""
    def __init__(self, message: str = "Bad request", error_code: str = "BAD_REQUEST"):
        super().__init__(message, 400, error_code)

class ValidationException(APIException):
    """422 Unprocessable Entity"""
    def __init__(self, message: str = "Validation failed", error_code: str = "VALIDATION_ERROR", errors: list = None):
        super().__init__(message, 422, error_code)
        self.errors = errors or []

class ConflictException(APIException):
    """409 Conflict"""
    def __init__(self, message: str = "Resource conflict", error_code: str = "CONFLICT"):
        super().__init__(message, 409, error_code)

class InternalServerException(APIException):
    """500 Internal Server Error"""
    def __init__(self, message: str = "Internal server error", error_code: str = "INTERNAL_ERROR"):
        super().__init__(message, 500, error_code)