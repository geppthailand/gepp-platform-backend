"""
BMA Public Integration Swagger/OpenAPI Documentation
Filtered documentation for external BMA integration partners
"""

from typing import Dict, Any


def get_bma_public_swagger_spec(deployment_state: str = "dev") -> Dict[str, Any]:
    """
    Generate BMA-specific public API documentation

    Only includes endpoints relevant for BMA integration partners:
    - /api/auth/integration
    - /api/integration/bma/audit_status
    - /api/integration/bma/usage
    - /api/integration/bma/transaction [GET]
    - /api/integration/bma/transaction [POST]
    - /api/integration/bma/transaction/{transaction_version}/{house_id}

    Args:
        deployment_state: The deployment environment (dev, staging, prod)

    Returns:
        OpenAPI 3.0 specification for BMA public API
    """
    from .auth import get_auth_schemas
    from .integration_bma import get_bma_integration_schemas

    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "GEPP Platform - BMA Integration API",
            "version": "1.0.0",
            "description": """
# BMA Integration API Documentation

Welcome to the GEPP Platform BMA Integration API. This documentation is specifically designed for Bangkok Metropolitan Administration (BMA) integration partners.

## Getting Started

### 1. Authentication

First, obtain an integration token using your credentials:

```bash
POST /api/auth/integration
{
  "email": "your@email.com",
  "password": "your_password"
}
```

The token expires in **7 days** and is tagged as 'integration' type.

### 2. Using the Token

Include the token in all API requests:

```
Authorization: Bearer <your_integration_token>
```

### 3. Available Operations

- **Submit Transactions**: Upload waste transaction data
- **Query Transactions**: Retrieve transaction details with pagination
- **Check Audit Status**: Monitor AI audit processing status
- **View Usage**: Track API usage statistics

## Integration Workflow

```
1. Authenticate → Get integration token (7-day validity)
2. Submit transactions → POST /api/integration/bma/transaction
3. Monitor status → GET /api/integration/bma/audit_status
4. Retrieve results → GET /api/integration/bma/transaction
5. Track usage → GET /api/integration/bma/usage
```

## Support

For technical support or questions, please contact:
- Email: support@gepp.com
- Documentation: https://docs.gepp.com/integration/bma
            """,
            "contact": {
                "name": "GEPP Platform BMA Integration Support",
                "email": "support@gepp.com"
            }
        },
        "servers": [
            {
                "url": f"/{deployment_state}",
                "description": f"{deployment_state.capitalize()} Environment (Relative)"
            },
            {
                "url": f"https://api.geppdata.com/{deployment_state}",
                "description": f"Production - {deployment_state.capitalize()} Environment"
            }
        ],
        "security": [
            {
                "BearerAuth": []
            }
        ],
        "tags": [
            {
                "name": "Authentication",
                "description": "Integration authentication endpoints"
            },
            {
                "name": "BMA Transactions",
                "description": "Waste transaction management for BMA integration"
            },
            {
                "name": "BMA Monitoring",
                "description": "Audit status and usage monitoring"
            }
        ],
        "paths": {},
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Integration JWT token obtained from /api/auth/integration (7-day validity)"
                }
            },
            "schemas": {},
            "responses": {
                "UnauthorizedError": {
                    "description": "Authentication required or token invalid/expired",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/Error"
                            },
                            "example": {
                                "success": False,
                                "message": "Invalid token or insufficient permissions",
                                "error_code": "UNAUTHORIZED"
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
                                "message": "Invalid request format",
                                "error_code": "BAD_REQUEST"
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
        }
    }

    # Add Error schema
    spec["components"]["schemas"]["Error"] = {
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
    }

    # Import and add only the specific paths and schemas we need
    from .auth import get_auth_paths
    from .integration_bma import get_bma_integration_paths

    all_auth_paths = get_auth_paths()
    all_bma_paths = get_bma_integration_paths()

    # Filter to only include specific endpoints
    spec["paths"]["/api/auth/integration"] = all_auth_paths.get("/api/auth/integration", {})
    spec["paths"]["/api/integration/bma/audit_status"] = all_bma_paths.get("/api/integration/bma/audit_status", {})
    spec["paths"]["/api/integration/bma/usage"] = all_bma_paths.get("/api/integration/bma/usage", {})
    spec["paths"]["/api/integration/bma/transaction"] = all_bma_paths.get("/api/integration/bma/transaction", {})
    spec["paths"]["/api/integration/bma/transaction/{transaction_version}/{house_id}"] = all_bma_paths.get(
        "/api/integration/bma/transaction/{transaction_version}/{house_id}", {}
    )

    # Add required schemas
    auth_schemas = get_auth_schemas()
    bma_schemas = get_bma_integration_schemas()

    # Add only the schemas we need
    required_schemas = [
        "IntegrationLoginRequest",
        "LoginResponse",
        "UserInfo",
        "BmaAuditStatusResponse",
        "BmaUsageResponse",
        "BmaTransactionBatchRequest",
        "BmaTransactionBatchResponse",
        "BmaTransactionListResponse",
        "BmaTransactionGetResponse",
        "BmaMaterialAudit"
    ]

    for schema_name in required_schemas:
        if schema_name in auth_schemas:
            spec["components"]["schemas"][schema_name] = auth_schemas[schema_name]
        elif schema_name in bma_schemas:
            spec["components"]["schemas"][schema_name] = bma_schemas[schema_name]

    return spec


def get_bma_public_swagger_html(deployment_state: str = "dev") -> str:
    """
    Generate Swagger UI HTML for BMA public API documentation

    Args:
        deployment_state: The deployment environment

    Returns:
        HTML string for Swagger UI
    """
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEPP Platform - BMA Integration API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.10.0/swagger-ui.css">
    <style>
        html {{
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }}
        *, *:before, *:after {{
            box-sizing: inherit;
        }}
        body {{
            margin: 0;
            padding: 0;
        }}
        .topbar {{
            background-color: #1b5e20 !important;
        }}
        .swagger-ui .topbar .download-url-wrapper {{
            display: none;
        }}
        .swagger-ui .info .title {{
            color: #1b5e20;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.10.0/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.10.0/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            const currentPath = window.location.pathname;
            const basePath = currentPath.replace(/\\/docs\\/bma\\/.*$/, '');
            const specUrl = currentPath.replace(/\\/$/, '') + '/openapi.json';

            fetch(specUrl)
                .then(response => response.json())
                .then(spec => {{
                    spec.servers = [
                        {{
                            url: basePath,
                            description: "Current Environment (Relative)"
                        }},
                        {{
                            url: window.location.protocol + '//' + window.location.host + basePath,
                            description: "Current Environment (Absolute)"
                        }}
                    ];

                    const ui = SwaggerUIBundle({{
                        spec: spec,
                        dom_id: '#swagger-ui',
                        deepLinking: true,
                        presets: [
                            SwaggerUIBundle.presets.apis,
                            SwaggerUIStandalonePreset
                        ],
                        plugins: [
                            SwaggerUIBundle.plugins.DownloadUrl
                        ],
                        layout: "StandaloneLayout",
                        defaultModelsExpandDepth: 1,
                        defaultModelExpandDepth: 3,
                        docExpansion: "list",
                        filter: true,
                        showExtensions: true,
                        showCommonExtensions: true,
                        persistAuthorization: true
                    }});
                    window.ui = ui;
                }})
                .catch(error => {{
                    console.error('Error loading OpenAPI spec:', error);
                }});
        }};
    </script>
</body>
</html>
    """
    return html
