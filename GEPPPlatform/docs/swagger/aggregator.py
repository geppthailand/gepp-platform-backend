"""
Swagger/OpenAPI documentation aggregator
Combines all service specifications into a single OpenAPI document
"""

from typing import Dict, Any
import json

from .base import get_base_swagger_config
from .integration_bma import get_bma_integration_paths, get_bma_integration_schemas
from .auth import get_auth_paths, get_auth_schemas
from .iot_devices import get_iot_devices_paths, get_iot_devices_schemas


def merge_deep(base: Dict, update: Dict) -> Dict:
    """
    Deep merge two dictionaries

    Args:
        base: Base dictionary
        update: Dictionary to merge into base

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_deep(result[key], value)
        else:
            result[key] = value
    return result


def get_full_swagger_spec(deployment_state: str = "dev") -> Dict[str, Any]:
    """
    Generate complete Swagger/OpenAPI specification for all services

    Args:
        deployment_state: The deployment environment (dev, staging, prod)

    Returns:
        Complete OpenAPI 3.0 specification
    """
    # Start with base configuration
    spec = get_base_swagger_config(deployment_state)

    # Add Auth paths and schemas
    auth_paths = get_auth_paths()
    spec["paths"] = merge_deep(spec.get("paths", {}), auth_paths)

    auth_schemas = get_auth_schemas()
    if "components" not in spec:
        spec["components"] = {}
    if "schemas" not in spec["components"]:
        spec["components"]["schemas"] = {}
    spec["components"]["schemas"] = merge_deep(
        spec["components"]["schemas"],
        auth_schemas
    )

    # Add BMA Integration paths
    bma_paths = get_bma_integration_paths()
    spec["paths"] = merge_deep(spec["paths"], bma_paths)

    # Add BMA Integration schemas
    bma_schemas = get_bma_integration_schemas()
    spec["components"]["schemas"] = merge_deep(
        spec["components"]["schemas"],
        bma_schemas
    )

    # Add IoT Devices paths
    iot_paths = get_iot_devices_paths()
    spec["paths"] = merge_deep(spec["paths"], iot_paths)

    # Add IoT Devices schemas
    iot_schemas = get_iot_devices_schemas()
    spec["components"]["schemas"] = merge_deep(
        spec["components"]["schemas"],
        iot_schemas
    )

    # TODO: Add other service specifications here
    # Example:
    # transaction_paths = get_transaction_paths()
    # spec["paths"] = merge_deep(spec["paths"], transaction_paths)

    return spec


def get_swagger_ui_html(deployment_state: str = "dev") -> str:
    """
    Generate Swagger UI HTML page

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
    <title>GEPP Platform API Documentation</title>
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
            background-color: #1b1b1b !important;
        }}
        .swagger-ui .topbar .download-url-wrapper {{
            display: none;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.10.0/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.10.0/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            // Get the current path and construct the OpenAPI spec URL
            const currentPath = window.location.pathname;
            const basePath = currentPath.replace(/\/documents\/api-docs.*$/, '');
            const specUrl = basePath + '/documents/api-docs/openapi.json';

            // Construct the server URL from current location
            const protocol = window.location.protocol;
            const host = window.location.host;
            const serverUrl = protocol + '//' + host + basePath;

            // Fetch the spec and modify the servers
            fetch(specUrl)
                .then(response => response.json())
                .then(spec => {{
                    // Override servers with current URL
                    spec.servers = [
                        {{
                            url: basePath,
                            description: "Current Environment (Relative)"
                        }},
                        {{
                            url: serverUrl,
                            description: "Current Environment (Absolute)"
                        }}
                    ];

                    // Initialize Swagger UI with modified spec
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
                    // Fallback to URL-based loading if fetch fails
                    const ui = SwaggerUIBundle({{
                        url: specUrl,
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
                }});
        }};
    </script>
</body>
</html>
    """
    return html


def get_redoc_html(deployment_state: str = "dev") -> str:
    """
    Generate ReDoc HTML page (alternative documentation UI)

    Args:
        deployment_state: The deployment environment

    Returns:
        HTML string for ReDoc UI
    """
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEPP Platform API Documentation - ReDoc</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
        }}
    </style>
</head>
<body>
    <div id="redoc-container"></div>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
    <script>
        // Get the current path and construct the OpenAPI spec URL
        const currentPath = window.location.pathname;
        const basePath = currentPath.replace(/\/documents\/api-docs.*$/, '');
        const specUrl = basePath + '/documents/api-docs/openapi.json';

        // Initialize Redoc
        Redoc.init(specUrl, {{}}, document.getElementById('redoc-container'));
    </script>
</body>
</html>
    """
    return html
