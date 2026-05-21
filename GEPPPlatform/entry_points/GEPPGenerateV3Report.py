"""Lambda entry point for PDF export hub jobs."""

from typing import Any, Dict

from GEPPPlatform.services.cores.pdf_export_hub import lambda_handler as _lambda_handler


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Delegate PDF export Lambda invocations to the service hub."""
    return _lambda_handler(event, context)

