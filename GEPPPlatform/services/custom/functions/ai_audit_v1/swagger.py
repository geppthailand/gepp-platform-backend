"""
OpenAPI/Swagger Documentation for AI Audit V1 API

This module contains the OpenAPI 3.0 specification for the AI Audit V1 custom API.
"""

from typing import Dict, Any


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
            "description": "AI-powered waste transaction audit API. Analyzes images and validates waste classification using Google Vertex AI.",
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
            "/analyze": {
                "post": {
                    "tags": ["Audit"],
                    "summary": "Analyze transaction",
                    "description": "Run AI audit on a specific transaction by ID",
                    "operationId": "analyzeTransaction",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/AnalyzeRequest"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Analysis completed",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/AnalyzeResponse"
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
                "AnalyzeRequest": {
                    "type": "object",
                    "required": ["transaction_id"],
                    "properties": {
                        "transaction_id": {
                            "type": "integer",
                            "description": "ID of the transaction to analyze",
                            "example": 12345
                        },
                        "options": {
                            "type": "object",
                            "properties": {
                                "detailed": {
                                    "type": "boolean",
                                    "description": "Return detailed analysis",
                                    "default": True
                                },
                                "language": {
                                    "type": "string",
                                    "enum": ["thai", "english"],
                                    "description": "Response language",
                                    "default": "thai"
                                }
                            }
                        }
                    }
                },
                "AnalyzeResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "transaction_id": {"type": "integer"},
                        "audit_result": {"type": "object"}
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
                                "message": "transaction_id is required",
                                "error_code": "MISSING_TRANSACTION_ID"
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
