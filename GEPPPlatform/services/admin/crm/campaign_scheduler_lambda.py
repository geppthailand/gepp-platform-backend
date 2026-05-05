"""
CRM Campaign Scheduler — Lambda entry point.

Invoked every minute by AWS EventBridge:
    rate(1 minute)

Function exported: lambda_handler(event, context)

Local smoke test:
    python3 -c "
    from GEPPPlatform.services.admin.crm.campaign_scheduler_lambda import lambda_handler
    print('ok')
    "

See docs/Services/GEPP-Backoffice/features/crm_campaign_scheduler_schedule.md
for the EventBridge rule definition.
"""

import json
import logging

from GEPPPlatform.database import get_session
from .campaign_scheduler import tick, retry_soft_bounces

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """
    CRM trigger-campaign scheduler Lambda.

    Evaluates all running trigger campaigns for new matching crm_events
    and fans out deliveries via delivery_sender.enqueue_delivery.

    Runs every minute (EventBridge rate rule). Each invocation processes
    up to 50 campaigns × 500 events = 25 000 potential deliveries.

    Returns:
        {"statusCode": 200, "body": <summary_json>}
    """
    logger.info("CRM campaign scheduler Lambda invoked. event=%s", event)

    tick_summary = {}
    retry_summary = {}

    with get_session() as db:
        tick_summary = tick(db)

    logger.info("CRM campaign scheduler tick complete: %s", tick_summary)

    with get_session() as db:
        retry_summary = retry_soft_bounces(db)

    logger.info("CRM soft-bounce retry complete: %s", retry_summary)

    combined = {
        "tick": tick_summary,
        "retry_soft_bounces": retry_summary,
    }
    return {
        "statusCode": 200,
        "body": json.dumps(combined),
    }
