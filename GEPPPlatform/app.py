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
from GEPPPlatform.exceptions import APIException
from GEPPPlatform.database import get_session

import random
import string

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
            
            elif "/api/auth/iot-devices" in path:
                # Handle all iot devices auth routes through iot devices module (no authorization required)
                iot_devices_result = handle_auth_routes(path, data=body, **commonParams)
                results = {
                    "success": True,
                    "data": iot_devices_result
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
                token_data = auth_handler.verify_jwt_token(token, path)
                print(token_data)

                if token_data is None:
                    return {
                        "statusCode": 401,
                        "headers": headers,
                        "body": json.dumps({'success': False, 'message': 'Invalid token or insufficient permissions'})
                    }

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
                    if "/api/users" in path or "/api/locations" in path:
                        # Handle all user management routes
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
                        results = {
                            "success": True,
                            "data": reports_result
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

                    else:
                        # Handle other future modules here
                        available_routes = ["/api/auth/*", "/api/users/*", "/api/organizations/*", "/api/materials/*", "/api/reports/*", "/api/transactions/*", "/api/transaction_audit/*", "/api/audit/*", "/api/debug/*", "/api/integration/*", "/health"]
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

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps(results),
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
