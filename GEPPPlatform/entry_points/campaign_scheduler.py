"""Lambda entry point for CRM campaign scheduling."""

from typing import Any, Dict

from GEPPPlatform.services.admin.crm.campaign_scheduler_lambda import (
    lambda_handler as _lambda_handler,
)


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Delegate CRM campaign scheduler invocations to the service wrapper."""
    return _lambda_handler(event, context)

