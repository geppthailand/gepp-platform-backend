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
        "/api/integration/bma/transaction": {
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
                                                    "HOUSE-001": {
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
                                                    "HOUSE-001": {
                                                        "timestamp": "2025-10-23T08:30:00+07:00",
                                                        "material": {
                                                            "general": {
                                                                "image_url": "https://s3.example.com/bma/house001-general.jpg"
                                                            }
                                                        }
                                                    },
                                                    "HOUSE-002": {
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
                                                    "HOUSE-003": {
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
                                                            "house_id": "HOUSE-004",
                                                            "error": "Invalid timestamp format"
                                                        }
                                                    ]
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
            "description": "Houses grouped under an origin_id (must be 2170)",
            "additionalProperties": {
                "$ref": "#/components/schemas/BmaHouseData"
            },
            "example": {
                "HOUSE-001": {
                    "timestamp": "2025-10-23T08:30:00+07:00",
                    "material": {
                        "general": {
                            "image_url": "https://s3.example.com/bma/house001-general.jpg"
                        }
                    }
                },
                "HOUSE-002": {
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
                    "HOUSE-001": {
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
                                "HOUSE-001": {
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
                    "description": "The house ID that failed",
                    "example": "HOUSE-001"
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
                        }
                    }
                }
            }
        }
    }
