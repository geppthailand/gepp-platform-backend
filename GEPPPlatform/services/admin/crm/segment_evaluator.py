"""
CRM Segment Evaluator — safe SQL compiler for rule-tree based segments.

Security guarantees:
  - Field names are whitelisted against ALLOWED_FIELDS.
  - Operators are whitelisted against ALLOWED_OPERATORS.
  - All values go through SQLAlchemy named bind-params (:p0, :p1, …).
  - Any violation raises BadRequestException — never executes partial SQL.

Public API:
    compile_rules(rule_tree, scope)            -> (where_clause, params)
    preview_segment(db, rule_tree, scope, org_id?) -> {count, sample}
    evaluate_segment(db, segment_id)            -> member_count
    get_field_registry()                        -> dict (API contract §2)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field registry — these are the ONLY columns that may be referenced in rules.
# Extend here when new profile columns are added via migrations.
# ---------------------------------------------------------------------------

ALLOWED_FIELDS: Dict[str, Set[str]] = {
    "user": {
        "days_since_last_login",
        "login_count_30d",
        "transaction_count_30d",
        "transaction_count_lifetime",
        "qr_count_30d",
        "reward_claim_count_30d",
        "iot_readings_count_30d",
        "gri_submission_count_30d",
        "traceability_count_30d",
        "engagement_score",
        "activity_tier",
        "onboarded",
        "subscription_plan_id",
        "organization_id",
        # Sprint 4 — email engagement fields (populated by profile_refresher)
        "emails_received_30d",
        "emails_opened_30d",
        "emails_clicked_30d",
        "last_email_received_at",
        "last_email_opened_at",
    },
    "organization": {
        "active_user_count_30d",
        "total_user_count",
        "active_user_ratio",
        "transaction_count_30d",
        "traceability_count_30d",
        "gri_submission_count_30d",
        "subscription_plan_id",
        "subscription_active",
        "quota_used_pct",
        "activity_tier",
        "organization_id",
        # Sprint 4 — org-level email engagement fields
        "org_emails_received_30d",
        "org_emails_opened_30d",
        "org_emails_clicked_30d",
        "org_last_email_opened_at",
    },
}

# These are the ONLY operators that may appear in rule conditions.
ALLOWED_OPERATORS: Set[str] = {
    "=", "!=", ">", "<", ">=", "<=",
    "IN", "NOT IN", "BETWEEN",
    # Sprint 4: nullable datetime fields (last_email_opened_at etc.)
    "IS NULL", "IS NOT NULL",
}

_SCOPE_TABLE = {
    "user":         "crm_user_profiles",
    "organization": "crm_org_profiles",
}

_SCOPE_PK = {
    "user":         "user_location_id",
    "organization": "organization_id",
}

# ---------------------------------------------------------------------------
# Field registry for the frontend rule builder (GET /crm-segments/fields)
# ---------------------------------------------------------------------------

_FIELD_DEFINITIONS: Dict[str, List[Dict[str, Any]]] = {
    "userFields": [
        {"name": "days_since_last_login",    "label": "Days since last login",       "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "login_count_30d",          "label": "Logins (30d)",                "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "transaction_count_30d",    "label": "Transactions (30d)",           "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "transaction_count_lifetime","label": "Transactions (lifetime)",     "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "qr_count_30d",             "label": "QR scans (30d)",              "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "reward_claim_count_30d",   "label": "Reward claims (30d)",         "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "iot_readings_count_30d",   "label": "IoT readings (30d)",          "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "gri_submission_count_30d", "label": "GRI submissions (30d)",       "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "traceability_count_30d",   "label": "Traceability actions (30d)",  "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "engagement_score",         "label": "Engagement score",            "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "activity_tier",            "label": "Activity tier",               "type": "enum",    "operators": ["=", "!=", "IN", "NOT IN"], "options": ["active", "at_risk", "dormant"]},
        {"name": "onboarded",                "label": "Onboarded",                   "type": "boolean", "operators": ["=", "!="]},
        {"name": "subscription_plan_id",     "label": "Subscription plan",           "type": "fk:subscription_plans", "operators": ["=", "!=", "IN", "NOT IN"]},
        {"name": "organization_id",          "label": "Organisation",                "type": "fk:organizations", "operators": ["=", "!=", "IN", "NOT IN"]},
        # Sprint 4 — email engagement fields
        {
            "name": "emails_received_30d",
            "label": "Emails received (30d)",
            "type": "number",
            "description": "Number of campaign emails sent to this user in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "emails_opened_30d",
            "label": "Emails opened (30d)",
            "type": "number",
            "description": "Number of campaign emails this user opened in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "emails_clicked_30d",
            "label": "Emails clicked (30d)",
            "type": "number",
            "description": "Number of campaign emails where this user clicked a link in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "last_email_received_at",
            "label": "Last email received at",
            "type": "datetime",
            "description": "Timestamp of the most recent campaign email sent to this user.",
            "operators": ["=", "!=", ">", "<", "IS NULL", "IS NOT NULL"],
        },
        {
            "name": "last_email_opened_at",
            "label": "Last email opened at",
            "type": "datetime",
            "description": "Timestamp of the most recent campaign email this user opened.",
            "operators": ["=", "!=", ">", "<", "IS NULL", "IS NOT NULL"],
        },
    ],
    "organizationFields": [
        {"name": "active_user_count_30d",    "label": "Active users (30d)",          "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "total_user_count",         "label": "Total users",                 "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "active_user_ratio",        "label": "Active user ratio",           "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "transaction_count_30d",    "label": "Transactions (30d)",          "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "traceability_count_30d",   "label": "Traceability actions (30d)", "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "gri_submission_count_30d", "label": "GRI submissions (30d)",      "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "subscription_plan_id",     "label": "Subscription plan",          "type": "fk:subscription_plans", "operators": ["=", "!=", "IN", "NOT IN"]},
        {"name": "subscription_active",      "label": "Subscription active",        "type": "boolean", "operators": ["=", "!="]},
        {"name": "quota_used_pct",           "label": "Quota used (%)",             "type": "number",  "operators": ["=", "!=", ">", "<", ">=", "<="]},
        {"name": "activity_tier",            "label": "Activity tier",              "type": "enum",    "operators": ["=", "!=", "IN", "NOT IN"], "options": ["active", "at_risk", "dormant"]},
        # Sprint 4 — org-level email engagement fields
        {
            "name": "org_emails_received_30d",
            "label": "Org emails received (30d)",
            "type": "number",
            "description": "Total campaign emails sent to this organisation's users in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "org_emails_opened_30d",
            "label": "Org emails opened (30d)",
            "type": "number",
            "description": "Total campaign emails opened by this organisation's users in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "org_emails_clicked_30d",
            "label": "Org emails clicked (30d)",
            "type": "number",
            "description": "Total campaign emails clicked by this organisation's users in the last 30 days.",
            "unit": "emails",
            "operators": ["=", "!=", ">", "<", ">=", "<="],
        },
        {
            "name": "org_last_email_opened_at",
            "label": "Org last email opened at",
            "type": "datetime",
            "description": "Timestamp of the most recent campaign email opened by any user in this organisation.",
            "operators": ["=", "!=", ">", "<", "IS NULL", "IS NOT NULL"],
        },
    ],
}


def get_field_registry() -> Dict[str, Any]:
    """Return the field definitions for the frontend rule builder."""
    return _FIELD_DEFINITIONS


# ---------------------------------------------------------------------------
# Rule tree compiler
# ---------------------------------------------------------------------------

def _validate_field(field: str, scope: str) -> None:
    """Raise BadRequestException if field is not in the whitelist for this scope."""
    allowed = ALLOWED_FIELDS.get(scope, set())
    if field not in allowed:
        raise BadRequestException(
            f"Unknown or disallowed field '{field}' for scope '{scope}'. "
            f"Allowed fields: {sorted(allowed)}"
        )


def _validate_operator(operator: str) -> None:
    """Raise BadRequestException if operator is not whitelisted."""
    if operator not in ALLOWED_OPERATORS:
        raise BadRequestException(
            f"Unknown or disallowed operator '{operator}'. "
            f"Allowed operators: {sorted(ALLOWED_OPERATORS)}"
        )


def _compile_condition(
    condition: Dict[str, Any],
    scope: str,
    params: Dict[str, Any],
    counter: List[int],
) -> str:
    """
    Compile a single leaf condition `{field, operator, value}` into a SQL fragment.

    Args:
        condition: The leaf node dict.
        scope:     'user' or 'organization'.
        params:    Accumulator dict for bind parameters (mutated in place).
        counter:   Single-element list holding the next available param index (mutated).

    Returns:
        SQL fragment string with named placeholders, e.g. "days_since_last_login > :p0"
    """
    field    = condition.get("field", "")
    operator = condition.get("operator", "")
    value    = condition.get("value")

    # Security: whitelist field + operator before any SQL construction.
    _validate_field(field, scope)
    _validate_operator(operator)

    # Column name is now safe (validated against whitelist — no user-supplied text in SQL).
    col = field

    # IS NULL / IS NOT NULL take no value — just emit the keyword clause.
    if operator in ("IS NULL", "IS NOT NULL"):
        return f"{col} {operator}"

    if operator in ("IN", "NOT IN"):
        if not isinstance(value, (list, tuple)):
            raise BadRequestException(
                f"Operator '{operator}' requires a list value for field '{field}'."
            )
        placeholders = []
        for v in value:
            key = f"p{counter[0]}"
            params[key] = v
            counter[0] += 1
            placeholders.append(f":{key}")
        return f"{col} {operator} ({', '.join(placeholders)})"

    elif operator == "BETWEEN":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise BadRequestException(
                f"Operator 'BETWEEN' requires a 2-element list for field '{field}'."
            )
        k_low  = f"p{counter[0]}";  counter[0] += 1
        k_high = f"p{counter[0]}";  counter[0] += 1
        params[k_low]  = value[0]
        params[k_high] = value[1]
        return f"{col} BETWEEN :{k_low} AND :{k_high}"

    else:
        key = f"p{counter[0]}"; counter[0] += 1
        params[key] = value
        return f"{col} {operator} :{key}"


def _compile_node(
    node: Dict[str, Any],
    scope: str,
    params: Dict[str, Any],
    counter: List[int],
    depth: int = 0,
) -> str:
    """
    Recursively compile a rule tree node into a SQL WHERE fragment.

    A node is either:
      - A group:     {"op": "AND"|"OR", "conditions": [...]}
      - A condition: {"field": "...", "operator": "...", "value": ...}
    """
    if depth > 10:
        raise BadRequestException("Rule tree exceeds maximum nesting depth of 10.")

    # Group node
    if "op" in node:
        logical_op = node["op"].upper()
        if logical_op not in ("AND", "OR"):
            raise BadRequestException(
                f"Invalid logical operator '{node['op']}'. Must be 'AND' or 'OR'."
            )
        children = node.get("conditions", [])
        if not children:
            raise BadRequestException("Group node must have at least one condition.")

        parts = [
            _compile_node(child, scope, params, counter, depth + 1)
            for child in children
        ]
        joined = f" {logical_op} ".join(f"({p})" for p in parts)
        return joined

    # Leaf condition node
    if "field" in node:
        return _compile_condition(node, scope, params, counter)

    raise BadRequestException(
        "Invalid rule node: must have either 'op' (group) or 'field' (condition)."
    )


def compile_rules(
    rule_tree: Dict[str, Any],
    scope: str,
) -> Tuple[str, Dict[str, Any]]:
    """
    Compile a rule tree into (where_clause, params).

    Args:
        rule_tree: JSON rule tree per API contract §2 schema.
        scope:     'user' or 'organization'.

    Returns:
        (where_clause, params) — where_clause uses named :p0 … :pN placeholders;
        params is the corresponding dict.

    Raises:
        BadRequestException on unknown field, disallowed operator, or malformed tree.
    """
    if scope not in ALLOWED_FIELDS:
        raise BadRequestException(
            f"Unknown scope '{scope}'. Must be 'user' or 'organization'."
        )

    params: Dict[str, Any] = {}
    counter: List[int] = [0]
    where_clause = _compile_node(rule_tree, scope, params, counter)
    return where_clause, params


# ---------------------------------------------------------------------------
# Preview + evaluate helpers
# ---------------------------------------------------------------------------

def preview_segment(
    db_session: Session,
    rule_tree: Dict[str, Any],
    scope: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute compiled rules and return {count, sample}.

    Args:
        db_session:       Active SQLAlchemy session.
        rule_tree:        Rule tree JSON.
        scope:            'user' or 'organization'.
        organization_id:  Optional org filter (restricts to one org's profiles).

    Returns:
        {"count": N, "sample": [{pk: ..., ...}, ...]}  (sample limited to 20 rows)
    """
    where_clause, params = compile_rules(rule_tree, scope)

    table = _SCOPE_TABLE[scope]
    pk    = _SCOPE_PK[scope]

    org_filter = ""
    if organization_id is not None:
        org_filter = " AND organization_id = :_org_id"
        params["_org_id"] = organization_id

    count_sql = text(
        f"SELECT COUNT(*) FROM {table} WHERE {where_clause}{org_filter}"
    )
    sample_sql = text(
        f"SELECT * FROM {table} WHERE {where_clause}{org_filter} LIMIT 20"
    )

    count_result  = db_session.execute(count_sql,  params).scalar() or 0
    sample_rows   = db_session.execute(sample_sql, params).mappings().all()
    sample        = [dict(row) for row in sample_rows]

    return {"count": count_result, "sample": sample}


