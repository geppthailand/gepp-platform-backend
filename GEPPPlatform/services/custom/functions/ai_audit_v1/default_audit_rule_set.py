"""
Default Audit Rule Set
Returns mock audit data for organizations without a specific rule set.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def execute(
    db_session: Session,
    organization_id: int,
    transaction_ids: List[int],
    body: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    Default audit rule set – returns mock/placeholder audit results.

    Args:
        db_session: Database session
        organization_id: Organization ID
        transaction_ids: List of transaction IDs to audit
        body: Original request body
        **kwargs: Additional context

    Returns:
        Mock audit results
    """
    logger.info(f"[DEFAULT_AUDIT] Running default audit rule set for org={organization_id}, txns={transaction_ids}")

    results = []
    for txn_id in transaction_ids:
        results.append({
            "transaction_id": txn_id,
            "audit_status": "no_action",
            "confidence_score": 0.0,
            "message": "Default rule set – no audit logic configured. Please assign a specific rule set to your organization.",
            "audits": [],
            "violations": []
        })

    return {
        "success": True,
        "rule_set": "default_audit_rule_set",
        "organization_id": organization_id,
        "total_transactions": len(transaction_ids),
        "results": results
    }
