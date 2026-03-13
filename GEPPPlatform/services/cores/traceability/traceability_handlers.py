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

    db_session = params.get("db_session")
    if not db_session:
        raise APIException("Database session not provided")

    current_user = params.get("current_user", {})
    current_user_organization_id = current_user.get("organization_id")
    current_user_id = current_user.get("user_id")

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

    if path == "/api/traceability/revert" and method == "POST":
        body = data or {}
        transaction_id = body.get("transaction_id")
        if transaction_id is None:
            raise APIException("Missing required field: transaction_id", status_code=400)
        result = traceability_service.revert_transaction(
            transaction_id=int(transaction_id),
            organization_id=current_user_organization_id,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to revert transaction"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability/destinations" and method == "GET":
        result = traceability_service.get_destination_locations(organization_id=current_user_organization_id)
        return {"message": "Destination locations (for input options)", "data": result}

    if path == "/api/traceability/hierarchy" and method == "GET":
        result = traceability_service.get_traceability_hierarchy(organization_id=current_user_organization_id, current_user_id=current_user_id, **query_params)
        return {"message": "Traceability hierarchy (tree)", "data": result["data"]}

    if path == "/api/traceability" and method == "POST":
        # Body: either "transaction_group_id" (root) or "transport_transaction_id" (children of an arrived transport).
        # With transport_transaction_id: use it as parent_id for all new rows and same transaction_group_id as parent.
        body = data or {}
        data_list = body.get("data")
        transaction_group_id = body.get("transaction_group_id")
        transport_transaction_id = body.get("transport_transaction_id")
        if not isinstance(data_list, list) or len(data_list) == 0:
            raise APIException("Missing or empty required field: data (array of items with weight, origin_id)", status_code=400)
        if transaction_group_id is None and transport_transaction_id is None:
            raise APIException("Missing required field: transaction_group_id or transport_transaction_id", status_code=400)
        if transaction_group_id is not None and transport_transaction_id is not None:
            raise APIException("Provide either transaction_group_id or transport_transaction_id, not both", status_code=400)
        result = traceability_service.create_transport_transactions(
            data=data_list,
            transaction_group_id=int(transaction_group_id) if transaction_group_id is not None else None,
            organization_id=current_user_organization_id,
            transport_transaction_id=int(transport_transaction_id) if transport_transaction_id is not None else None,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to create transport transactions"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability/export/pdf" and method == "GET":
        from ..pdf_export_hub import generate_pdf_via_lambda
        summary_result = traceability_service.get_traceability(organization_id=current_user_organization_id, current_user_id=current_user_id, **query_params)
        hierarchy_result = traceability_service.get_traceability_hierarchy(organization_id=current_user_organization_id, current_user_id=current_user_id, **query_params)
        payload = {
            "hierarchy": hierarchy_result["data"],
            "summary": summary_result.get("summary"),
            "date_from": query_params.get("date_from"),
            "date_to": query_params.get("date_to"),
        }
        return generate_pdf_via_lambda(
            payload,
            export_type="traceability",
            default_filename_prefix="traceability_report",
        )

    if path == "/api/traceability" and method == "PUT":
        body = data or {}
        data_list = body.get("data")
        if not isinstance(data_list, list) or len(data_list) == 0:
            raise APIException("Missing or empty required field: data (array of items with transport_transaction_id)", status_code=400)
        result = traceability_service.update_transport_transactions(
            data=data_list,
            organization_id=current_user_organization_id,
        )
        if not result.get("success"):
            raise APIException(result.get("message", "Failed to update transport transactions"), status_code=400)
        return {"message": result["message"], "data": result}

    if path == "/api/traceability" and method == "GET":
        result = traceability_service.get_traceability(organization_id=current_user_organization_id, current_user_id=current_user_id, **query_params)
        return {
            "message": "Traceability API",
            "data": result["data"],
            "total_waste_weight": result["summary"]["total_waste_weight"],
            "total_disposal": result["summary"]["total_disposal"],
            "total_treatment": result["summary"]["total_treatment"],
            "total_managed_waste": result["summary"]["total_managed_waste"],
        }

    raise APIException(f"Not found: {method} {path}", status_code=404)
