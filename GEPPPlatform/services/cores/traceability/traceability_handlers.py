"""
Traceability API handlers
"""

from typing import Dict, Any

from ....exceptions import APIException
from .traceability_service import TraceabilityService


def handle_traceability_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for traceability routes.
    """
    path = event.get("rawPath", "")
    method = params.get("method", "GET")
    query_params = params.get("query_params", {})
    path_params = params.get("path_params", {})

    db_session = params.get("db_session")
    if not db_session:
        raise APIException("Database session not provided")

    current_user = params.get("current_user", {})
    current_user_id = current_user.get("user_id")
    current_user_organization_id = current_user.get("organization_id")

    traceability_service = TraceabilityService(db_session)

    if path == "/api/traceability/confirm-arrival" and method == "POST":
        body = data or {}
        transaction_id = body.get("transaction_id")
        if transaction_id is None:
            raise APIException("Missing required field: transaction_id", status_code=400)
        result = traceability_service.confirm_arrival(
            transaction_id=int(transaction_id),
            organization_id=current_user_organization_id,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to confirm arrival"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability/go-back" and method == "POST":
        body = data or {}
        transaction_id = body.get("transaction_id")
        if transaction_id is None:
            raise APIException("Missing required field: transaction_id", status_code=400)
        result = traceability_service.go_back_one_step(
            transaction_id=int(transaction_id),
            organization_id=current_user_organization_id,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to go back"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability/destinations" and method == "GET":
        result = traceability_service.get_destination_locations(organization_id=current_user_organization_id)
        return {"message": "Destination locations (for input options)", "data": result}

    if path == "/api/traceability" and method == "POST":
        # Body: record_id, weight, origin_id, vehicle_info, messenger_info, destination_id
        body = data or {}
        record_id = body.get("record_id")
        weight = body.get("weight")
        origin_id = body.get("origin_id")
        vehicle_info = body.get("vehicle_info")
        messenger_info = body.get("messenger_info")
        destination_id = body.get("destination_id")
        if record_id is None or weight is None or origin_id is None or destination_id is None:
            raise APIException(
                "Missing required fields: record_id, weight, origin_id, destination_id",
                status_code=400,
            )
        result = traceability_service.create_transport_transaction(
            record_id=int(record_id),
            weight=float(weight),
            origin_id=int(origin_id),
            destination_id=int(destination_id),
            vehicle_info=vehicle_info,
            messenger_info=messenger_info,
            created_by_id=current_user_id,
            organization_id=current_user_organization_id,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to create transport transaction"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability" and method == "GET":
        result = traceability_service.get_traceability(organization_id=current_user_organization_id, **query_params)
        return {"message": "Traceability API", "data": result}

    raise APIException(f"Not found: {method} {path}", status_code=404)
