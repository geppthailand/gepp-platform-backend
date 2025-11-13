"""
Base Swagger/OpenAPI configuration for GEPP Platform
"""

from typing import Dict, Any

def get_base_swagger_config(deployment_state: str = "dev") -> Dict[str, Any]:
    """
    Get base Swagger/OpenAPI 3.0 configuration

    Args:
        deployment_state: The deployment environment (dev, staging, prod)

    Returns:
        Base OpenAPI configuration dictionary
    """
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "GEPP Platform API",
            "version": "1.0.0",
            "description": """
# GEPP Platform API Documentation

The GEPP Platform provides a comprehensive API for waste management, sustainability reporting, and compliance tracking.

## Authentication

Most endpoints require JWT authentication. Include your token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

## API Structure

The API is organized into the following modules:

- **Auth** - Authentication and user management
- **Organizations** - Organization and location management
- **Users** - User profile and permissions
- **Materials** - Material catalog and categories
- **Transactions** - Waste transaction tracking
- **Audit** - Transaction auditing and compliance
- **Reports** - Analytics and reporting
- **Integration** - External system integrations

## Deployment States

The API supports multiple deployment environments:
- `dev` - Development environment
- `staging` - Staging environment
- `prod` - Production environment

Access the API at: `/{deployment_state}/api/*`
            """,
            "contact": {
                "name": "GEPP Platform Support",
                "email": "support@gepp.com"
            },
            "license": {
                "name": "Proprietary",
                "url": "https://gepp.com/license"
            }
        },
        "servers": [
            {
                "url": f"/{deployment_state}",
                "description": f"Relative URL - {deployment_state.capitalize()} Environment"
            },
            {
                "url": f"https://api.geppdata.com/{deployment_state}",
                "description": f"Production - {deployment_state.capitalize()} Environment"
            },
            {
                "url": f"http://localhost:3000/{deployment_state}",
                "description": f"Local Development - {deployment_state.capitalize()} Environment"
            }
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT token obtained from /api/auth/login"
                }
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean",
                            "example": False
                        },
                        "message": {
                            "type": "string",
                            "example": "Error message"
                        },
                        "error_code": {
                            "type": "string",
                            "example": "ERROR_CODE"
                        },
                        "errors": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    }
                },
                "SuccessResponse": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean",
                            "example": True
                        },
                        "message": {
                            "type": "string",
                            "example": "Operation successful"
                        },
                        "data": {
                            "type": "object"
                        }
                    }
                }
            },
            "responses": {
                "UnauthorizedError": {
                    "description": "Authentication required or token invalid",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Invalid token",
                                "error_code": "UNAUTHORIZED"
                            }
                        }
                    }
                },
                "NotFoundError": {
                    "description": "Resource not found",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Resource not found",
                                "error_code": "NOT_FOUND"
                            }
                        }
                    }
                },
                "BadRequestError": {
                    "description": "Invalid request parameters",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Invalid request",
                                "error_code": "BAD_REQUEST"
                            }
                        }
                    }
                },
                "ValidationError": {
                    "description": "Validation error",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Validation failed",
                                "error_code": "VALIDATION_ERROR",
                                "errors": ["Email already registered"]
                            }
                        }
                    }
                },
                "InternalServerError": {
                    "description": "Internal server error",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Internal server error",
                                "error_code": "INTERNAL_ERROR"
                            }
                        }
                    }
                }
            }
        },
        "security": [
            {
                "BearerAuth": []
            }
        ],
        "tags": [
            {
                "name": "Auth",
                "description": "Authentication and authorization endpoints"
            },
            {
                "name": "Organizations",
                "description": "Organization and location management"
            },
            {
                "name": "Users",
                "description": "User management and profiles"
            },
            {
                "name": "Materials",
                "description": "Material catalog and categories"
            },
            {
                "name": "Transactions",
                "description": "Waste transaction tracking and management"
            },
            {
                "name": "Audit",
                "description": "Transaction auditing and compliance"
            },
            {
                "name": "Reports",
                "description": "Analytics and reporting"
            },
            {
                "name": "Integration",
                "description": "External system integrations"
            },
            {
                "name": "BMA Integration",
                "description": "Bangkok Metropolitan Administration integration"
            },
            {
                "name": "IOT Devices",
                "description": "IoT device management and telemetry"
            }
        ],
        "paths": {}
    }
