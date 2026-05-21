"""Lambda entry point for CRM profile refresh jobs."""

from typing import Any, Dict

from GEPPPlatform.services.admin.crm.profile_refresher_lambda import (
    lambda_handler as _lambda_handler,
)


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Delegate CRM profile refresh invocations to the service wrapper."""
    return _lambda_handler(event, context)

