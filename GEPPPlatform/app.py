from datetime import datetime, timedelta
from time import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from dateutil.parser import parse
import threading
import boto3
import zipfile

# import pandas as pd
import numpy as np
import zlib
import base64

import json
import os
from glob import glob
import math
import gzip
import pickle
import re
from boto3.dynamodb.conditions import Key, Attr
import bcrypt


from pgvector.psycopg2 import register_vector
import psycopg2 as pg
import jwt

from GEPPPlatform.services.auth import handle_auth_routes
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.libs import authGuard
from GEPPPlatform.exceptions import APIException, UnauthorizedException
from GEPPPlatform.database import get_session

import random
import string
import logging

logger = logging.getLogger(__name__)

def main(event, context):
    try:
        # Get HTTP method
        http_method = event['requestContext']['http'].get("method", "POST")
        raw_path = event.get("rawPath")

        # Extract deployment state from path if present
        # Support pattern: /{deployment_state}/api/* or /api/*
        deployment_state = None
        path = raw_path

        # Check if path starts with /{something}/api/
        path_parts = raw_path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[1] == 'api':
            # Path has format: /{deployment_state}/api/*
            deployment_state = path_parts[0]
            # Normalize path to /api/* for routing
            path = '/' + '/'.join(path_parts[1:])
        elif path_parts[0] == 'api':
            # Path has format: /api/*
            path = raw_path

        # Handle CORS preflight
        if http_method == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"message": "CORS preflight"})
            }

        # Parse request body and query parameters
        body = {}
        query_params = event.get("queryStringParameters") or {}
        path_params = event.get("pathParameters") or {}

        # Add deployment state to path params if present
        if deployment_state:
            path_params['deployment_state'] = deployment_state
        
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError:
                return {
                    "statusCode": 400,
                    "headers": {
                        "Content-Type": "application/json",
                    },
                    "body": json.dumps({"error": "Invalid JSON in request body"})
                }
        
        results = {}

        # CORS headers
        headers = {
            # 'Access-Control-Allow-Origin': '*',
            # 'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            # 'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Content-Type': 'application/json'
        }

        # Use SQLAlchemy session instead of direct psycopg2 connection
        with get_session() as session:
            commonParams = {
                "db_session": session,
                "method": http_method,
                "query_params": query_params,
                "path_params": path_params,
                "headers": event.get("headers", {}),
            }

            # Route based on path and method
            if "/api/auth" in path:
                # Handle all auth routes through auth module (no authorization required)
                # Includes: login, register, register/check-email, refresh, validate, etc.
                # Support both legacy format and direct data for POST requests
                auth_result = handle_auth_routes(path, data=body, **commonParams)
                results = {"data": auth_result}

            elif "/documents/api-docs" in raw_path or "/docs/bma/" in raw_path:
                # Handle documentation routes (no authorization required)
                from .docs.docs_handlers import handle_docs_routes

                docs_result = handle_docs_routes(event, **commonParams)
                content_type = docs_result.get('content_type', 'application/json')

                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": content_type,
                    },
                    "body": docs_result.get('body', '')
                }

            elif path == "/health" or "/health" in path:
                # Health check endpoint (no authorization required)
                results = {"status": "healthy", "timestamp": datetime.now().isoformat(), "method": http_method}

            elif "/api/userapi/documents/" in path:
                # PUBLIC: Handle API documentation routes (no authentication required)
                # Pattern: /api/userapi/documents/{service_path}
                # Example: /api/userapi/documents/ai_audit/v1
                try:
                    # Extract service_path from URL
                    parts = path.split('/api/userapi/documents/')[1].split('/')
                    if len(parts) < 1:
                        return {
                            "statusCode": 400,
                            "headers": headers,
                            "body": json.dumps({
                                "success": False,
                                "message": "Invalid documentation path. Expected: /api/userapi/documents/{service_path}",
                                "error_code": "INVALID_PATH"
                            })
                        }
                    
                    # Reconstruct service_path (e.g., "ai_audit/v1")
                    service_path = '/'.join(parts).split('?')[0]
                    
                    logger.info(f"Documentation request for service_path: {service_path}")
                    
                    # Try to import the swagger module for the service
                    try:
                        # Map service_path to function module
                        # For example: 'ai_audit/v1' -> 'ai_audit_v1'
                        function_module_name = service_path.replace('/', '_')
                        
                        # Import the swagger module dynamically
                        swagger_module = __import__(
                            f'GEPPPlatform.services.custom.functions.{function_module_name}.swagger',
                            fromlist=['get_swagger_spec']
                        )
                        
                        # Get the swagger spec
                        swagger_spec = swagger_module.get_swagger_spec()
                        
                        # Generate Swagger UI HTML page
                        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{swagger_spec['info']['title']} - API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.10.5/swagger-ui.css" />
    <style>
        body {{
            margin: 0;
            padding: 0;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.10.5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.10.5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            const spec = {json.dumps(swagger_spec)};
            
            SwaggerUIBundle({{
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
                layout: "StandaloneLayout"
            }});
        }};
    </script>
