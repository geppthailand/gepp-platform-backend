# GEPP Platform API Documentation System

## Overview

The GEPP Platform provides comprehensive, hierarchical API documentation using Swagger/OpenAPI 3.0 specification. The documentation is automatically generated and served through multiple interfaces.

## Documentation Structure

```
GEPPPlatform/
├── docs/
│   ├── __init__.py
│   ├── README.md                    # This file
│   ├── docs_handlers.py             # Documentation route handlers
│   └── swagger/
│       ├── __init__.py
│       ├── base.py                  # Base OpenAPI configuration
│       ├── aggregator.py            # Combines all service specs
│       ├── integration_bma.py       # BMA Integration API specs
│       └── [future service specs]   # Other service specifications
```

## Accessing Documentation

### Available Endpoints

All documentation endpoints are accessible at `/{deployment_state}/docs/*`:

| Endpoint | Description |
|----------|-------------|
| `/{d}/docs` | Documentation landing page with links to all documentation formats |
| `/{d}/docs/swagger` | Swagger UI - Interactive API documentation |
| `/{d}/docs/redoc` | ReDoc - Clean, responsive API reference |
| `/{d}/docs/openapi.json` | OpenAPI 3.0 specification in JSON format |
| `/{d}/docs/openapi.yaml` | OpenAPI 3.0 specification in YAML format |

Where `{d}` is the deployment state: `dev`, `staging`, or `prod`

### Examples

#### Development Environment
- Landing Page: `https://api.gepp.com/dev/docs`
- Swagger UI: `https://api.gepp.com/dev/docs/swagger`
- ReDoc: `https://api.gepp.com/dev/docs/redoc`
- JSON Spec: `https://api.gepp.com/dev/docs/openapi.json`

#### Production Environment
- Landing Page: `https://api.gepp.com/prod/docs`
- Swagger UI: `https://api.gepp.com/prod/docs/swagger`
- ReDoc: `https://api.gepp.com/prod/docs/redoc`
- JSON Spec: `https://api.gepp.com/prod/docs/openapi.json`

## Documentation Features

### 🎨 Multiple UI Options

1. **Swagger UI**
   - Interactive "Try it out" functionality
   - Built-in request/response examples
   - OAuth/JWT authentication support
   - Persistent authorization across sessions

2. **ReDoc**
   - Clean, responsive design
   - Advanced search capabilities
   - Three-panel layout for easy navigation
   - Mobile-friendly interface

3. **Raw Specifications**
   - JSON format for programmatic access
   - YAML format for human readability
   - Can be imported into Postman, Insomnia, etc.

### 📚 Hierarchical Organization

Documentation is organized by service modules:

- **Auth** - Authentication and authorization
- **Organizations** - Organization and location management
- **Users** - User profiles and permissions
- **Materials** - Material catalog and categories
- **Transactions** - Waste transaction tracking
- **Audit** - Transaction auditing and compliance
- **Reports** - Analytics and reporting
- **Integration** - External system integrations
  - **BMA** - Bangkok Metropolitan Administration

### 🔐 Security Definitions

- JWT Bearer token authentication
- Automatic authentication UI in Swagger
- Persistent authorization state
- Clear security requirements per endpoint

## Adding Documentation for New Services

### Step 1: Create Service Specification File

Create a new file in `GEPPPlatform/docs/swagger/` for your service:

```python
# GEPPPlatform/docs/swagger/my_service.py

from typing import Dict, Any

def get_my_service_paths() -> Dict[str, Any]:
    """
    Get path specifications for My Service API
    """
    return {
        "/api/myservice/endpoint": {
            "get": {
                "tags": ["My Service"],
                "summary": "Endpoint summary",
                "description": "Detailed description",
                "operationId": "getMyServiceData",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "param1",
                        "in": "query",
                        "description": "Parameter description",
                        "required": False,
                        "schema": {
                            "type": "string"
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MyServiceResponse"
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

def get_my_service_schemas() -> Dict[str, Any]:
    """
    Get schema definitions for My Service
    """
    return {
        "MyServiceResponse": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean"
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "integer"
                        },
                        "name": {
                            "type": "string"
                        }
                    }
                }
            }
        }
    }
```

### Step 2: Add to Aggregator

Update `GEPPPlatform/docs/swagger/aggregator.py`:

```python
from .my_service import get_my_service_paths, get_my_service_schemas

def get_full_swagger_spec(deployment_state: str = "dev") -> Dict[str, Any]:
    # ... existing code ...

    # Add My Service paths
    my_service_paths = get_my_service_paths()
    spec["paths"] = merge_deep(spec["paths"], my_service_paths)

    # Add My Service schemas
    my_service_schemas = get_my_service_schemas()
    spec["components"]["schemas"] = merge_deep(
        spec["components"]["schemas"],
        my_service_schemas
    )

    return spec
```

