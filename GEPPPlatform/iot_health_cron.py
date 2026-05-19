"""IoT health-snapshot cron — feeds the Fleet online% chart.

Wire this as a Lambda function fired by an EventBridge rule every 5 min:

    Function:    {ENV}-GEPPPlatform-IOTHEALTHCRON
    Schedule:    rate(5 minutes)   (or  cron(*/5 * * * ? *))
    Handler:     GEPPPlatform.iot_health_cron.cron_iot_health_snapshot
    Memory:      256 MB     (light DB-only workload)
    Timeout:     30 s

The body is intentionally tiny — all it does is call
`AdminService.aggregate_health_snapshot()` which idempotently writes one
5-min bucket row per active device. See `update_iot_health_cron.sh` for
the deploy command and `admin_service.py:aggregate_health_snapshot` for
the actual SQL.
"""
import json
import logging


def cron_iot_health_snapshot(event, context):
    """EventBridge cron entrypoint. Returns the aggregator's stats dict."""
    logger = logging.getLogger(__name__)
    logger.info("Starting cron_iot_health_snapshot")

    try:
        from GEPPPlatform.services.admin.admin_service import AdminService
        from GEPPPlatform.database import get_session

        with get_session() as session:
            svc = AdminService(session)
            result = svc.aggregate_health_snapshot()
        logger.info(
            f"cron_iot_health_snapshot done: {json.dumps(result, default=str)}"
        )
        return {'success': True, **result}
    except Exception as e:
        logger.exception("cron_iot_health_snapshot failed")
        return {'success': False, 'error': str(e)}