</body>
</html>"""
                        
                        return {
                            "statusCode": 200,
                            "headers": {
                                "Content-Type": "text/html; charset=utf-8"
                            },
                            "body": html_content
                        }
                        
                    except ImportError as e:
                        return {
                            "statusCode": 404,
                            "headers": headers,
                            "body": json.dumps({
                                "success": False,
                                "message": f"Documentation not found for service: {service_path}",
                                "error_code": "DOCS_NOT_FOUND",
                                "detail": str(e)
                            })
                        }
                    except AttributeError:
                        return {
                            "statusCode": 500,
                            "headers": headers,
                            "body": json.dumps({
                                "success": False,
                                "message": "Documentation module does not have get_swagger_spec function",
                                "error_code": "INVALID_DOCS_MODULE"
                            })
                        }
                        
                except Exception as docs_err:
                    logger.error(f"Documentation error: {docs_err}", exc_info=True)
                    return {
                        "statusCode": 500,
                        "headers": headers,
                        "body": json.dumps({
                            "success": False,
                            "message": "Error retrieving documentation",
                            "error_code": "DOCS_ERROR",
                            "detail": str(docs_err)
                        })
                    }

            elif "/api/input-channel/" in path:
                # Public input channel access (no authorization required)
                # Used for QR code mobile input
                from GEPPPlatform.services.cores.users.input_channel_service import InputChannelService

                # Extract hash from path: /api/input-channel/{hash} or /api/input-channel/{hash}/submit or /api/input-channel/{hash}/preferences or /api/input-channel/{hash}/materials
                path_parts = path.split('/api/input-channel/')[1].split('/')
                hash_value = path_parts[0].split('?')[0]
                is_submit = len(path_parts) > 1 and path_parts[1] == 'submit'
                is_preferences = len(path_parts) > 1 and path_parts[1].startswith('preferences')
                is_materials = len(path_parts) > 1 and path_parts[1].startswith('materials')

                input_service = InputChannelService(session)

                if is_materials and http_method == 'GET':
                    # Get all materials for the material picker (with channel-based auth)
                    subuser = query_params.get('subuser', '')
                    materials_result = input_service.get_all_materials_for_picker(hash_value, subuser)
                    results = {
                        "success": materials_result.get('success', False),
                        "data": {
                            "materials": materials_result.get('materials', []),
                            "categories": materials_result.get('categories', []),
                            "main_materials": materials_result.get('main_materials', [])
                        }
                    }
                elif is_preferences:
                    # Handle preferences GET/POST
                    subuser = query_params.get('subuser') or body.get('subuser', '')
                    if http_method == 'GET':
                        # Get subuser preferences
                        prefs = input_service.get_subuser_preferences(hash_value, subuser)
                        results = {
                            "success": True,
                            "data": prefs
                        }
                    elif http_method == 'POST':
                        # Save subuser preferences
                        material_ids = body.get('material_ids', [])
                        save_result = input_service.save_subuser_preferences(hash_value, subuser, material_ids)
                        results = {
                            "success": save_result.get('success', False),
                            "data": save_result
                        }
                        if not save_result.get('success'):
                            return {
                                "statusCode": 400,
                                "headers": headers,
                                "body": json.dumps({
                                    'success': False,
                                    'message': save_result.get('message', 'Failed to save preferences')
                                })
                            }
                    else:
                        return {
                            "statusCode": 405,
                            "headers": headers,
                            "body": json.dumps({'success': False, 'message': 'Method not allowed'})
                        }
                elif is_submit and http_method == 'POST':
                    # Handle transaction submission from QR input
                    submit_result = input_service.submit_transaction_by_hash(hash_value, body)
                    if submit_result.get('status') == 'success':
                        results = {
                            "success": True,
                            "data": submit_result
                        }
                    else:
                        return {
                            "statusCode": 400,
                            "headers": headers,
                            "body": json.dumps({
                                'success': False,
                                'message': submit_result.get('message', 'Submission failed'),
                                'data': submit_result
                            })
                        }
                else:
                    # Get channel data
                    subuser = query_params.get('subuser')
                    display_name = query_params.get('display_name')
                    channel_data = input_service.get_input_channel_by_hash(hash_value, subuser, display_name)

                    if channel_data:
                        results = {
                            "success": True,
                            "data": channel_data
                        }
                    else:
                        return {
                            "statusCode": 404,
                            "headers": headers,
                            "body": json.dumps({'success': False, 'message': 'Input channel not found'})
                        }

            # Check for channel-based authentication for materials endpoints (QR mobile input)
            elif path.startswith('/api/materials') and http_method == 'GET':
                # Allow materials access with channel_hash + subuser authentication
                channel_hash = query_params.get('channel_hash')
                subuser = query_params.get('subuser')

                if channel_hash and subuser:
                    # Validate channel and subuser
                    from GEPPPlatform.services.cores.users.input_channel_service import InputChannelService
                    input_service = InputChannelService(session)
                    channel_data = input_service.get_input_channel_by_hash(channel_hash, subuser)

                    if channel_data and channel_data.get('subUser', {}).get('isValid'):
                        # Valid channel access - serve materials data without token
                        from GEPPPlatform.services.cores.materials.materials_handlers import handle_materials_routes
                        materials_result = handle_materials_routes(
                            event,
                            db_session=session,
                            method=http_method,
                            query_params=query_params,
                            path_params={},
                            headers=event.get('headers', {}),
                            current_user={'channel_auth': True, 'organization_id': channel_data.get('organization_id')}
                        )
                        results = {
                            "success": True,
                            "data": materials_result
                        }
                    else:
                        return {
                            "statusCode": 401,
                            "headers": headers,
                            "body": json.dumps({'success': False, 'message': 'Invalid channel or subuser'})
                        }
                else:
                    # No channel auth provided, fall through to regular token auth
                    auth_header = event.get('headers', {}).get('Authorization', '') or event.get('headers', {}).get('authorization', '')
                    if not auth_header.startswith('Bearer '):
                        return {
                            "statusCode": 401,
                            "headers": headers,
                            "body": json.dumps({'success': False, 'message': 'Missing or invalid authorization header'})
                        }
                    token = auth_header[7:]
                    auth_handler = AuthHandlers(session)
                    token_data = auth_handler.verify_jwt_token(token, path)
                    if token_data is None:
                        return {
                            "statusCode": 401,
                            "headers": headers,
                            "body": json.dumps({'success': False, 'message': 'Invalid token or insufficient permissions'})
                        }
                    # Handle materials routes with token auth
                    from GEPPPlatform.services.cores.materials.materials_handlers import handle_materials_routes
                    current_user = {
                        'user_id': token_data['user_id'],
                        'organization_id': token_data.get('organization_id'),
                        'email': token_data.get('email'),
                        'token_data': token_data
                    }
                    materials_result = handle_materials_routes(
                        event,
                        db_session=session,
                        method=http_method,
                        query_params=query_params,
                        path_params={},
                        headers=event.get('headers', {}),
                        current_user=current_user
                    )
                    results = {
                        "success": True,
                        "data": materials_result
                    }

            else:
                # All other routes require authorization
                auth_header = event.get('headers', {}).get('Authorization', '') or event.get('headers', {}).get('authorization', '')

                if not auth_header.startswith('Bearer '):
                    return {
                        "statusCode": 401,
                        "headers": headers,
                        "body": json.dumps({'success': False, 'message': 'Missing or invalid authorization header'})
                    }

                token = auth_header[7:]  # Remove 'Bearer ' prefix
                # Create AuthHandlers instance for token verification
                auth_handler = AuthHandlers(session)
                
                # Add logging for custom API paths
                if "/api/userapi/" in path:
                    logger.info(f"[CUSTOM_API_AUTH] Verifying token for path: {path}")
                    logger.info(f"[CUSTOM_API_AUTH] Token (first 20 chars): {token[:20]}...")
                
                token_data = auth_handler.verify_jwt_token(token, path)

                if token_data is None:
                    if "/api/userapi/" in path:
                        logger.error(f"[CUSTOM_API_AUTH] Token verification FAILED for path: {path}")
                    return {
                        "statusCode": 401,
                        "headers": headers,
                        "body": json.dumps({'success': False, 'message': 'Invalid token or insufficient permissions'})
                    }
                
                if "/api/userapi/" in path:
                    logger.info(f"[CUSTOM_API_AUTH] Token verification SUCCESS - token_data: {token_data}")
                if '/api/iot-devices' in path:
                    current_device = {
                        'device_id': token_data['device_id'],
                        'token_data': token_data  # Include full token data for future use
                    }
                    commonParams['current_device'] = current_device
                    # Optionally also decode a user token provided in the request body
                    try:
                        if isinstance(body, dict):
                            user_token = body.get('user_token') or body.get('userToken') or body.get('token')
                        else:
                            user_token = None
                    except Exception:
                        user_token = None

                    if user_token:
                        user_token_data = auth_handler.verify_jwt_token(user_token, path)
                        if user_token_data and user_token_data.get('user_id'):
                            current_user = {
                                'user_id': user_token_data['user_id'],
                                'organization_id': user_token_data.get('organization_id'),
                                'email': user_token_data.get('email'),
                                'token_data': user_token_data
                            }
                            commonParams['current_user'] = current_user
                else:
                # Extract full user info from JWT token and add to commonParams
                    current_user = {
                        'user_id': token_data['user_id'],
                        'organization_id': token_data.get('organization_id'),
                        'email': token_data.get('email'),
                        'token_data': token_data  # Include full token data for future use
                    }
                    commonParams['current_user'] = current_user

                # Route to appropriate handler (all handlers can assume user is authenticated)
                try:
                    if "/api/iot-devices" in path:
                        # Handle all IoT devices management routes
                        from GEPPPlatform.services.cores.iot_devices.iot_devices_handlers import handle_iot_devices_routes

                        iot_devices_result = handle_iot_devices_routes(event, data=body, **commonParams)
                        results = {
                            "success": True,
                            "data": iot_devices_result
                        }
                    elif "/api/users" in path or "/api/locations" in path or "/api/input-channels" in path:
                        # Handle all user management routes (including organization-level input channels)
                        from GEPPPlatform.services.cores.users.user_handlers import handle_user_routes

                        user_result = handle_user_routes(event, data=body, **commonParams)
                        results = {
                            "success": True,
                            "data": user_result
                        }

                    elif "/api/organizations" in path:
                        # Handle all organization management routes
                        from .services.cores.organizations.organization_handlers import organization_routes

                        org_result = organization_routes(event, context, **commonParams)
                        results = {
                            "success": True,
                            "data": org_result
                        }

                    elif "/api/materials" in path:
                        # Handle all materials management routes
                        from .services.cores.materials.materials_handlers import handle_materials_routes

                        materials_result = handle_materials_routes(event, **commonParams)
                        results = {
                            "success": True,
                            "data": materials_result
                        }

                    elif "/api/reports" in path:
                        # Handle all materials management routes
                        from .services.cores.reports.reports_handlers import handle_reports_routes

                        reports_result = handle_reports_routes(event, **commonParams)
                        # If handler returned an API Gateway proxy response (e.g., raw PDF),
                        # pass it through directly without wrapping.
                        if isinstance(reports_result, dict) and \
                           "statusCode" in reports_result and \
                           "headers" in reports_result and \
                           "body" in reports_result:
                            results = reports_result
                        else:
                            results = {
                                "success": True,
                                "data": reports_result
                            }
                    elif "/api/gri" in path:
                        # Handle all GRI routes
                        from .services.cores.gri.gri_handlers import handle_gri_routes

                        gri_result = handle_gri_routes(event, **commonParams)
                        results = {
                            "success": True,
                            "data": gri_result
                        }
                        
                    elif "/api/transactions" in path:
                        # Handle all transaction management routes
                        from .services.cores.transactions.transaction_handlers import handle_transaction_routes

                        transaction_result = handle_transaction_routes(event, data=body, **commonParams)
                        # Transaction handlers return complete response structure, don't double-wrap
                        results = {
                            "success": True,
                            "data": transaction_result
                        }

                    elif "/api/transaction_audit" in path:
                        # Handle all transaction audit routes
                        from .services.cores.transaction_audit.transaction_audit_handlers import handle_transaction_audit_routes

                        audit_result = handle_transaction_audit_routes(event, data=body, **commonParams)
                        results = {
                            "success": True,
                            "data": audit_result
                        }

                    elif "/api/audit" in path:
                        if "/api/audit/manual" in path:
                            # Handle all manual audit routes
                            from .services.cores.transaction_audit.manual_audit_handlers import handle_manual_audit_routes

                            manual_audit_result = handle_manual_audit_routes(event, data=body, **commonParams)
                            results = {
                                "success": True,
                                "data": manual_audit_result
                            }
                        else:
                            # Handle all audit rules management routes
                            from .services.cores.audit_rules.audit_rules_handlers import handle_audit_rules_routes

                            rules_result = handle_audit_rules_routes(event, data=body, **commonParams)
                            results = {
                                "success": True,
                                "data": rules_result
                            }

                    elif "/api/debug" in path:
                        # Handle all debug routes (development only)
                        from .services.debug.debug_handlers import handle_debug_routes

                        debug_result = handle_debug_routes(event, data=body, **commonParams)
                        results = {
                            "success": True,
                            "data": debug_result
                        }

                    elif "/api/integration" in path:
                        # Handle all integration routes
                        if "/api/integration/bma" in path:
                            # Handle BMA integration routes
                            from .services.integrations.bma.bma_handlers import handle_bma_routes

                            bma_result = handle_bma_routes(event, data=body, **commonParams)
                            results = {
                                "success": True,
                                "data": bma_result
                            }
                        else:
                            # Handle other integration routes here
                            available_integration_routes = ["/api/integration/bma/*"]
                            return {
                                "statusCode": 404,
                                "headers": headers,
                                "body": json.dumps({
                                    "success": False,
                                    "message": "Integration route not found",
                                    "error_code": "ROUTE_NOT_FOUND",
                                    "path": path,
                                    "method": http_method,
                                    "available_integration_routes": available_integration_routes
                                })
                            }

                    elif "/api/userapi/" in path:
                        # Handle custom API routes: /api/userapi/{api_path}/{service_path}/...
                        from .services.custom.custom_api_service import CustomApiService
                        from .services.custom import execute_custom_function
                        
                        try:
                            # Extract api_path and service_path from URL
                            # Pattern: /api/userapi/{api_path}/{service_path}/...
                            parts = path.split('/api/userapi/')[1].split('/')
                            if len(parts) < 2:
                                return {
                                    "statusCode": 400,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": "Invalid custom API path. Expected: /api/userapi/{api_path}/{service_path}/...",
                                        "error_code": "INVALID_PATH"
                                    })
                                }
                            
                            api_path = parts[0]
                            # Extract service_path and remaining_path
                            # We need to find where the service_path ends by checking against database
                            # Try progressively longer paths: "ai_audit", "ai_audit/v1", "ai_audit/v1/test", etc.
                            remaining_parts = parts[1:]
                            
                            logger.info(f"[CUSTOM_API] Parsing URL - api_path={api_path}, remaining_parts={remaining_parts}")
                            
                            # Initialize service
                            custom_api_service = CustomApiService(session)
                            
                            # Try to find the service by progressively building the service_path
                            # Start with just the first segment, then first+second, etc.
                            service_path = None
                            remaining_path = ""
                            custom_api = None
                            
                            for i in range(len(remaining_parts), 0, -1):
                                potential_service_path = '/'.join(remaining_parts[:i]).split('?')[0]
                                logger.info(f"[CUSTOM_API] Trying service_path: {potential_service_path}")
                                
                                # Try to find this service_path in the database
                                potential_api = custom_api_service.get_custom_api_by_service_path(potential_service_path)
                                if potential_api:
                                    service_path = potential_service_path
                                    remaining_path = '/'.join(remaining_parts[i:]) if i < len(remaining_parts) else ""
                                    custom_api = potential_api
                                    logger.info(f"[CUSTOM_API] Found service: {service_path}, remaining: {remaining_path}")
                                    break
                            
                            if not service_path or not custom_api:
                                # No matching service found
                                attempted_paths = ['/'.join(remaining_parts[:i]).split('?')[0] for i in range(1, len(remaining_parts) + 1)]
                                return {
                                    "statusCode": 404,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": "API service not found",
                                        "error_code": "API_NOT_FOUND",
                                        "debug_info": {
                                            "api_path": api_path,
                                            "attempted_service_paths": attempted_paths
                                        }
                                    })
                                }
                            
                            # Get the organization for this api_path
                            organization = custom_api_service.get_organization_by_api_path(api_path)
                            if not organization:
                                return {
                                    "statusCode": 404,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": f"Organization not found for api_path: {api_path}",
                                        "error_code": "ORG_NOT_FOUND",
                                        "debug_info": {
                                            "api_path": api_path,
                                            "service_path": service_path
                                        }
                                    })
                                }
                            
                            # Get organization API access
                            org_api = custom_api_service.get_organization_api_access(organization.id, custom_api.id)
                            if not org_api:
                                return {
                                    "statusCode": 403,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": "Organization does not have access to this API",
                                        "error_code": "API_ACCESS_DENIED",
                                        "debug_info": {
                                            "api_path": api_path,
                                            "service_path": service_path,
                                            "organization_id": organization.id,
                                            "organization_name": organization.name
                                        }
                                    })
                                }
                            
                            # Validate access (enabled, not expired, has quota)
                            try:
                                # Check if enabled
                                if not org_api.enable:
                                    raise APIException(
                                        status_code=403,
                                        message="API access is disabled for this organization",
                                        error_code="API_DISABLED"
                                    )
                                
                                # Check expiration
                                from datetime import datetime, timezone
                                if org_api.expired_date and org_api.expired_date < datetime.now(timezone.utc):
                                    raise APIException(
                                        status_code=403,
                                        message="API access has expired",
                                        error_code="API_EXPIRED"
                                    )
                                
                                # Check API call quota
                                if not org_api.has_api_quota():
                                    raise APIException(
                                        status_code=429,
                                        message="API call quota exceeded",
                                        error_code="QUOTA_EXCEEDED"
                                    )
                                    
                                logger.info(f"[CUSTOM_API] Access validated - org_id={organization.id}, api={custom_api.name}")
                                
                            except APIException:
                                raise  # Re-raise API exceptions as-is
                            
                            logger.info(f"[CUSTOM_API] JWT current_user: {current_user}")
                            # This prevents users from accessing other organizations' APIs even with valid tokens
                            token_org_id = current_user.get('organization_id')
                            logger.info(f"[CUSTOM_API] Org match check - token_org_id={token_org_id}, api_org_id={organization.id}")
                            
                            if not token_org_id:
                                logger.warning(f"[CUSTOM_API] Missing organization_id in JWT token")
                                return {
                                    "statusCode": 403,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": "JWT token does not contain organization_id claim",
                                        "error_code": "MISSING_ORG_CLAIM",
                                        "debug_info": {
                                            "api_path": api_path,
                                            "service_path": service_path,
                                            "jwt_claims": list(current_user.keys()) if current_user else []
                                        }
                                    })
                                }
                            
                            if token_org_id != organization.id:
                                logger.warning(f"[CUSTOM_API] Organization mismatch: JWT token org_id={token_org_id}, api_path org_id={organization.id}")
                                return {
                                    "statusCode": 403,
                                    "headers": headers,
                                    "body": json.dumps({
                                        "success": False,
                                        "message": "Access denied. Your organization does not match this API path.",
                                        "error_code": "ORG_MISMATCH",
                                        "debug_info": {
                                            "api_path": api_path,
                                            "service_path": service_path,
                                            "jwt_organization_id": token_org_id,
                                            "api_organization_id": organization.id,
                                            "api_organization_name": organization.name
                                        }
                                    })
                                }
                            
                            logger.info(f"[CUSTOM_API] Organization match successful - proceeding to execute function")
                            
                            # Execute the custom function
                            result = execute_custom_function(
                                root_fn_name=custom_api.root_fn_name,
                                db_session=session,
                                organization_id=organization.id,
                                method=http_method,
                                path=remaining_path,
                                query_params=query_params,
                                body=body,
                                headers=event.get("headers", {})
                            )
                            
                            # Record API usage (increment counters)
                            process_units = result.get('process_units', 0)  # Functions can report units consumed
                            custom_api_service.record_api_call(org_api, process_units)
                            
                            # Return result
                            results = {
                                "success": True,
                                "data": result,
                                "quota": custom_api_service.get_quota_status(org_api)
                            }
                            
                        except APIException as api_err:
                            # Custom API validation errors (already have proper status codes)
                            error_detail = {
                                "success": False,
                                "message": api_err.message,
                                "error_code": api_err.error_code,
                                "debug_info": {
                                    "api_path": api_path,
                                    "service_path": service_path,
                                    "status_code": api_err.status_code
                                }
                            }
                            logger.error(f"[CUSTOM_API] APIException: {api_err.error_code} - {api_err.message}")
                            return {
                                "statusCode": api_err.status_code,
                                "headers": headers,
                                "body": json.dumps(error_detail)
                            }
                        except ValueError as val_err:
                            # Function not found in registry
                            error_detail = {
                                "success": False,
                                "message": str(val_err),
                                "error_code": "FUNCTION_NOT_FOUND",
                                "debug_info": {
                                    "api_path": api_path,
                                    "service_path": service_path,
                                    "function_registry_name": custom_api.root_fn_name if 'custom_api' in locals() else None
                                }
                            }
                            logger.error(f"[CUSTOM_API] Function not found: {val_err}")
                            return {
                                "statusCode": 404,
                                "headers": headers,
                                "body": json.dumps(error_detail)
                            }
                        except Exception as custom_err:
                            logger.error(f"[CUSTOM_API] Unexpected error: {custom_err}", exc_info=True)
                            error_detail = {
                                "success": False,
                                "message": "Internal error processing custom API request",
                                "error_code": "CUSTOM_API_ERROR",
                                "error_type": type(custom_err).__name__,
                                "detail": str(custom_err),
                                "debug_info": {
                                    "api_path": api_path if 'api_path' in locals() else None,
                                    "service_path": service_path if 'service_path' in locals() else None
                                }
                            }
                            return {
                                "statusCode": 500,
                                "headers": headers,
                                "body": json.dumps(error_detail)
                            }



                    else:
                        # Handle other future modules here
                        available_routes = ["/api/auth/*", "/api/users/*", "/api/organizations/*", "/api/materials/*", "/api/locations/*", "/api/reports/*", "/api/transactions/*", "/api/transaction_audit/*", "/api/audit/*", "/api/debug/*", "/api/integration/*", "/api/userapi/{api_path}/{service_path}/*", "/health"]
                        return {
                            "statusCode": 404,
                            "headers": headers,
                            "body": json.dumps({
                                "success": False,
                                "message": "Route not found",
                                "error_code": "ROUTE_NOT_FOUND",
                                "path": path,
                                "method": http_method,
                                "available_routes": available_routes
                            })
                        }

                except APIException as api_error:
                    # Handle custom API exceptions with proper status codes
                    return {
                        "statusCode": api_error.status_code,
                        "headers": headers,
                        "body": json.dumps({
                            "success": False,
                            "message": api_error.message,
                            "error_code": api_error.error_code,
                            "errors": getattr(api_error, 'errors', None)
                        })
                    }

                except Exception as service_error:
                    # Handle unexpected service errors
                    import traceback
                    return {
                        "statusCode": 500,
                        "headers": headers,
                        "body": json.dumps({
                            "success": False,
                            "message": "Internal server error in service layer",
                            "error_code": "SERVICE_ERROR",
                            "stack_trace": traceback.format_exc()
                        })
                    }

        # If a handler already returned a full proxy response (e.g., PDF binary),
        # pass it through unmodified. Otherwise, wrap as JSON.
        if isinstance(results, dict) and "statusCode" in results and "body" in results:
            return results
        else:
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps(results),
            }
        
    except UnauthorizedException as auth_error:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({
                "error": "Unauthorized",
                "message": str(auth_error)
            })
        }
        
    except Exception as e:
        import traceback
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({
                "error": "Internal server error",
                "message": str(e),
                "stack_trace": traceback.format_exc()
            })
        }
