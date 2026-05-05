"""
CRM Profile Refresher — Lambda entry point.

Invoked nightly by AWS EventBridge:
    cron(0 19 * * ? *)   →   02:00 Asia/Bangkok (UTC+7)

Function exported: lambda_handler(event, context)

Local smoke test:
    python -c "
    from GEPPPlatform.services.admin.crm.profile_refresher_lambda import lambda_handler
    print(lambda_handler.__doc__ or 'imported OK')
    "
"""
import json
import logging

from GEPPPlatform.database import get_session
from .profile_refresher import run_full_refresh

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """
    Nightly CRM profile refresh Lambda.

    Rebuilds crm_user_profiles and crm_org_profiles from crm_events using
    a bulk set-based UPSERT (idempotent — safe to re-run if retried).

    Returns:
        {"statusCode": 200, "body": {"user_profiles": {...}, "org_profiles": {...}}}
    """
    logger.info("CRM profile refresh Lambda invoked. event=%s", event)

    with get_session() as session:
        summary = run_full_refresh(session)

    logger.info("CRM profile refresh complete: %s", summary)
    return {"statusCode": 200, "body": json.dumps(summary)}