def evaluate_segment(db_session: Session, segment_id: int) -> int:
    """
    Re-evaluate a segment: replace crm_segment_members rows and update member_count.

    Args:
        db_session:  Active SQLAlchemy session.
        segment_id:  PK of the crm_segments row.

    Returns:
        New member count.

    Raises:
        NotFoundException if segment not found.
    """
    # Lazy import to avoid circular deps at module load time.
    from ....models.crm.segments import CrmSegment, CrmSegmentMember

    segment = db_session.query(CrmSegment).filter(
        CrmSegment.id == segment_id,
        CrmSegment.deleted_date.is_(None),
    ).first()
    if not segment:
        raise NotFoundException(f"Segment {segment_id} not found.")

    scope      = segment.scope
    rule_tree  = segment.rules
    table      = _SCOPE_TABLE[scope]
    pk         = _SCOPE_PK[scope]

    where_clause, params = compile_rules(rule_tree, scope)

    # Restrict to the segment's org if specified.
    org_filter = ""
    if segment.organization_id:
        org_filter = " AND organization_id = :_seg_org_id"
        params["_seg_org_id"] = segment.organization_id

    # 1. Delete existing members for this segment.
    db_session.execute(
        text("DELETE FROM crm_segment_members WHERE segment_id = :sid"),
        {"sid": segment_id},
    )

    # 2. Insert fresh members.
    now_utc = datetime.now(timezone.utc)
    insert_sql = text(
        f"""
        INSERT INTO crm_segment_members (segment_id, member_type, member_id, evaluated_at)
        SELECT :sid, :mtype, {pk}, :now
        FROM   {table}
        WHERE  {where_clause}{org_filter}
        """
    )
    params.update({"sid": segment_id, "mtype": scope, "now": now_utc})
    db_session.execute(insert_sql, params)

    # 3. Count and store.
    count = db_session.execute(
        text("SELECT COUNT(*) FROM crm_segment_members WHERE segment_id = :sid"),
        {"sid": segment_id},
    ).scalar() or 0

    segment.member_count       = count
    segment.last_evaluated_at  = now_utc
    db_session.commit()

    logger.info("evaluate_segment: segment %d → %d members", segment_id, count)
    return count
