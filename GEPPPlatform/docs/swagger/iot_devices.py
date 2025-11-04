"""
Swagger/OpenAPI documentation for IoT Devices related endpoints
"""

from typing import Dict, Any


def get_iot_devices_paths() -> Dict[str, Any]:
    """
    Get OpenAPI path specifications for IoT Devices endpoints

    Returns:
        Dictionary of path specifications
    """
    return {
        "/api/locations/my-memberships": {
            "get": {
                "tags": ["IOT Devices"],
                "summary": "List locations where current user is a dataInput member",
                "description": "Returns locations in the user's organization where the authenticated user appears in the location members list. Defaults to role=dataInput.",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "in": "query",
                        "name": "role",
                        "required": False,
                        "schema": {"type": "string", "default": "dataInput"},
                        "description": "Filter by member role (default: dataInput)"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "List of member locations",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LocationsByMembershipResponse"
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/UnauthorizedError"},
                    "404": {"$ref": "#/components/responses/NotFoundError"},
                    "400": {"$ref": "#/components/responses/BadRequestError"}
                }
            }
        }
    }


def get_iot_devices_schemas() -> Dict[str, Any]:
    """
    Get OpenAPI schema definitions for IoT Devices endpoints

    Returns:
        Dictionary of schema definitions
    """
    return {
        "Location": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 123},
                "display_name": {"type": "string", "example": "Main Branch"},
                "name_en": {"type": "string", "nullable": True},
                "name_th": {"type": "string", "nullable": True},
                "is_location": {"type": "boolean", "example": True},
                "is_active": {"type": "boolean", "example": True},
                "organization_id": {"type": "integer", "example": 42},
                "members": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "user_id": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                            "role": {"type": "string", "example": "dataInput"}
                        }
                    }
                }
            }
        },
        "LocationsByMembershipResponse": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "example": True},
                "data": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Location"}
                },
                "total": {"type": "integer", "example": 2},
                "organization_id": {"type": "integer", "example": 42},
                "role": {"type": "string", "example": "dataInput"}
            }
        }
    }


