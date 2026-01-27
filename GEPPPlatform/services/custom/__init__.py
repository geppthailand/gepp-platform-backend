"""
Custom API Service Layer

This module provides the function registry and execution engine for custom APIs.
Functions are imported from the functions/ subdirectory and registered by their root_fn_name.
"""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

# Import function modules
from .functions.ai_audit_v1 import main as ai_audit_v1_module

# Function Registry: Maps root_fn_name to module
FUNCTION_REGISTRY: Dict[str, Any] = {
    'ai_audit_v1': ai_audit_v1_module,
}


def get_available_functions() -> list:
    """Return list of available function names"""
    return list(FUNCTION_REGISTRY.keys())


def execute_custom_function(
    root_fn_name: str,
    db_session: Session,
    organization_id: int,
    method: str,
    path: str,
    query_params: Dict[str, Any],
    body: Dict[str, Any],
    headers: Dict[str, str],
    **kwargs
) -> Dict[str, Any]:
    """
    Execute a custom function by its registered name.
    
    Args:
        root_fn_name: The function identifier (must match entry in FUNCTION_REGISTRY)
        db_session: SQLAlchemy database session
        organization_id: The ID of the organization making the request
        method: HTTP method (GET, POST, etc.)
        path: Remaining path after service_path
        query_params: URL query parameters
        body: Request body (parsed JSON)
        headers: Request headers
        **kwargs: Additional parameters
    
    Returns:
        Dict containing the function result
    
    Raises:
        ValueError: If function is not found in registry
    """
    if root_fn_name not in FUNCTION_REGISTRY:
        raise ValueError(f"Function '{root_fn_name}' not found in registry. Available: {get_available_functions()}")
    
    module = FUNCTION_REGISTRY[root_fn_name]
    
    return module.execute(
        db_session=db_session,
        organization_id=organization_id,
        method=method,
        path=path,
        query_params=query_params,
        body=body,
        headers=headers,
        **kwargs
    )
