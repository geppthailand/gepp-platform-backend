"""
Event Dashboard V1 Custom API Function

Provides event dashboard endpoints for waste statistics and org structure extraction.

GET /overall-waste-data  – Waste stats with recycling rate, GHG, material breakdown, timeseries, tenant split
GET /structure-of        – Extract sub-tree from organization setup
GET /swagger             – OpenAPI 3.0 specification
"""

import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def execute(
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
    Execute Event Dashboard V1 API operations.

    Supported endpoints:
    - GET /overall-waste-data  - Waste statistics
    - GET /structure-of        - Organization structure sub-tree
    - GET /swagger             - API documentation
    """
    path = path.strip('/') if path else ''

    logger.info(f"Event Dashboard V1 API called: method={method}, path={path}, org_id={organization_id}")

    if method == 'GET':
        if path == 'overall-waste-data':
            from .overall_waste_data import handle_overall_waste_data
            return handle_overall_waste_data(db_session, organization_id, query_params)

        elif path == 'structure-of':
            from .structure_of import handle_structure_of
            return handle_structure_of(db_session, organization_id, query_params)

        elif path == 'swagger':
            from .swagger import get_swagger_spec
            return get_swagger_spec()

        elif path == '' or path == 'status':
            return {
                "success": True,
                "service": "event_dashboard",
                "version": "v1",
                "organization_id": organization_id,
                "status": "operational",
                "endpoints": [
                    "GET /overall-waste-data",
                    "GET /structure-of",
                    "GET /swagger",
                ]
            }

    return {
        "success": False,
        "error": "ENDPOINT_NOT_FOUND",
        "message": f"Unknown endpoint: {method} /{path}",
        "available_endpoints": [
            "GET /overall-waste-data?user_location_id=&start_date=&end_date=&interval=",
            "GET /structure-of?user_location_id=",
            "GET /swagger"
        ]
    }
