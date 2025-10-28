"""
Documentation API handlers
Serves Swagger/OpenAPI documentation
"""

from typing import Dict, Any
import json
import logging

from .swagger.aggregator import (
    get_full_swagger_spec,
    get_swagger_ui_html,
    get_redoc_html
)
from .swagger.bma_public import (
    get_bma_public_swagger_spec,
    get_bma_public_swagger_html
)

logger = logging.getLogger(__name__)


def handle_docs_routes(event: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for documentation routes

    Routes:
    - GET /documents/api-docs - Swagger UI (default)
    - GET /documents/api-docs/swagger - Swagger UI
    - GET /documents/api-docs/redoc - ReDoc UI
    - GET /documents/api-docs/openapi.json - OpenAPI JSON specification
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    path_params = params.get('path_params', {})

    # Extract deployment state from path params (set by app.py)
    deployment_state = path_params.get('deployment_state', 'dev')

    try:
        # BMA Public Documentation (specific hash-protected endpoint)
        if '/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c' in path:
            if path.endswith('/openapi.json'):
                # Return BMA public OpenAPI spec
                spec = get_bma_public_swagger_spec(deployment_state)
                return {
                    'content_type': 'application/json',
                    'body': json.dumps(spec, indent=2)
                }
            else:
                # Return BMA public Swagger UI
                return {
                    'content_type': 'text/html',
                    'body': get_bma_public_swagger_html(deployment_state)
                }

        # Swagger UI (default)
        elif path.endswith('/documents/api-docs') or path.endswith('/documents/api-docs/'):
            return {
                'content_type': 'text/html',
                'body': get_swagger_ui_html(deployment_state)
            }

        # Swagger UI (explicit)
        elif path.endswith('/documents/api-docs/swagger') or path.endswith('/documents/api-docs/swagger/'):
            return {
                'content_type': 'text/html',
                'body': get_swagger_ui_html(deployment_state)
            }

        # ReDoc UI
        elif path.endswith('/documents/api-docs/redoc') or path.endswith('/documents/api-docs/redoc/'):
            return {
                'content_type': 'text/html',
                'body': get_redoc_html(deployment_state)
            }

        # OpenAPI JSON specification
        elif path.endswith('/documents/api-docs/openapi.json'):
            spec = get_full_swagger_spec(deployment_state)
            return {
                'content_type': 'application/json',
                'body': json.dumps(spec, indent=2)
            }

        # OpenAPI YAML specification
        elif path.endswith('/documents/api-docs/openapi.yaml') or path.endswith('/documents/api-docs/openapi.yml'):
            try:
                import yaml
                spec = get_full_swagger_spec(deployment_state)
                return {
                'content_type': 'application/x-yaml',
                    'body': yaml.dump(spec, default_flow_style=False, sort_keys=False)
                }
            except ImportError:
                return {
                    'content_type': 'application/json',
                    'body': json.dumps({
                        'error': 'YAML support not available. Install PyYAML package.',
                        'alternative': f'/{deployment_state}/documents/api-docs/openapi.json'
                    })
                }

        # Index page
        elif '/documents/api-docs' in path:
            return {
                'content_type': 'text/html',
                'body': get_docs_index_html(deployment_state)
            }

        else:
            return {
                'content_type': 'application/json',
                'body': json.dumps({
                    'error': 'Route not found',
                    'available_routes': [
                        f'/{deployment_state}/documents/api-docs',
                        f'/{deployment_state}/documents/api-docs/swagger',
                        f'/{deployment_state}/documents/api-docs/redoc',
                        f'/{deployment_state}/documents/api-docs/openapi.json',
                        f'/{deployment_state}/documents/api-docs/openapi.yaml'
                    ]
                })
            }

    except Exception as e:
        logger.error(f"Error serving documentation: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'content_type': 'application/json',
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def get_docs_index_html(deployment_state: str = "dev") -> str:
    """
    Generate documentation index/landing page

    Args:
        deployment_state: The deployment environment

    Returns:
        HTML string for documentation index
    """
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEPP Platform API Documentation</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 800px;
            width: 100%;
            padding: 40px;
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1em;
        }}
        .badge {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            margin-bottom: 20px;
            text-transform: uppercase;
        }}
        .card-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }}
        .card {{
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            padding: 24px;
            text-decoration: none;
            color: inherit;
            transition: all 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            border-color: #667eea;
        }}
        .card h3 {{
            color: #667eea;
            margin-bottom: 10px;
            font-size: 1.3em;
        }}
        .card p {{
            color: #666;
            line-height: 1.6;
        }}
        .info-section {{
            margin-top: 40px;
            padding-top: 30px;
            border-top: 2px solid #e9ecef;
        }}
        .info-section h2 {{
            color: #333;
            margin-bottom: 15px;
        }}
        .info-section ul {{
            list-style: none;
            padding-left: 0;
        }}
        .info-section li {{
            padding: 8px 0;
            color: #666;
        }}
        .info-section li:before {{
            content: "✓ ";
            color: #667eea;
            font-weight: bold;
            margin-right: 8px;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <span class="badge">{deployment_state} Environment</span>
        <h1>🌿 GEPP Platform API</h1>
        <p class="subtitle">Comprehensive API for Waste Management & Sustainability</p>

        <div class="card-grid">
            <a href="swagger" class="card">
                <h3>📚 Swagger UI</h3>
                <p>Interactive API documentation with try-it-out functionality</p>
            </a>

            <a href="redoc" class="card">
                <h3>📖 ReDoc</h3>
                <p>Clean, responsive API reference documentation</p>
            </a>

            <a href="openapi.json" class="card">
                <h3>📄 OpenAPI JSON</h3>
                <p>Download the OpenAPI 3.0 specification in JSON format</p>
            </a>

            <a href="openapi.yaml" class="card">
                <h3>📝 OpenAPI YAML</h3>
                <p>Download the OpenAPI 3.0 specification in YAML format</p>
            </a>
        </div>

        <div class="info-section">
            <h2>Available API Modules</h2>
            <ul>
                <li><strong>Auth</strong> - Authentication and authorization</li>
                <li><strong>Organizations</strong> - Organization and location management</li>
                <li><strong>Users</strong> - User profiles and permissions</li>
                <li><strong>Materials</strong> - Material catalog and categories</li>
                <li><strong>Transactions</strong> - Waste transaction tracking</li>
                <li><strong>Audit</strong> - Transaction auditing and compliance</li>
                <li><strong>Reports</strong> - Analytics and reporting</li>
                <li><strong>Integration</strong> - External system integrations (BMA)</li>
            </ul>
        </div>

        <div class="info-section">
            <h2>Quick Start</h2>
            <ul>
                <li>Most endpoints require JWT authentication</li>
                <li>Include token in header: <code>Authorization: Bearer &lt;token&gt;</code></li>
                <li>Base URL: <code>/{deployment_state}/api/*</code></li>
                <li>Content-Type: <code>application/json</code></li>
            </ul>
        </div>
    </div>
</body>
</html>
    """
    return html
