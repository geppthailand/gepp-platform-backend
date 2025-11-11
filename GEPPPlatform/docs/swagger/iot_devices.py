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
        "/api/auth/iot-devices/login": {
            "post": {
                "tags": ["IOT Devices"],
                "summary": "IoT device credential login",
                "description": "Authenticate an IoT device using device_name or MAC address plus password. Returns short-lived auth token and refresh token with device info.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/IotDeviceCredentialLoginRequest"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/DeviceLoginResponse"}
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/BadRequestError"},
                    "401": {"$ref": "#/components/responses/UnauthorizedError"}
                }
            }
        },
        "/api/auth/qr-login": {
            "post": {
                "tags": ["IOT Devices"],
                "summary": "QR login (user via QR token)",
                "description": "Authenticate a user using a short-lived QR token (email, password, expiry). Returns auth and refresh tokens like normal user login.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/IotDeviceQRLoginRequest"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LoginResponse"}
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/BadRequestError"},
                    "401": {"$ref": "#/components/responses/UnauthorizedError"}
                }
            }
        },
        "/api/iot-devices/my-memberships": {
            "post": {
                "tags": ["IOT Devices"],
                "summary": "List locations where current user is a dataInput member",
                "description": "Requires Bearer device token. Provide user JWT token in body via `user_token` to resolve memberships. Returns reduced location objects: id, display_name, materials.",
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
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/IotDeviceUserTokenRequest"}
                        }
                    }
                },
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
        },
        "/api/iot-devices/records": {
            "post": {
                "tags": ["IOT Devices"],
                "summary": "Create transaction record from IoT device",
                "description": "Requires Bearer device token in Authorization header. Optionally include a `user_token` in the request body to attribute the record to a user.",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/IotDeviceCreateRecordRequest"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Record created successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SuccessResponse"}
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/UnauthorizedError"},
                    "500": {"$ref": "#/components/responses/InternalServerError"}
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
        "IotDeviceCredentialLoginRequest": {
            "type": "object",
            "required": ["password"],
            "properties": {
                "device_name": {"type": "string", "description": "Device name (optional)"},
                "mac_address_bluetooth": {"type": "string", "description": "Bluetooth MAC (optional)"},
                "mac_address_tablet": {"type": "string", "description": "Tablet MAC (optional)"},
                "password": {"type": "string", "format": "password", "description": "Device password (bcrypt-hashed on server)"}
            },
            "oneOf": [
                {"required": ["device_name"]},
                {"required": ["mac_address_bluetooth"]},
                {"required": ["mac_address_tablet"]}
            ]
        },
        "IotDeviceQRLoginRequest": {
            "type": "object",
            "required": ["login-token"],
            "properties": {
                "login-token": {"type": "string", "description": "HS256-signed QR login token containing email, password, and expiry"}
            }
        },
        "DeviceInfo": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 7},
                "device_name": {"type": "string", "example": "Scale-FrontDesk"},
                "device_type": {"type": "string", "example": "scale"}
            }
        },
        "DeviceLoginResponse": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "example": True},
                "auth_token": {"type": "string", "description": "Short-lived auth token (15 min)"},
                "refresh_token": {"type": "string", "description": "Refresh token (7 days)"},
                "token_type": {"type": "string", "example": "Bearer"},
                "expires_in": {"type": "integer", "example": 900},
                "device": {"$ref": "#/components/schemas/DeviceInfo"}
            }
        },
        "IotDeviceTransactionRecord": {
            "type": "object",
            "required": [
                "material_id", "main_material_id", "category_id",
                "unit", "transaction_date", "origin_quantity",
                "origin_weight_kg", "transaction_type", "hazardous_level"
            ],
            "properties": {
                "material_id": {"type": "integer", "example": 307},
                "main_material_id": {"type": "integer", "example": 1},
                "category_id": {"type": "integer", "example": 1},
                "unit": {"type": "string", "example": "กิโลกรัม"},
                "transaction_date": {"type": "string", "format": "date-time", "example": "2025-11-04T17:00:00.000Z"},
                "origin_quantity": {"type": "number", "format": "float", "example": 23},
                "origin_weight_kg": {"type": "number", "format": "float", "example": 23},
                "images": {"type": "array", "items": {"type": "string"}, "example": []},
                "origin_price_per_unit": {"type": "number", "format": "float", "nullable": True, "example": 11},
                "total_amount": {"type": "number", "format": "float", "nullable": True, "example": 253},
                "transaction_type": {"type": "string", "example": "manual_input"},
                "hazardous_level": {"type": "integer", "example": 0},
                "notes": {"type": "string", "nullable": True, "example": "Destination: 2502"}
            }
        },
        "IotDeviceTransactionData": {
            "type": "object",
            "required": ["origin_id", "transaction_method", "status", "transaction_date", "records"],
            "properties": {
                "origin_id": {"type": "integer", "example": 2445},
                "transaction_method": {"type": "string", "example": "origin"},
                "status": {"type": "string", "example": "pending"},
                "transaction_date": {"type": "string", "format": "date-time", "example": "2025-11-04T08:50:23.052Z"},
                "notes": {"type": "string", "nullable": True, "example": "Created via web interface"},
                "images": {"type": "array", "items": {"type": "string"}, "example": []},
                "records": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/IotDeviceTransactionRecord"}
                }
            },
            "example": {
                "origin_id": 2445,
                "transaction_method": "origin",
                "status": "pending",
                "transaction_date": "2025-11-04T08:50:23.052Z",
                "notes": "Created via web interface",
                "images": [],
                "records": [
                    {
                        "material_id": 307,
                        "main_material_id": 1,
                        "category_id": 1,
                        "unit": "กิโลกรัม",
                        "transaction_date": "2025-11-04T17:00:00.000Z",
                        "origin_quantity": 23,
                        "origin_weight_kg": 23,
                        "images": [],
                        "origin_price_per_unit": 11,
                        "total_amount": 253,
                        "transaction_type": "manual_input",
                        "hazardous_level": 0,
                        "notes": "Destination: 2502"
                    },
                    {
                        "material_id": 289,
                        "main_material_id": 1,
                        "category_id": 1,
                        "unit": "กิโลกรัม",
                        "transaction_date": "2025-11-04T08:50:08.830Z",
                        "origin_quantity": 33,
                        "origin_weight_kg": 33,
                        "images": [],
                        "origin_price_per_unit": 2,
                        "total_amount": 66,
                        "transaction_type": "manual_input",
                        "hazardous_level": 0,
                        "notes": "Destination: 2502"
                    }
                ]
            }
        },
        "MaterialRef": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 101},
                "name_en": {"type": "string", "example": "PET Bottle"},
                "name_th": {"type": "string", "example": "ขวด PET"},
                "category_id": {"type": "integer", "nullable": True, "example": 5},
                "main_material_id": {"type": "integer", "nullable": True, "example": 2},
                "unit_name_th": {"type": "string", "example": "กก."},
                "unit_name_en": {"type": "string", "example": "kg"},
                "unit_weight": {"type": "number", "format": "float", "example": 1.0}
            }
        },
        "LocationReduced": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 123},
                "display_name": {"type": "string", "example": "Main Branch"},
                "materials": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/MaterialRef"}
                }
            }
        },
        "LocationsByMembershipResponse": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "example": True},
                "data": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/LocationReduced"}
                }
            }
        },
        "IotDeviceCreateRecordRequest": {
            "type": "object",
            "required": ["data"],
            "properties": {
                "user_token": {
                    "type": "string",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                },
                "data": {"$ref": "#/components/schemas/IotDeviceTransactionData"}
            }
        },
        "IotDeviceUserTokenRequest": {
            "type": "object",
            "required": ["user_token"],
            "properties": {
                "user_token": {
                    "type": "string",
                    "description": "User JWT token (HS256) to perform membership lookup",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                }
            }
        }
    }


