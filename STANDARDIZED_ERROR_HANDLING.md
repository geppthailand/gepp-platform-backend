# Standardized Error Handling Pattern

## Overview

This document describes the standardized error handling pattern implemented across all backend services. The pattern separates concerns between service layers and the main application handler.

## Architecture

### 1. Service Layer (handlers/services)
- **Success case**: Return data directly (no status codes or wrapping)
- **Error case**: Raise custom exceptions with appropriate error codes

### 2. Application Layer (app.py)
- **Success case**: Wrap returned data in standardized success response
- **Error case**: Catch exceptions and convert to standardized error responses with proper HTTP status codes

## Custom Exceptions

All custom exceptions inherit from `APIException` and include:
- `message`: Human-readable error message
- `status_code`: HTTP status code (401, 404, 422, etc.)
- `error_code`: Machine-readable error identifier

### Available Exception Classes

```python
from GEPPPlatform.exceptions import (
    APIException,           # Base exception (500)
    UnauthorizedException,  # 401 Unauthorized
    ForbiddenException,     # 403 Forbidden
    NotFoundException,      # 404 Not Found
    BadRequestException,    # 400 Bad Request
    ValidationException,    # 422 Unprocessable Entity
    ConflictException,      # 409 Conflict
    InternalServerException # 500 Internal Server Error
)
```

## Implementation Examples

### Service Layer Example (BEFORE)
```python
def handle_get_organization_roles(org_service, user_id, headers):
    try:
        organization = org_service.get_user_organization(user_id)

        if not organization:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'success': False, 'message': 'Organization not found'})
            }

        roles = org_service.get_organization_roles(organization.id)
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'success': True, 'data': roles})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'success': False, 'message': str(e)})
        }
```

### Service Layer Example (AFTER)
```python
def handle_get_organization_roles(org_service, user_id, headers):
    organization = org_service.get_user_organization(user_id)

    if not organization:
        raise NotFoundException('User is not part of any organization')

    roles = org_service.get_organization_roles(organization.id)
    return roles  # Return data directly
```

### Application Layer (app.py)
```python
try:
    if "/api/organizations" in path:
        org_result = organization_routes(event_with_auth, context)
        results = {
            "success": True,
            "data": org_result
        }

except APIException as api_error:
    return {
        "statusCode": api_error.status_code,
        "headers": headers,
        "body": json.dumps({
            "success": False,
            "message": api_error.message,
            "error_code": api_error.error_code,
            "errors": getattr(api_error, 'errors', None)
        })
    }

except Exception as service_error:
    return {
        "statusCode": 500,
        "headers": headers,
        "body": json.dumps({
            "success": False,
            "message": "Internal server error",
            "error_code": "SERVICE_ERROR",
            "stack_trace": traceback.format_exc()
        })
    }
```

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... }
}
```

### Error Response
```json
{
  "success": false,
  "message": "Human-readable error message",
  "error_code": "MACHINE_READABLE_CODE",
  "errors": ["Optional array of validation errors"],
  "stack_trace": "Debug info (only in development)"
}
```

## Benefits

1. **Separation of Concerns**: Services focus on business logic, app.py handles HTTP concerns
2. **Consistent Error Format**: All errors follow the same response structure
3. **Proper Status Codes**: HTTP status codes are set correctly in one place
4. **Better Debugging**: Stack traces are included for unexpected errors
5. **Type Safety**: Return types are cleaner (no mixed success/error objects)

## Migration Guide

To migrate existing handlers:

1. Add exception imports to your handler file
2. Replace error returns with appropriate exception raises
3. Remove try-catch blocks that return HTTP responses
4. Return data directly on success
5. Let exceptions propagate to app.py

The application layer in `app.py` will automatically handle the exceptions and convert them to proper HTTP responses.