"""
OpenAPI/Swagger Documentation for AI Audit V1 API

This module contains the OpenAPI 3.0 specification for the AI Audit V1 custom API.
"""

from typing import Dict, Any


def _generate_example_households(count: int = 100) -> Dict[str, Any]:
    """
    Generate example household data with complete materials for all households.

    Args:
        count: Number of households to generate (default 100)

    Returns:
        Example data structure with specified number of households
    """
    households = {}

    for i in range(1, count + 1):
        # Zero-pad household ID to 13 digits
        household_id = str(i).zfill(13)

        # Each household has all 4 material types with complete image URLs
        households[household_id] = {
            "materials": {
                "general": {"image_url": f"https://storage.example.com/general_{household_id}.jpg"},
                "organic": {"image_url": f"https://storage.example.com/organic_{household_id}.jpg"},
                "recyclable": {"image_url": f"https://storage.example.com/recyclable_{household_id}.jpg"},
                "hazardous": {"image_url": f"https://storage.example.com/hazardous_{household_id}.jpg"}
            }
        }

    return {
        "2025-01": {
            "เขตยานนาวา": {
                "แขวงช่องนนทรี": households
            }
        }
    }


def get_swagger_spec() -> Dict[str, Any]:
    """
    Returns the OpenAPI 3.0 specification for AI Audit V1 API.
    
    Returns:
        Dictionary containing the complete OpenAPI specification
    """
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "AI Audit V1 API",
            "version": "1.0.0",
            "description": "AI-powered waste transaction audit API. Receives household waste data, upserts transactions, and dispatches to the organisation's configured audit rule set.",
            "contact": {
                "name": "GEPP Platform Support",
                "url": "https://gepp.co.th"
            }
        },
        "servers": [
            {
                "url": "https://api.geppdata.com/v1/api/userapi/{api_path}/ai_audit/v1",
                "description": "Production API",
                "variables": {
                    "api_path": {
                        "description": "Organization-specific API path (32-character random string)",
                        "default": "your-api-path-here"
                    }
                }
            }
        ],
        "security": [
            {
                "bearerAuth": []
            }
        ],
        "tags": [
            {
                "name": "Testing",
                "description": "Test and verify API connection"
            },
            {
                "name": "Audit",
                "description": "AI audit operations"
            },
            {
                "name": "Management",
                "description": "Quota and status management"
            }
        ],
        "paths": {
            "/test": {
                "get": {
                    "tags": ["Testing"],
                    "summary": "Test API connection",
                    "description": "Verifies API access and returns organization information. Recommended first endpoint to test.",
                    "operationId": "testConnection",
                    "responses": {
                        "200": {
                            "description": "Connection successful",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/TestResponse"
                                    }
                                }
                            }
                        },
                        "403": {
                            "$ref": "#/components/responses/Forbidden"
                        },
                        "404": {
                            "$ref": "#/components/responses/NotFound"
                        }
                    }
                }
            },
            "/status": {
                "get": {
                    "tags": ["Management"],
                    "summary": "Get service status",
                    "description": "Returns service health and capabilities",
                    "operationId": "getStatus",
                    "responses": {
                        "200": {
                            "description": "Service status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/StatusResponse"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/quota": {
                "get": {
                    "tags": ["Management"],
                    "summary": "Get quota usage",
                    "description": "Returns current API call and processing quota status",
                    "operationId": "getQuota",
                    "responses": {
                        "200": {
                            "description": "Quota information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/QuotaResponse"
                                    }
                                }
                            }
                        },
                        "403": {
                            "$ref": "#/components/responses/Forbidden"
                        }
                    }
                }
            },
            "/call": {
                "post": {
                    "tags": ["Audit"],
                    "summary": "Submit household waste data for audit",
                    "description": "Receives nested household waste data, upserts transactions (using ext_id_1 + ext_id_2 as unique key), and dispatches to the organisation's configured audit rule set. The subdistrict name (แขวง) is matched against user_locations.name_en to resolve origin_id for each transaction.",
                    "operationId": "callAudit",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/CallRequest"
                                },
                                "example": _generate_example_households(100)
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Call processed successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/CallResponse"
                                    }
                                }
                            }
                        },
                        "400": {
                            "$ref": "#/components/responses/BadRequest"
                        },
                        "403": {
                            "$ref": "#/components/responses/Forbidden"
                        },
                        "404": {
                            "$ref": "#/components/responses/NotFound"
                        },
                        "429": {
                            "$ref": "#/components/responses/QuotaExceeded"
                        }
                    }
                }
            },
            "/sync": {
                "post": {
                    "tags": ["Audit"],
                    "summary": "Sync audit (batch processing)",
                    "description": "Process pending transactions in batch",
                    "operationId": "syncAudit",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/SyncRequest"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Sync completed",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/SyncResponse"
                                    }
                                }
                            }
                        },
                        "429": {
                            "$ref": "#/components/responses/QuotaExceeded"
                        }
                    }
                }
            }
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT token with organization_id claim that matches the api_path organization"
                }
            },
            "schemas": {
                "TestResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "message": {"type": "string", "example": "API connection successful"},
                        "organization": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer", "example": 8},
                                "name": {"type": "string", "example": "Organization Name"},
                                "description": {"type": "string"},
                                "api_path": {"type": "string", "example": "a7f8e9c2d3b4a5c6d7e8f9a0b1c2d3e4"},
                                "allow_ai_audit": {"type": "boolean", "example": True},
                                "enable_ai_audit_api": {"type": "boolean", "example": True},
                                "ai_audit_rule_set_id": {"type": "integer", "example": 1},
                                "is_active": {"type": "boolean", "example": True},
                                "created_date": {"type": "string", "format": "date-time"}
                            }
                        },
                        "authenticated_at": {"type": "string", "example": "success"},
                        "api_version": {"type": "string", "example": "v1"}
                    }
                },
                "StatusResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "service": {"type": "string", "example": "ai_audit"},
                        "version": {"type": "string", "example": "v1"},
                        "organization_id": {"type": "integer"},
                        "status": {"type": "string", "example": "operational"},
                        "capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "example": ["waste_classification", "contamination_detection", "quality_assessment"]
                        },
                        "supported_waste_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "example": ["general", "recyclable", "organic", "hazardous"]
                        }
                    }
                },
                "QuotaResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "organization_id": {"type": "integer"},
                        "quota": {
                            "type": "object",
                            "properties": {
                                "api_calls": {
                                    "type": "object",
                                    "properties": {
                                        "used": {"type": "integer", "example": 50},
                                        "limit": {"type": "integer", "example": 1000},
                                        "remaining": {"type": "integer", "example": 950}
                                    }
                                },
                                "process_units": {
                                    "type": "object",
                                    "properties": {
                                        "used": {"type": "integer", "example": 200},
                                        "limit": {"type": "integer", "example": 10000},
                                        "remaining": {"type": "integer", "example": 9800}
                                    }
                                }
                            }
                        },
                        "expired_date": {"type": "string", "format": "date-time", "nullable": True},
                        "enabled": {"type": "boolean", "example": True}
                    }
                },
                "CallRequest": {
                    "type": "object",
                    "description": "Nested household waste data. Structure: { ext_id_1: { district (เขต): { subdistrict (แขวง): { household_id: { materials: { ... } } } } } }. The subdistrict name is matched against user_locations.name_en to resolve transaction.origin_id.",
                    "additionalProperties": {
                        "type": "object",
                        "description": "District level (เขต), keyed by district name",
                        "additionalProperties": {
                            "type": "object",
                            "description": "Subdistrict level (แขวง), keyed by subdistrict name. Matched against user_locations.name_en to resolve origin_id.",
                            "additionalProperties": {
                                "type": "object",
                                "description": "Household level, keyed by household_id (13-digit zero-padded string, e.g. '0000000000001'). Used as ext_id_2.",
                                "properties": {
                                    "materials": {
                                        "type": "object",
                                        "description": "Waste materials for this household. Only 4 keys allowed: general, organic, recyclable, hazardous",
                                        "properties": {
                                            "general": {"$ref": "#/components/schemas/MaterialData"},
                                            "organic": {"$ref": "#/components/schemas/MaterialData"},
                                            "recyclable": {"$ref": "#/components/schemas/MaterialData"},
                                            "hazardous": {"$ref": "#/components/schemas/MaterialData"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "MaterialData": {
                    "type": "object",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "format": "uri",
                            "description": "URL of the waste image",
                            "example": "https://storage.example.com/waste_image.jpg"
                        }
                    }
                },
                "CallResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "calling_id": {"type": "integer", "description": "ID of the custom_api_callings record", "example": 42},
                        "rule_set": {"type": "string", "description": "Name of the audit rule set executed", "example": "bma_audit_rule_set"},
                        "transactions": {
                            "type": "object",
                            "properties": {
                                "created": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "IDs of newly created transactions",
                                    "example": [101, 102]
                                },
                                "updated": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "IDs of updated transactions",
                                    "example": [50]
                                }
                            }
                        },
                        "audit_result": {
                            "type": "object",
                            "description": "Result returned by the audit rule set"
                        }
                    }
                },
                "SyncRequest": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum transactions to process",
                            "default": 10,
                            "example": 10
                        },
                        "transaction_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Specific transaction IDs to process (optional)",
                            "nullable": True
                        }
                    }
                },
                "SyncResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "result": {"type": "object"}
                    }
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "message": {"type": "string"},
                        "error_code": {"type": "string"}
                    }
                }
            },
            "responses": {
                "BadRequest": {
                    "description": "Invalid request",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"},
                            "example": {
                                "success": False,
                                "message": "Invalid request payload",
                                "error_code": "BAD_REQUEST"
                            }
                        }
                    }
                },
                "Forbidden": {
                    "description": "Access denied",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"},
                            "examples": {
                                "org_mismatch": {
                                    "value": {
                                        "success": False,
                                        "message": "Access denied. Your organization does not match this API path.",
                                        "error_code": "ORG_MISMATCH"
                                    }
                                },
                                "api_disabled": {
                                    "value": {
                                        "success": False,
                                        "message": "API access is disabled for this organization",
                                        "error_code": "API_DISABLED"
                                    }
                                },
                                "api_expired": {
                                    "value": {
                                        "success": False,
                                        "message": "API access has expired",
                                        "error_code": "API_EXPIRED"
                                    }
                                }
                            }
                        }
                    }
                },
                "NotFound": {
                    "description": "Resource not found",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"},
                            "example": {
                                "success": False,
                                "message": "Organization not found for api_path: invalid-path",
                                "error_code": "ORG_NOT_FOUND"
                            }
                        }
                    }
                },
                "QuotaExceeded": {
                    "description": "Quota limit exceeded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"},
                            "example": {
                                "success": False,
                                "message": "API call quota exceeded",
                                "error_code": "QUOTA_EXCEEDED"
                            }
                        }
                    }
                }
            }
        }
    }
