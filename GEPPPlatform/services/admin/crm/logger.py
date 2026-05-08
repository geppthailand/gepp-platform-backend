"""
CRM structured logger — emit JSON log lines that CloudWatch Insights can query.

Usage::

    from .logger import crm_log

    # per-request: generate once, pass down
    cid = crm_log.new_correlation_id()

    crm_log("delivery.start",  campaign_id=42, user_location_id=7,  correlation_id=cid)
    crm_log("delivery.sent",   mandrill_id="abc", latency_ms=210,    correlation_id=cid)
    crm_log("delivery.failed", error_message="timeout",              correlation_id=cid)

    crm_log("webhook.received",  signature_valid=True, event_count=3, correlation_id=cid)
    crm_log("webhook.processed", mandrill_event="open", msg_id="x",
            delivery_id=1, correlation_id=cid)

    crm_log("scheduler.tick.start", campaigns_to_process=5, correlation_id=cid)
    crm_log("scheduler.tick.done",  deliveries_enqueued=3, latency_ms=120, correlation_id=cid)

All fields are written to a single JSON object so Insights can do:
    fields @timestamp, event, campaign_id, latency_ms
    | filter event like /delivery/
    | stats avg(latency_ms) by campaign_id
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

_logger = logging.getLogger("crm.structured")


def new_correlation_id() -> str:
    """Generate a short (8-char) UUID4 hex for log correlation."""
    return uuid.uuid4().hex[:8]


def crm_log(event: str, **kwargs: Any) -> None:
    """
    Emit one JSON line via the 'crm.structured' logger at INFO level.

    Always includes:
      - event         (positional first arg)
      - ts            (ISO-8601 UTC)
      - correlation_id (from kwargs, or auto-generated if absent)

    All extra kwargs are merged into the top-level JSON object.
    """
    record: dict = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "correlation_id": kwargs.pop("correlation_id", new_correlation_id()),
    }
    record.update(kwargs)
    # Serialize safely — stringify anything non-primitive
    try:
        _logger.info(json.dumps(record, default=str))
    except Exception:
        # Never let structured logging break the caller
        _logger.info(json.dumps({"event": event, "error": "serialization_failed"}, default=str))
