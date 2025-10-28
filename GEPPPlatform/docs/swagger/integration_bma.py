"""
Swagger/OpenAPI specification for BMA Integration API
"""

from typing import Dict, Any


def get_bma_integration_paths() -> Dict[str, Any]:
    """
    Get BMA Integration API path specifications

    Returns:
        Dictionary of path specifications for BMA Integration endpoints
    """
    return {
        "/api/integration/bma/audit_status": {
            "get": {
                "tags": ["BMA Integration"],
                "summary": "Get audit status summary",
                "description": """
Get a summary of transaction audit statuses for the past year.

This endpoint returns:
- Total number of transactions in the past year
- Breakdown of AI audit statuses (not_audit, queued, approved, rejected)
- Breakdown of actual transaction statuses (pending, approved, rejected)

Filters:
- Only includes transactions from the past 365 days
- Only includes active transactions (deleted_date is NULL)
- Scoped to the authenticated user's organization
                """,
                "operationId": "getBmaAuditStatusSummary",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Audit status summary retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaAuditStatusResponse"
                                },
                                "example": {
                                    "success": True,
                                    "data": {
                                        "start_date": "2024-10-27",
                                        "num_transactions": 150,
                                        "ai_audit": {
                                            "not_audit": 45,
                                            "queued": 30,
                                            "approved": 50,
                                            "rejected": 25
                                        },
                                        "actual_status": {
                                            "pending": 60,
                                            "approved": 70,
                                            "rejected": 20
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            }
        },
        "/api/integration/bma/usage": {
            "get": {
                "tags": ["BMA Integration"],
                "summary": "Get subscription usage information",
                "description": """
Get current subscription usage limits and consumption for the organization.

This endpoint returns:
- Transaction creation limits and current usage
- AI audit limits and current usage

Useful for checking remaining quota before creating transactions.
                """,
                "operationId": "getBmaSubscriptionUsage",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Subscription usage information retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaUsageResponse"
                                },
                                "example": {
                                    "success": True,
                                    "data": {
                                        "subscription_usage": {
                                            "create_transaction_limit": 100,
                                            "create_transaction_usage": 45,
                                            "ai_audit_limit": 10,
                                            "ai_audit_usage": 3
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/BadRequestError"
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            }
        },
        "/api/integration/bma/add_transactions_to_audit_queue": {
            "post": {
                "tags": ["BMA Integration"],
                "summary": "Add transactions to AI audit queue",
                "description": """
Add all transactions with ai_audit_status = 'null' to the AI audit queue.

This endpoint:
- Updates all non-audited transactions to 'queued' status
- Uses optimized raw SQL for bulk updates
- Only affects transactions in the authenticated user's organization
- Only affects active transactions (deleted_date is NULL)

**Use Case:**
Trigger AI auditing for all pending transactions that haven't been queued yet.
                """,
                "operationId": "addTransactionsToAuditQueue",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Transactions successfully added to audit queue",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaAuditQueueResponse"
                                },
                                "example": {
                                    "success": True,
                                    "data": {
                                        "transactions_queued": 45,
                                        "message": "Successfully added 45 transactions to audit queue"
                                    }
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            }
        },
        "/api/integration/bma/transaction": {
            "get": {
                "tags": ["BMA Integration"],
                "summary": "Get list of transactions with pagination",
                "description": """
Get a paginated list of transactions filtered by query parameters, sorted by ID in ascending order.

**Response Structure:**
Returns transactions in nested format organized by:
- transaction_version (ext_id_1)
- origin_id
- house_id (ext_id_2)
- audit (status, ai_audit, overall_violations, materials)
  - materials (general, organic, recyclable, hazardous)

**Sorting:**
- Transactions are sorted by **house_id (ext_id_2)** in ascending order

**Pagination:**
- Use `page` and `limit` parameters for pagination
- Response includes pagination metadata: page, limit, total, total_pages, has_next, has_prev

**Query Parameters:**
- `limit`: Number of transactions per page (default: 100, max: 1000)
- `page`: Page number (default: 1, starts from 1)
- `transaction_version`: Filter by transaction version (ext_id_1)
- `origin_id`: Filter by origin ID (default: 2170)

**Example:**
- Page 1: `GET /api/integration/bma/transaction?page=1&limit=100`
- Page 2: `GET /api/integration/bma/transaction?page=2&limit=100`
                """,
                "operationId": "getBmaTransactions",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Maximum number of transactions to return per page",
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "default": 100,
                            "maximum": 1000,
                            "minimum": 1
                        }
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "description": "Page number (starts from 1)",
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "default": 1,
                            "minimum": 1,
                            "example": 1
                        }
                    },
                    {
                        "name": "transaction_version",
                        "in": "query",
                        "description": "Filter by transaction version (ext_id_1)",
                        "required": False,
                        "schema": {
                            "type": "string",
                            "example": "v2025-Q4"
                        }
                    },
                    {
                        "name": "origin_id",
                        "in": "query",
                        "description": "Filter by origin ID",
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "default": 2170,
                            "example": 2170
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Transactions retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaTransactionListResponse"
                                },
                                "example": {
                                    "success": True,
                                    "data": {
                                        "transactions": {
                                            "v2025-Q4": {
                                                "2170": {
                                                    "00000000001": {
                                                        "audit": {
                                                            "status": "approved",
                                                            "ai_audit": "approved",
                                                            "overall_violations": [],
                                                            "materials": {
                                                                "general": {
                                                                    "image_url": "https://s3.example.com/general.jpg",
                                                                    "violations": []
                                                                },
                                                                "organic": {
                                                                    "image_url": "https://s3.example.com/organic.jpg",
                                                                    "violations": []
                                                                },
                                                                "recyclable": {
                                                                    "image_url": "https://s3.example.com/recyclable.jpg",
                                                                    "violations": []
                                                                },
                                                                "hazardous": {
                                                                    "image_url": "https://s3.example.com/hazardous.jpg",
                                                                    "violations": []
                                                                }
                                                            }
                                                        }
                                                    },
                                                    "00000000002": {
                                                        "audit": {
                                                            "status": "rejected",
                                                            "ai_audit": "rejected",
                                                            "overall_violations": [
                                                                "Incomplete transaction: Missing required material types"
                                                            ],
                                                            "materials": {
                                                                "general": {
                                                                    "image_url": "https://s3.example.com/general2.jpg",
                                                                    "violations": [
                                                                        "Image-material mismatch: Appears to be hazardous waste"
                                                                    ]
                                                                },
                                                                "organic": {
                                                                    "image_url": None,
                                                                    "violations": []
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        },
                                        "origins": {
                                            "2170": "BMA Collection Center"
                                        },
                                        "pagination": {
                                            "page": 1,
                                            "limit": 100,
                                            "total": 2,
                                            "total_pages": 1,
                                            "has_next": False,
                                            "has_prev": False
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/BadRequestError"
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            },
            "post": {
                "tags": ["BMA Integration"],
                "summary": "Process BMA transaction batch",
                "description": """
Process a batch of waste transactions from the BMA (Bangkok Metropolitan Administration) system.

This endpoint allows BMA systems to:
- Create new transactions with waste material data
- Update existing transactions identified by transaction_version and house_id
- Automatically match and link material records to transactions

**Transaction Matching:**
- Transactions are matched using `ext_id_1` (transaction_version) and `ext_id_2` (house_id)
- If a match is found, the transaction is updated
- If no match is found, a new transaction is created

**House ID Format:**
- **Recommended:** Use 11-digit format (e.g., '00000000001', '00000000002')
- Ensures consistency and easy sorting
- Example: '00000000123' instead of 'HOUSE-123'

**Material Types:**
- `general` - General Waste (material_id: 94)
- `organic` - Food and Plant Waste (material_id: 77)
- `recyclable` - Non-Specific Recyclables (material_id: 298)
- `hazardous` - Non-Specific Hazardous Waste (material_id: 113)
                """,
                "operationId": "processBmaTransactionBatch",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "requestBody": {
                    "required": True,
                    "description": "Batch of BMA transactions organized by version and house ID",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/BmaTransactionBatch"
                            },
                            "examples": {
                                "single_house": {
                                    "summary": "Single house with multiple materials",
                                    "value": {
                                        "batch": {
                                            "v2025-Q1": {
                                                "2170": {
                                                    "00000000001": {
                                                        "timestamp": "2025-10-23T08:30:00+07:00",
                                                        "material": {
                                                            "general": {
                                                                "image_url": "https://s3.example.com/bma/house001-general.jpg"
                                                            },
                                                            "recyclable": {
                                                                "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                },
                                "multiple_houses": {
                                    "summary": "Multiple houses and versions",
                                    "value": {
                                        "batch": {
                                            "v2025-Q1": {
                                                "2170": {
                                                    "00000000001": {
                                                        "timestamp": "2025-10-23T08:30:00+07:00",
                                                        "material": {
                                                            "general": {
                                                                "image_url": "https://s3.example.com/bma/house001-general.jpg"
                                                            }
                                                        }
                                                    },
                                                    "00000000002": {
                                                        "timestamp": "2025-10-23T09:15:00+07:00",
                                                        "material": {
                                                            "organic": {
                                                                "image_url": "https://s3.example.com/bma/house002-organic.jpg"
                                                            },
                                                            "hazardous": {
                                                                "image_url": "https://s3.example.com/bma/house002-hazardous.jpg"
                                                            }
                                                        }
                                                    }
                                                }
                                            },
                                            "v2025-Q2": {
                                                "2170": {
                                                    "00000000003": {
                                                        "timestamp": "2025-10-23T10:00:00+07:00",
                                                        "material": {
                                                            "recyclable": {
                                                                "image_url": "https://s3.example.com/bma/house003-recyclable.jpg"
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Batch processed successfully (may include partial errors)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaTransactionBatchResponse"
                                },
                                "examples": {
                                    "all_success": {
                                        "summary": "All transactions processed successfully",
                                        "value": {
                                            "success": True,
                                            "data": {
                                                "success": True,
                                                "message": "Processed 3 transactions",
                                                "results": {
                                                    "processed": 3,
                                                    "created": 2,
                                                    "updated": 1,
                                                    "errors": []
                                                },
                                                "subscription_usage": {
                                                    "create_transaction_limit": 100,
                                                    "create_transaction_usage": 45,
                                                    "ai_audit_limit": 10,
                                                    "ai_audit_usage": 3
                                                }
                                            }
                                        }
                                    },
                                    "partial_success": {
                                        "summary": "Some transactions failed",
                                        "value": {
                                            "success": True,
                                            "data": {
                                                "success": True,
                                                "message": "Processed 2 transactions",
                                                "results": {
                                                    "processed": 2,
                                                    "created": 1,
                                                    "updated": 1,
                                                    "errors": [
                                                        {
                                                            "transaction_version": "v2025-Q1",
                                                            "house_id": "00000000004",
                                                            "error": "Invalid timestamp format"
                                                        }
                                                    ]
                                                },
                                                "subscription_usage": {
                                                    "create_transaction_limit": 100,
                                                    "create_transaction_usage": 45,
                                                    "ai_audit_limit": 10,
                                                    "ai_audit_usage": 3
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/BadRequestError"
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            }
        },
        "/api/integration/bma/transaction/{transaction_version}/{house_id}": {
            "get": {
                "tags": ["BMA Integration"],
                "summary": "Get specific transaction by IDs",
                "description": """
Get a specific transaction by transaction_version (ext_id_1) and house_id (ext_id_2).

Returns transaction in the same nested format as the list endpoint:
- transaction_version (ext_id_1)
- origin_id
- house_id (ext_id_2)
- material_name

Also includes origin names mapping.
                """,
                "operationId": "getBmaTransactionByIds",
                "security": [
                    {
                        "BearerAuth": []
                    }
                ],
                "parameters": [
                    {
                        "name": "transaction_version",
                        "in": "path",
                        "description": "Transaction version (ext_id_1)",
                        "required": True,
                        "schema": {
                            "type": "string",
                            "example": "v2025-Q4"
                        }
                    },
                    {
                        "name": "house_id",
                        "in": "path",
                        "description": "House ID (ext_id_2)",
                        "required": True,
                        "schema": {
                            "type": "string",
                            "example": "00000000001"
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Transaction retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BmaTransactionGetResponse"
                                },
                                "example": {
                                    "success": True,
                                    "data": {
                                        "transactions": {
                                            "v2025-Q4": {
                                                "2170": {
                                                    "00000000001": {
                                                        "audit": {
                                                            "status": "approved",
                                                            "ai_audit": "approved",
                                                            "overall_violations": [],
                                                            "materials": {
                                                                "general": {
                                                                    "image_url": "https://s3.example.com/general.jpg",
                                                                    "violations": []
                                                                },
                                                                "organic": {
                                                                    "image_url": "https://s3.example.com/organic.jpg",
                                                                    "violations": []
                                                                },
                                                                "recyclable": {
                                                                    "image_url": "https://s3.example.com/recyclable.jpg",
                                                                    "violations": []
                                                                },
                                                                "hazardous": {
                                                                    "image_url": "https://s3.example.com/hazardous.jpg",
                                                                    "violations": []
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        },
                                        "origins": {
                                            "2170": "BMA Collection Center"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/BadRequestError"
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    },
                    "404": {
                        "description": "Transaction not found",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Error"
                                },
                                "example": {
                                    "success": False,
                                    "message": "Transaction not found: v2025-Q4/00000000001"
                                }
                            }
                        }
                    },
                    "500": {
                        "$ref": "#/components/responses/InternalServerError"
                    }
                }
            }
        }
    }


def get_bma_integration_schemas() -> Dict[str, Any]:
    """
    Get BMA Integration component schemas

    Returns:
        Dictionary of schema definitions for BMA Integration
    """
    return {
        "BmaMaterialData": {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "format": "uri",
                    "description": "URL to the waste material image",
                    "example": "https://s3.example.com/bma/house001-general.jpg"
                }
            }
        },
        "BmaHouseData": {
            "type": "object",
            "required": ["timestamp", "material"],
            "properties": {
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 datetime with timezone when the waste was collected",
                    "example": "2025-10-23T08:30:00+07:00"
                },
                "material": {
                    "type": "object",
                    "description": "Material data keyed by material type (general, organic, recyclable, hazardous)",
                    "additionalProperties": {
                        "$ref": "#/components/schemas/BmaMaterialData"
                    },
                    "example": {
                        "general": {
                            "image_url": "https://s3.example.com/bma/house001-general.jpg"
                        },
                        "recyclable": {
                            "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
                        }
                    }
                }
            }
        },
        "BmaOriginData": {
            "type": "object",
            "description": "Houses grouped under an origin_id (must be 2170). House IDs should use 11-digit format (e.g., '00000000001', '00000000002').",
            "additionalProperties": {
                "$ref": "#/components/schemas/BmaHouseData"
            },
            "example": {
                "00000000001": {
                    "timestamp": "2025-10-23T08:30:00+07:00",
                    "material": {
                        "general": {
                            "image_url": "https://s3.example.com/bma/house001-general.jpg"
                        }
                    }
                },
                "00000000002": {
                    "timestamp": "2025-10-23T09:15:00+07:00",
                    "material": {
                        "organic": {
                            "image_url": "https://s3.example.com/bma/house002-organic.jpg"
                        }
                    }
                }
            }
        },
        "BmaTransactionVersion": {
            "type": "object",
            "description": "Origins grouped under a transaction version",
            "additionalProperties": {
                "$ref": "#/components/schemas/BmaOriginData"
            },
            "example": {
                "2170": {
                    "00000000001": {
                        "timestamp": "2025-10-23T08:30:00+07:00",
                        "material": {
                            "general": {
                                "image_url": "https://s3.example.com/bma/house001-general.jpg"
                            }
                        }
                    }
                }
            }
        },
        "BmaTransactionBatch": {
            "type": "object",
            "required": ["batch"],
            "properties": {
                "batch": {
                    "type": "object",
                    "description": "Batch of transactions organized by version, then by house ID",
                    "additionalProperties": {
                        "$ref": "#/components/schemas/BmaTransactionVersion"
                    },
                    "example": {
                        "v2025-Q1": {
                            "2170": {
                                "00000000001": {
                                    "timestamp": "2025-10-23T08:30:00+07:00",
                                    "material": {
                                        "general": {
                                            "image_url": "https://s3.example.com/bma/house001-general.jpg"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "BmaTransactionError": {
            "type": "object",
            "properties": {
                "transaction_version": {
                    "type": "string",
                    "description": "The transaction version that failed",
                    "example": "v2025-Q1"
                },
                "house_id": {
                    "type": "string",
                    "description": "The house ID that failed (11-digit format recommended)",
                    "example": "00000000001"
                },
                "error": {
                    "type": "string",
                    "description": "Error message",
                    "example": "Invalid timestamp format"
                }
            }
        },
        "BmaTransactionResults": {
            "type": "object",
            "properties": {
                "processed": {
                    "type": "integer",
                    "description": "Total number of house transactions processed",
                    "example": 3
                },
                "created": {
                    "type": "integer",
                    "description": "Number of new transactions created",
                    "example": 2
                },
                "updated": {
                    "type": "integer",
                    "description": "Number of existing transactions updated",
                    "example": 1
                },
                "errors": {
                    "type": "array",
                    "description": "List of errors encountered during processing",
                    "items": {
                        "$ref": "#/components/schemas/BmaTransactionError"
                    }
                }
            }
        },
        "BmaSubscriptionUsage": {
            "type": "object",
            "properties": {
                "create_transaction_limit": {
                    "type": "integer",
                    "description": "Maximum number of transactions allowed to create",
                    "example": 100
                },
                "create_transaction_usage": {
                    "type": "integer",
                    "description": "Current number of transactions created",
                    "example": 45
                },
                "ai_audit_limit": {
                    "type": "integer",
                    "description": "Maximum number of AI audits allowed",
                    "example": 10
                },
                "ai_audit_usage": {
                    "type": "integer",
                    "description": "Current number of AI audits used",
                    "example": 3
                }
            }
        },
        "BmaTransactionBatchResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean",
                            "example": True
                        },
                        "message": {
                            "type": "string",
                            "example": "Processed 3 transactions"
                        },
                        "results": {
                            "$ref": "#/components/schemas/BmaTransactionResults"
                        },
                        "subscription_usage": {
                            "$ref": "#/components/schemas/BmaSubscriptionUsage"
                        }
                    }
                }
            }
        },
        "BmaUsageResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "subscription_usage": {
                            "$ref": "#/components/schemas/BmaSubscriptionUsage"
                        }
                    }
                }
            }
        },
        "BmaAuditStatusResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "format": "date",
                            "description": "Start date for the summary (today - 1 year)",
                            "example": "2024-10-27"
                        },
                        "num_transactions": {
                            "type": "integer",
                            "description": "Total number of transactions in the period",
                            "example": 150
                        },
                        "ai_audit": {
                            "type": "object",
                            "description": "Breakdown of AI audit statuses",
                            "properties": {
                                "not_audit": {
                                    "type": "integer",
                                    "description": "Number of transactions not yet audited by AI",
                                    "example": 45
                                },
                                "queued": {
                                    "type": "integer",
                                    "description": "Number of transactions queued for AI audit",
                                    "example": 30
                                },
                                "approved": {
                                    "type": "integer",
                                    "description": "Number of transactions approved by AI audit",
                                    "example": 50
                                },
                                "rejected": {
                                    "type": "integer",
                                    "description": "Number of transactions rejected by AI audit",
                                    "example": 25
                                }
                            }
                        },
                        "actual_status": {
                            "type": "object",
                            "description": "Breakdown of actual transaction statuses",
                            "properties": {
                                "pending": {
                                    "type": "integer",
                                    "description": "Number of transactions with pending status",
                                    "example": 60
                                },
                                "approved": {
                                    "type": "integer",
                                    "description": "Number of transactions with approved status",
                                    "example": 70
                                },
                                "rejected": {
                                    "type": "integer",
                                    "description": "Number of transactions with rejected status",
                                    "example": 20
                                }
                            }
                        }
                    }
                }
            }
        },
        "BmaAuditQueueResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "transactions_queued": {
                            "type": "integer",
                            "description": "Number of transactions added to the audit queue",
                            "example": 45
                        },
                        "message": {
                            "type": "string",
                            "description": "Success message",
                            "example": "Successfully added 45 transactions to audit queue"
                        }
                    }
                }
            }
        },
        "BmaMaterialAudit": {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": ["string", "null"],
                    "description": "URL to the material image (first image from images array, null if not available)",
                    "example": "https://s3.example.com/general.jpg"
                },
                "audit": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Transaction status",
                            "enum": ["pending", "approved", "rejected"],
                            "example": "approved"
                        },
                        "ai_audit_status": {
                            "type": "string",
                            "description": "AI audit status",
                            "enum": ["null", "queued", "approved", "rejected"],
                            "example": "approved"
                        },
                        "violations": {
                            "type": "array",
                            "description": "List of audit violations",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string",
                                        "description": "Violation message",
                                        "example": "Incomplete transaction: Missing required material types"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "BmaTransactionListResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "transactions": {
                            "type": "object",
                            "description": "Nested structure: transaction_version > origin_id > house_id > material_name > material data",
                            "additionalProperties": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "additionalProperties": {
                                            "$ref": "#/components/schemas/BmaMaterialAudit"
                                        }
                                    }
                                }
                            }
                        },
                        "origins": {
                            "type": "object",
                            "description": "Mapping of origin_id to location name",
                            "additionalProperties": {
                                "type": "string"
                            },
                            "example": {
                                "2170": "BMA Collection Center"
                            }
                        },
                        "pagination": {
                            "type": "object",
                            "description": "Pagination information",
                            "properties": {
                                "page": {
                                    "type": "integer",
                                    "description": "Current page number",
                                    "example": 1
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Number of items per page",
                                    "example": 100
                                },
                                "total": {
                                    "type": "integer",
                                    "description": "Total number of items",
                                    "example": 250
                                },
                                "total_pages": {
                                    "type": "integer",
                                    "description": "Total number of pages",
                                    "example": 3
                                },
                                "has_next": {
                                    "type": "boolean",
                                    "description": "Whether there is a next page",
                                    "example": True
                                },
                                "has_prev": {
                                    "type": "boolean",
                                    "description": "Whether there is a previous page",
                                    "example": False
                                }
                            }
                        }
                    }
                }
            }
        },
        "BmaTransactionGetResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "transactions": {
                            "type": "object",
                            "description": "Nested structure: transaction_version > origin_id > house_id > material_name > material data",
                            "additionalProperties": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "additionalProperties": {
                                            "$ref": "#/components/schemas/BmaMaterialAudit"
                                        }
                                    }
                                }
                            }
                        },
                        "origins": {
                            "type": "object",
                            "description": "Mapping of origin_id to location name",
                            "additionalProperties": {
                                "type": "string"
                            },
                            "example": {
                                "2170": "BMA Collection Center"
                            }
                        }
                    }
                }
            }
        }
    }
