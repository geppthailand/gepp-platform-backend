"""
OpenAPI/Swagger Documentation for Event Dashboard V1 API
"""

from typing import Dict, Any


def get_swagger_spec() -> Dict[str, Any]:
    """Returns the OpenAPI 3.0 specification for Event Dashboard V1 API."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Event Dashboard V1 API",
            "version": "1.0.0",
            "description": "Event dashboard API providing waste statistics (recycling rate, GHG, material breakdown, timeseries, tenant split) and organization structure sub-tree extraction.",
            "contact": {
                "name": "GEPP Platform Support",
                "url": "https://gepp.co.th"
            }
        },
        "servers": [
            {
                "url": "https://api.geppdata.com/v1/api/userapi/{api_path}/event-dashboard-v1",
                "description": "Production API",
                "variables": {
                    "api_path": {
                        "description": "Organization-specific API path",
                        "default": "your-api-path-here"
                    }
                }
            }
        ],
        "security": [
            {"bearerAuth": []}
        ],
        "tags": [
            {"name": "Dashboard", "description": "Event dashboard data endpoints"},
            {"name": "Structure", "description": "Organization structure endpoints"},
            {"name": "Management", "description": "Status and documentation"}
        ],
        "paths": {
            "/overall-waste-data": {
                "get": {
                    "tags": ["Dashboard"],
                    "summary": "Get overall waste statistics",
                    "description": "Returns comprehensive waste statistics for a location sub-tree within a date range. Weight is calculated as origin_quantity × Material.unit_weight. Date filtering uses TransactionRecord.transaction_date.",
                    "operationId": "getOverallWasteData",
                    "parameters": [
                        {
                            "name": "user_location_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Root location ID — all descendant locations in the org tree are included"
                        },
                        {
                            "name": "start_date",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "format": "date"},
                            "description": "Start of date range (ISO format: YYYY-MM-DD)",
                            "example": "2026-01-01"
                        },
                        {
                            "name": "end_date",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "format": "date"},
                            "description": "End of date range (ISO format: YYYY-MM-DD)",
                            "example": "2026-03-23"
                        },
                        {
                            "name": "interval",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 86400},
                            "description": "Timeseries bucket size in seconds. Default: 86400 (1 day). Use 900 for 15min, 3600 for hourly, 604800 for weekly."
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Waste statistics",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/OverallWasteDataResponse"},
                                    "example": {
                                        "success": True,
                                        "user_location_id": 123,
                                        "start_date": "2026-01-01",
                                        "end_date": "2026-03-23",
                                        "total_weight_kg": 15000.5,
                                        "recycling_rate": 0.72,
                                        "ghg_reduction_kg": 8500.2,
                                        "tree_equivalent": 894.76,
                                        "material_breakdown": [
                                            {
                                                "category_id": 1,
                                                "category_name_th": "รีไซเคิลได้",
                                                "category_name_en": "Recyclable",
                                                "color": "#4CAF50",
                                                "total_weight_kg": 10800.3,
                                                "materials": [
                                                    {
                                                        "material_id": 5,
                                                        "name_th": "ขวด PET",
                                                        "name_en": "PET Bottle",
                                                        "weight_kg": 3200.1,
                                                        "percentage": 0.213,
                                                        "ghg_kg": 1920.0
                                                    }
                                                ]
                                            }
                                        ],
                                        "timeseries": {
                                            "timestamp": ["2026-01-01T00:00:00", "2026-01-01T00:15:00"],
                                            "sum_weight": [500.2, 320.1],
                                            "recycling_rate": [0.72, 0.65]
                                        },
                                        "tenant_split": [
                                            {
                                                "tenant_id": 10,
                                                "tenant_name": "Tenant A",
                                                "sum_weight": 7500.0,
                                                "recycling_rate": 0.68
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"}
                    }
                }
            },
            "/structure-of": {
                "get": {
                    "tags": ["Structure"],
                    "summary": "Get organization structure sub-tree",
                    "description": "Extracts the sub-tree rooted at the given user_location_id from the organization setup. Each node includes id, name, level (branch/building/floor/room), and children.",
                    "operationId": "getStructureOf",
                    "parameters": [
                        {
                            "name": "user_location_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Node ID to extract sub-tree from"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Organization structure sub-tree",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/StructureOfResponse"},
                                    "example": {
                                        "success": True,
                                        "user_location_id": 123,
                                        "node": {
                                            "id": 123,
                                            "name": "สาขา A",
                                            "name_en": "Branch A",
                                            "display_name": "สาขา A",
                                            "level": "branch",
                                            "children": [
                                                {
                                                    "id": 456,
                                                    "name": "อาคาร 1",
                                                    "name_en": "Building 1",
                                                    "display_name": "อาคาร 1",
                                                    "level": "building",
                                                    "children": []
                                                }
                                            ]
                                        },
                                        "descendant_ids": [123, 456, 789]
                                    }
                                }
                            }
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": {"$ref": "#/components/responses/NotFound"}
                    }
                }
            },
            "/status": {
                "get": {
                    "tags": ["Management"],
                    "summary": "Get service status",
                    "description": "Returns service health and available endpoints",
                    "operationId": "getStatus",
                    "responses": {
                        "200": {
                            "description": "Service status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "service": {"type": "string"},
                                            "version": {"type": "string"},
                                            "status": {"type": "string"},
                                            "endpoints": {"type": "array", "items": {"type": "string"}}
                                        }
                                    }
                                }
                            }
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
                    "description": "JWT token with organization_id claim"
                }
            },
            "schemas": {
                "OverallWasteDataResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "user_location_id": {"type": "integer"},
                        "start_date": {"type": "string", "format": "date"},
                        "end_date": {"type": "string", "format": "date"},
                        "total_weight_kg": {"type": "number", "description": "Total waste weight in kg"},
                        "recycling_rate": {"type": "number", "description": "Recycling rate (0-1)"},
                        "ghg_reduction_kg": {"type": "number", "description": "GHG reduction in kg CO2"},
                        "tree_equivalent": {"type": "number", "description": "Tree equivalent (1 tree = 9.5 kg CO2/year)"},
                        "material_breakdown": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/CategoryBreakdown"}
                        },
                        "timeseries": {"$ref": "#/components/schemas/TimeseriesData"},
                        "tenant_split": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/TenantEntry"}
                        }
                    }
                },
                "CategoryBreakdown": {
                    "type": "object",
                    "properties": {
                        "category_id": {"type": "integer"},
                        "category_name_th": {"type": "string"},
                        "category_name_en": {"type": "string"},
                        "color": {"type": "string", "description": "Hex color code"},
                        "total_weight_kg": {"type": "number"},
                        "materials": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/MaterialEntry"}
                        }
                    }
                },
                "MaterialEntry": {
                    "type": "object",
                    "properties": {
                        "material_id": {"type": "integer"},
                        "name_th": {"type": "string"},
                        "name_en": {"type": "string"},
                        "weight_kg": {"type": "number"},
                        "percentage": {"type": "number", "description": "Fraction of total weight (0-1)"},
                        "ghg_kg": {"type": "number", "description": "GHG reduction in kg CO2"}
                    }
                },
                "TimeseriesData": {
                    "type": "object",
                    "description": "Parallel arrays for easy graph plotting. Arrays are aligned by index.",
                    "properties": {
                        "timestamp": {
                            "type": "array",
                            "items": {"type": "string", "format": "date-time"},
                            "description": "Bucket start timestamps (ISO format)"
                        },
                        "sum_weight": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Total weight (kg) per bucket"
                        },
                        "recycling_rate": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Recycling rate (0-1) per bucket"
                        }
                    }
                },
                "TenantEntry": {
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "integer"},
                        "tenant_name": {"type": "string"},
                        "sum_weight": {"type": "number", "description": "Total weight (kg) for this tenant"},
                        "recycling_rate": {"type": "number", "description": "Recycling rate (0-1) for this tenant"}
                    }
                },
                "StructureOfResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "user_location_id": {"type": "integer"},
                        "node": {"$ref": "#/components/schemas/TreeNode"},
                        "descendant_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "All descendant location IDs (flat list)"
                        }
                    }
                },
                "TreeNode": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string", "description": "Display name (display_name or name_en)"},
                        "name_en": {"type": "string", "nullable": True},
                        "display_name": {"type": "string", "nullable": True},
                        "level": {"type": "string", "nullable": True, "description": "branch, building, floor, or room"},
                        "address": {"type": "string", "nullable": True},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/TreeNode"}
                        }
                    }
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "error": {"type": "string"},
                        "message": {"type": "string"}
                    }
                }
            },
            "responses": {
                "BadRequest": {
                    "description": "Invalid request parameters",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"},
                            "example": {
                                "success": False,
                                "error": "MISSING_PARAM",
                                "message": "user_location_id, start_date, and end_date are required"
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
                                "error": "NODE_NOT_FOUND",
                                "message": "Node not found in organization setup"
                            }
                        }
                    }
                }
            }
        }
    }
