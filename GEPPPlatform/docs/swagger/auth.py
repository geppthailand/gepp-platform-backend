"""
Swagger/OpenAPI documentation for Authentication endpoints
"""

from typing import Dict, Any


def get_auth_paths() -> Dict[str, Any]:
    """
    Get OpenAPI path specifications for authentication endpoints

    Returns:
        Dictionary of path specifications
    """
    return {
        "/api/auth/iot-devices/login": {
            "post": {
                "tags": ["IOT Devices"],
                "summary": "IoT device login via QR token",
                "description": "Authenticate an IoT user using a short-lived QR token that encodes email, password, and expiry. Returns a 15-minute auth token and a refresh token.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/IotDeviceLoginRequest"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LoginResponse"
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/BadRequestError"
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        },
        "/api/auth/login": {
            "post": {
                "tags": ["Authentication"],
                "summary": "User login (15-minute token)",
                "description": "Authenticate user with email and password. Returns short-lived auth token (15 min) and refresh token (7 days).",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/LoginRequest"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LoginResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        },
        "/api/auth/integration": {
            "post": {
                "tags": ["Authentication"],
                "summary": "Integration login (7-day token)",
                "description": "Authenticate for integration purposes using email and password. Returns long-lived token (7 days) tagged as 'integration' type. The JWT token is signed with user's unique secret key (auto-generated on first login if not exists). Use this for external system integrations.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/IntegrationLoginRequest"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Integration login successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/IntegrationLoginResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        },
        "/api/auth/integration/secret": {
            "post": {
                "tags": ["Authentication"],
                "summary": "Generate integration secret key",
                "description": "Generate or regenerate integration secret key for the authenticated user. Requires authentication with regular auth token. Keep this secret safe - it's used for integration authentication.",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Secret key generated successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/IntegrationSecretResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        },
        "/api/auth/register": {
            "post": {
                "tags": ["Authentication"],
                "summary": "Register new user",
                "description": "Register a new user account with organization",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/RegisterRequest"
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Registration successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LoginResponse"
                                }
                            }
                        }
                    },
                    "400": {
                        "$ref": "#/components/responses/ValidationError"
                    }
                }
            }
        },
        "/api/auth/validate": {
            "get": {
                "tags": ["Authentication"],
                "summary": "Validate token (from header)",
                "description": "Validate JWT token from Authorization header",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Token is valid",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/TokenValidationResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            },
            "post": {
                "tags": ["Authentication"],
                "summary": "Validate token (from body)",
                "description": "Validate JWT token from request body",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["token"],
                                "properties": {
                                    "token": {
                                        "type": "string",
                                        "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Token is valid",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/TokenValidationResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        },
        "/api/auth/refresh": {
            "post": {
                "tags": ["Authentication"],
                "summary": "Refresh auth token",
                "description": "Get new auth token using refresh token",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["refresh_token"],
                                "properties": {
                                    "refresh_token": {
                                        "type": "string",
                                        "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Token refreshed successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/LoginResponse"
                                }
                            }
                        }
                    },
                    "401": {
                        "$ref": "#/components/responses/UnauthorizedError"
                    }
                }
            }
        }
    }


def get_auth_schemas() -> Dict[str, Any]:
    """
    Get OpenAPI schema definitions for authentication

    Returns:
        Dictionary of schema definitions
    """
    return {
        "IotDeviceLoginRequest": {
            "type": "object",
            "required": ["token"],
            "properties": {
                "token": {
                    "type": "string",
                    "description": "HS256-signed QR login token containing email, password, and expiry",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImJpdGVjQGdlcHAubWUiLCJwYXNzd29yZCI6IkFiY2RlZmchMTIzIiwiZXhwaXJlZF9kYXRlIjoiMjAyNS0xMC0zMFQxMjozNTo1NloifQ.dyOO8uFApU_XuT0UhFWv096cQSGvcGZHfQ44f3iKXOY"
                }
            }
        },
        "LoginRequest": {
            "type": "object",
            "required": ["email", "password"],
            "properties": {
                "email": {
                    "type": "string",
                    "format": "email",
                    "example": "user@example.com"
                },
                "password": {
                    "type": "string",
                    "format": "password",
                    "example": "SecurePassword123"
                }
            }
        },
        "IntegrationLoginRequest": {
            "type": "object",
            "required": ["email", "password"],
            "properties": {
                "email": {
                    "type": "string",
                    "format": "email",
                    "example": "user@example.com"
                },
                "password": {
                    "type": "string",
                    "format": "password",
                    "description": "User password",
                    "example": "your_password"
                }
            }
        },
        "RegisterRequest": {
            "type": "object",
            "required": ["email", "password", "firstName", "lastName"],
            "properties": {
                "email": {
                    "type": "string",
                    "format": "email",
                    "example": "newuser@example.com"
                },
                "password": {
                    "type": "string",
                    "format": "password",
                    "example": "SecurePassword123"
                },
                "firstName": {
                    "type": "string",
                    "example": "John"
                },
                "lastName": {
                    "type": "string",
                    "example": "Doe"
                },
                "phoneNumber": {
                    "type": "string",
                    "example": "+66812345678"
                },
                "displayName": {
                    "type": "string",
                    "example": "John Doe"
                },
                "accountType": {
                    "type": "string",
                    "example": "organization"
                }
            }
        },
        "LoginResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "auth_token": {
                    "type": "string",
                    "description": "Short-lived authentication token (15 minutes)",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                },
                "refresh_token": {
                    "type": "string",
                    "description": "Long-lived refresh token (7 days)",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                },
                "token_type": {
                    "type": "string",
                    "example": "Bearer"
                },
                "expires_in": {
                    "type": "integer",
                    "description": "Token expiration time in seconds",
                    "example": 900
                },
                "user": {
                    "$ref": "#/components/schemas/UserInfo"
                }
            }
        },
        "IntegrationLoginResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "token": {
                    "type": "string",
                    "description": "Long-lived integration token (7 days) with 'integration' type tag",
                    "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                },
                "token_type": {
                    "type": "string",
                    "example": "Bearer"
                },
                "expires_in": {
                    "type": "integer",
                    "description": "Token expiration time in seconds (7 days = 604800)",
                    "example": 604800
                },
                "user": {
                    "$ref": "#/components/schemas/UserInfo"
                }
            }
        },
        "TokenValidationResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "user": {
                    "$ref": "#/components/schemas/UserInfo"
                }
            }
        },
        "IntegrationSecretResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "example": True
                },
                "message": {
                    "type": "string",
                    "example": "Integration secret key generated successfully"
                },
                "secret": {
                    "type": "string",
                    "description": "Your integration secret key - keep this safe!",
                    "example": "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz"
                },
                "user": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "integer",
                            "example": 1
                        },
                        "email": {
                            "type": "string",
                            "example": "user@example.com"
                        }
                    }
                }
            }
        },
        "UserInfo": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "example": 1
                },
                "email": {
                    "type": "string",
                    "example": "user@example.com"
                },
                "displayName": {
                    "type": "string",
                    "example": "John Doe"
                },
                "organizationId": {
                    "type": "integer",
                    "example": 1
                }
            }
        }
    }