### Step 3: Add Tag to Base Configuration

Update `GEPPPlatform/docs/swagger/base.py` to add your service tag:

```python
"tags": [
    # ... existing tags ...
    {
        "name": "My Service",
        "description": "Description of my service"
    }
]
```

## OpenAPI 3.0 Best Practices

### Request Bodies

```python
"requestBody": {
    "required": True,
    "description": "Request body description",
    "content": {
        "application/json": {
            "schema": {
                "$ref": "#/components/schemas/MyRequestSchema"
            },
            "examples": {
                "example1": {
                    "summary": "Example 1",
                    "value": {
                        "field": "value"
                    }
                }
            }
        }
    }
}
```

### Responses

```python
"responses": {
    "200": {
        "description": "Success",
        "content": {
            "application/json": {
                "schema": {
                    "$ref": "#/components/schemas/SuccessResponse"
                },
                "examples": {
                    "success": {
                        "summary": "Successful response",
                        "value": {
                            "success": True,
                            "data": {}
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
        "$ref": "#/components/responses/NotFoundError"
    },
    "500": {
        "$ref": "#/components/responses/InternalServerError"
    }
}
```

### Reusable Components

Use `$ref` to reference reusable components:

```python
# Schema reference
"schema": {
    "$ref": "#/components/schemas/MySchema"
}

# Response reference
"responses": {
    "401": {
        "$ref": "#/components/responses/UnauthorizedError"
    }
}

# Parameter reference
"parameters": [
    {
        "$ref": "#/components/parameters/PageParameter"
    }
]
```

## Common Schema Patterns

### Pagination

```python
"parameters": [
    {
        "name": "page",
        "in": "query",
        "schema": {
            "type": "integer",
            "minimum": 1,
            "default": 1
        }
    },
    {
        "name": "limit",
        "in": "query",
        "schema": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20
        }
    }
]
```

### List Response

```python
"ListResponse": {
    "type": "object",
    "properties": {
        "success": {
            "type": "boolean"
        },
        "data": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "$ref": "#/components/schemas/Item"
                    }
                },
                "total": {
                    "type": "integer"
                },
                "page": {
                    "type": "integer"
                },
                "limit": {
                    "type": "integer"
                }
            }
        }
    }
}
```

## Testing Documentation

### Local Testing

1. Start your development server
2. Navigate to `http://localhost:3000/dev/docs`
3. Test all endpoints using Swagger UI's "Try it out" feature

### Validation

Use online validators to check your OpenAPI spec:

- [Swagger Editor](https://editor.swagger.io/) - Paste JSON/YAML spec
- [OpenAPI Validator](https://apitools.dev/swagger-parser/online/) - Validate spec

### Export and Share

1. Download JSON: `/{d}/docs/openapi.json`
2. Download YAML: `/{d}/docs/openapi.yaml`
3. Import into tools:
   - Postman
   - Insomnia
   - API testing frameworks

## Maintenance

### Keeping Documentation Up-to-Date

1. **When adding new endpoints**: Create specification in appropriate service file
2. **When modifying endpoints**: Update the corresponding specification
3. **When deprecating endpoints**: Mark with `deprecated: true`
4. **Version changes**: Update version in `base.py`

### Documentation Review Checklist

- [ ] All endpoints documented
- [ ] Request/response schemas defined
- [ ] Examples provided for complex requests
- [ ] Security requirements specified
- [ ] Error responses documented
- [ ] Parameter descriptions clear
- [ ] Tags assigned correctly
- [ ] Tested in Swagger UI

## Troubleshooting

### Documentation not loading

1. Check server logs for errors
2. Validate OpenAPI spec at `/{d}/docs/openapi.json`
3. Ensure all `$ref` references are valid
4. Check for circular references in schemas

### Swagger UI shows errors

1. Check browser console for JavaScript errors
2. Verify OpenAPI spec is valid JSON
3. Check CORS headers if accessing from different domain

### Missing schemas or paths

1. Verify import in `aggregator.py`
2. Check for typos in `$ref` paths
3. Ensure function returns correct structure

## Resources

- [OpenAPI 3.0 Specification](https://swagger.io/specification/)
- [Swagger UI Documentation](https://swagger.io/tools/swagger-ui/)
- [ReDoc Documentation](https://redocly.com/docs/redoc/)
- [OpenAPI Best Practices](https://swagger.io/blog/api-design/openapi-best-practices/)

## Support

For questions or issues with the documentation system:
- Check this README first
- Review existing service specifications for examples
- Contact the GEPP Platform development team
