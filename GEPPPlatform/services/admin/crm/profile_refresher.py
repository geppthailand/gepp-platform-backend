"""
CRM Profile Refresher — nightly batch job that rebuilds crm_user_profiles
and crm_org_profiles from crm_events using a single parameterized SQL UPSERT
per table.

Entry points:
  refresh_user_profiles(db_session)         — called by cron / Lambda scheduler
  refresh_org_profiles(db_session)          — same
  refresh_email_engagement(db_session)      — Sprint 4: email stats from crm_events
  run_full_refresh(db_session)              — calls all three in sequence

CLI:
  python -m GEPPPlatform.services.admin.crm.profile_refresher

All SQL is parameterized via SQLAlchemy ``text()`` + bound params.
No ORM round-trips per row — this is a bulk set-based UPSERT.

Engagement score formula (per brief):
  score = 40 * min(login_count_30d / 20, 1)
        + 30 * min(transaction_count_30d / 50, 1)
        + 15 * min(reward_claim_count_30d / 10, 1)
        + 15 * min(iot_readings_count_30d / 100, 1)

Tier:
  active   if score >= 70
  at_risk  if score >= 40
  dormant  if score <  40

Email engagement rollup (Sprint 4 — 30-day window):
  Reads crm_events WHERE event_category='email' AND occurred_at > NOW()-30d.
  Aggregates per user_location_id → UPSERTs emails_received_30d / emails_opened_30d /
  emails_clicked_30d / last_email_received_at / last_email_opened_at into
  crm_user_profiles.
  Mirrors the same for organization_id → crm_org_profiles (org_* columns).
  Users/orgs with no email events in the last 30 days are reset to zero.
  Idempotent: running twice produces the same counts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─── User profile UPSERT ────────────────────────────────────────────────────
# Single-pass, set-based query that:
#   1. Aggregates crm_events per user over different windows
#   2. Joins user_locations for first_login_at via the min occurred_at of 'user_login'
#   3. Calculates engagement_score inline using the formula from the brief
#   4. UPSERTs into crm_user_profiles (ON CONFLICT … DO UPDATE)
#
# Performance notes:
#   - Uses only the indexed columns (user_location_id, occurred_at, event_type)
#   - FILTER on event_type keeps each aggregate narrow
#   - Scoped to is_user = TRUE rows only

_USER_UPSERT_SQL = text("""
INSERT INTO crm_user_profiles (
    user_location_id,
    organization_id,
    last_login_at,
    days_since_last_login,
    login_count_30d,
    transaction_count_30d,
    transaction_count_lifetime,
    qr_count_30d,
    reward_claim_count_30d,
    iot_readings_count_30d,
    gri_submission_count_30d,
    traceability_count_30d,
    first_login_at,
    onboarded,
    engagement_score,
    activity_tier,
    last_profile_refresh_at,
    created_date,
    updated_date
)
SELECT
    ul.id                                                           AS user_location_id,
    ul.organization_id                                             AS organization_id,

    -- Last login (any time)
    MAX(e.occurred_at) FILTER (WHERE e.event_type = 'user_login') AS last_login_at,

    -- Days since last login (NULL when never logged in)
    CASE
        WHEN MAX(e.occurred_at) FILTER (WHERE e.event_type = 'user_login') IS NULL
        THEN NULL
        ELSE EXTRACT(
            DAY FROM (
                :now - MAX(e.occurred_at) FILTER (WHERE e.event_type = 'user_login')
            )
        )::INT
    END                                                             AS days_since_last_login,

    -- 30-day counts
    COUNT(*) FILTER (
        WHERE e.event_type = 'user_login'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS login_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'transaction_created'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS transaction_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'transaction_created'
    )::INT                                                          AS transaction_count_lifetime,

    COUNT(*) FILTER (
        WHERE e.event_type = 'transaction_qr_input'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS qr_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'reward_claimed'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS reward_claim_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'scale_reading_received'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS iot_readings_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'gri_data_submitted'
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS gri_submission_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type IN ('traceability_created', 'transport_confirmed', 'disposal_recorded')
          AND e.occurred_at >= :window_30d
    )::INT                                                          AS traceability_count_30d,

    -- First login ever
    MIN(e.occurred_at) FILTER (WHERE e.event_type = 'user_login')  AS first_login_at,

    -- Onboarded = has ever logged in
    (COUNT(*) FILTER (WHERE e.event_type = 'user_login') > 0)      AS onboarded,

    -- Engagement score (formula from brief — inline, parameterized denominators)
    ROUND(
        (
            40.0 * LEAST(
                COUNT(*) FILTER (
                    WHERE e.event_type = 'user_login'
                      AND e.occurred_at >= :window_30d
                )::FLOAT / NULLIF(:login_denom, 0),
                1.0
            )
          + 30.0 * LEAST(
                COUNT(*) FILTER (
                    WHERE e.event_type = 'transaction_created'
                      AND e.occurred_at >= :window_30d
                )::FLOAT / NULLIF(:txn_denom, 0),
                1.0
            )
          + 15.0 * LEAST(
                COUNT(*) FILTER (
                    WHERE e.event_type = 'reward_claimed'
                      AND e.occurred_at >= :window_30d
                )::FLOAT / NULLIF(:reward_denom, 0),
                1.0
            )
          + 15.0 * LEAST(
                COUNT(*) FILTER (
                    WHERE e.event_type = 'scale_reading_received'
                      AND e.occurred_at >= :window_30d
                )::FLOAT / NULLIF(:iot_denom, 0),
                1.0
            )
        )::NUMERIC,
        2
    )                                                               AS engagement_score,

    -- Tier based on score (computed again, identical formula)
    CASE
        WHEN ROUND(
            (
                40.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'user_login'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:login_denom, 0),
                    1.0
                )
              + 30.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'transaction_created'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:txn_denom, 0),
                    1.0
                )
              + 15.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'reward_claimed'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:reward_denom, 0),
                    1.0
                )
              + 15.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'scale_reading_received'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:iot_denom, 0),
                    1.0
                )
            )::NUMERIC,
            2
        ) >= 70 THEN 'active'
        WHEN ROUND(
            (
                40.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'user_login'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:login_denom, 0),
                    1.0
                )
              + 30.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'transaction_created'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:txn_denom, 0),
                    1.0
                )
              + 15.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'reward_claimed'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:reward_denom, 0),
                    1.0
                )
              + 15.0 * LEAST(
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'scale_reading_received'
                          AND e.occurred_at >= :window_30d
                    )::FLOAT / NULLIF(:iot_denom, 0),
                    1.0
                )
            )::NUMERIC,
            2
        ) >= 40 THEN 'at_risk'
        ELSE 'dormant'
    END                                                             AS activity_tier,

    :now                                                            AS last_profile_refresh_at,
    NOW()                                                           AS created_date,
    NOW()                                                           AS updated_date

FROM user_locations ul
LEFT JOIN crm_events e ON e.user_location_id = ul.id
WHERE ul.is_user = TRUE
  AND ul.is_active = TRUE
  AND ul.deleted_date IS NULL
GROUP BY ul.id, ul.organization_id

ON CONFLICT (user_location_id) DO UPDATE SET
    organization_id           = EXCLUDED.organization_id,
    last_login_at             = EXCLUDED.last_login_at,
    days_since_last_login     = EXCLUDED.days_since_last_login,
    login_count_30d           = EXCLUDED.login_count_30d,
    transaction_count_30d     = EXCLUDED.transaction_count_30d,
    transaction_count_lifetime= EXCLUDED.transaction_count_lifetime,
    qr_count_30d              = EXCLUDED.qr_count_30d,
    reward_claim_count_30d    = EXCLUDED.reward_claim_count_30d,
    iot_readings_count_30d    = EXCLUDED.iot_readings_count_30d,
    gri_submission_count_30d  = EXCLUDED.gri_submission_count_30d,
    traceability_count_30d    = EXCLUDED.traceability_count_30d,
    first_login_at            = EXCLUDED.first_login_at,
    onboarded                 = EXCLUDED.onboarded,
    engagement_score          = EXCLUDED.engagement_score,
    activity_tier             = EXCLUDED.activity_tier,
    last_profile_refresh_at   = EXCLUDED.last_profile_refresh_at,
    updated_date              = NOW()
""")


# ─── Org profile UPSERT ─────────────────────────────────────────────────────
# Aggregates crm_events per org.  Org-level engagement tier mirrors the
# proportion of active users: ≥ 50% active users → "active",
# ≥ 20% → "at_risk", else "dormant".

_ORG_UPSERT_SQL = text("""
INSERT INTO crm_org_profiles (
    organization_id,
    active_user_count_30d,
    total_user_count,
    active_user_ratio,
    transaction_count_30d,
    traceability_count_30d,
    gri_submission_count_30d,
    subscription_plan_id,
    subscription_active,
    activity_tier,
    last_activity_at,
    last_profile_refresh_at,
    created_date,
    updated_date
)
SELECT
    o.id                                                    AS organization_id,

    -- Active users in last 30 days = distinct users who logged in
    COUNT(DISTINCT e.user_location_id) FILTER (
        WHERE e.event_type = 'user_login'
          AND e.occurred_at >= :window_30d
    )::INT                                                  AS active_user_count_30d,

    -- Total user count from user_locations
    COALESCE(uc.total_users, 0)                             AS total_user_count,

    -- Ratio (0–100)
    CASE
        WHEN COALESCE(uc.total_users, 0) = 0 THEN 0
        ELSE ROUND(
            (
                COUNT(DISTINCT e.user_location_id) FILTER (
                    WHERE e.event_type = 'user_login'
                      AND e.occurred_at >= :window_30d
                )::NUMERIC
                / uc.total_users::NUMERIC
            ) * 100,
            2
        )
    END                                                     AS active_user_ratio,

    COUNT(*) FILTER (
        WHERE e.event_type = 'transaction_created'
          AND e.occurred_at >= :window_30d
    )::INT                                                  AS transaction_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type IN ('traceability_created', 'transport_confirmed', 'disposal_recorded')
          AND e.occurred_at >= :window_30d
    )::INT                                                  AS traceability_count_30d,

    COUNT(*) FILTER (
        WHERE e.event_type = 'gri_data_submitted'
          AND e.occurred_at >= :window_30d
    )::INT                                                  AS gri_submission_count_30d,

    -- Subscription info from the org's most recently activated subscription
    sub.plan_id                                             AS subscription_plan_id,
    (sub.status = 'active')                                 AS subscription_active,

    -- Org-level tier: based on active_user_ratio
    CASE
        WHEN COALESCE(uc.total_users, 0) = 0 THEN 'dormant'
        WHEN ROUND(
            COUNT(DISTINCT e.user_location_id) FILTER (
                WHERE e.event_type = 'user_login'
                  AND e.occurred_at >= :window_30d
            )::NUMERIC / uc.total_users::NUMERIC * 100, 2
        ) >= 50 THEN 'active'
        WHEN ROUND(
            COUNT(DISTINCT e.user_location_id) FILTER (
                WHERE e.event_type = 'user_login'
                  AND e.occurred_at >= :window_30d
            )::NUMERIC / uc.total_users::NUMERIC * 100, 2
        ) >= 20 THEN 'at_risk'
        ELSE 'dormant'
    END                                                     AS activity_tier,

    MAX(e.occurred_at)                                      AS last_activity_at,
    :now                                                    AS last_profile_refresh_at,
    NOW()                                                   AS created_date,
    NOW()                                                   AS updated_date

FROM organizations o
LEFT JOIN crm_events e ON e.organization_id = o.id
-- Total users per org (is_user + active + not deleted)
LEFT JOIN (
    SELECT organization_id, COUNT(*) AS total_users
    FROM user_locations
    WHERE is_user = TRUE
      AND is_active = TRUE
      AND deleted_date IS NULL
    GROUP BY organization_id
) uc ON uc.organization_id = o.id
-- Latest active subscription per org
LEFT JOIN LATERAL (
    SELECT plan_id, status
    FROM subscriptions
    WHERE organization_id = o.id
      AND is_active = TRUE
    ORDER BY created_date DESC
    LIMIT 1
) sub ON TRUE
WHERE o.deleted_date IS NULL
GROUP BY o.id, uc.total_users, sub.plan_id, sub.status

ON CONFLICT (organization_id) DO UPDATE SET
    active_user_count_30d     = EXCLUDED.active_user_count_30d,
    total_user_count          = EXCLUDED.total_user_count,
    active_user_ratio         = EXCLUDED.active_user_ratio,
    transaction_count_30d     = EXCLUDED.transaction_count_30d,
    traceability_count_30d    = EXCLUDED.traceability_count_30d,
    gri_submission_count_30d  = EXCLUDED.gri_submission_count_30d,
    subscription_plan_id      = EXCLUDED.subscription_plan_id,
    subscription_active       = EXCLUDED.subscription_active,
    activity_tier             = EXCLUDED.activity_tier,
    last_activity_at          = EXCLUDED.last_activity_at,
    last_profile_refresh_at   = EXCLUDED.last_profile_refresh_at,
    updated_date              = NOW()
""")


# ─── Public entry points ─────────────────────────────────────────────────────

def refresh_user_profiles(db_session: Session) -> dict:
    """
    Rebuild all rows of crm_user_profiles from crm_events.

    Returns a summary dict ``{"rows_upserted": N, "duration_s": X}``.
    Safe to call repeatedly (idempotent UPSERT).
    """
    t0 = datetime.now(timezone.utc)
    now = t0
    from datetime import timedelta
    window_30d = now - timedelta(days=30)

    params = {
        "now": now,
        "window_30d": window_30d,
        # Score denominators (parameterized so tests can override)
        "login_denom": 20,
        "txn_denom": 50,
        "reward_denom": 10,
        "iot_denom": 100,
    }

    result = db_session.execute(_USER_UPSERT_SQL, params)
    db_session.commit()

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    rows = result.rowcount if result.rowcount >= 0 else -1
    logger.info("refresh_user_profiles: upserted %d rows in %.2fs", rows, elapsed)
    return {"rows_upserted": rows, "duration_s": round(elapsed, 3)}


def refresh_org_profiles(db_session: Session) -> dict:
    """
    Rebuild all rows of crm_org_profiles from crm_events.

    Returns a summary dict ``{"rows_upserted": N, "duration_s": X}``.
    """
    t0 = datetime.now(timezone.utc)
    now = t0
    from datetime import timedelta
    window_30d = now - timedelta(days=30)

    params = {
        "now": now,
        "window_30d": window_30d,
    }

    result = db_session.execute(_ORG_UPSERT_SQL, params)
    db_session.commit()

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    rows = result.rowcount if result.rowcount >= 0 else -1
    logger.info("refresh_org_profiles: upserted %d rows in %.2fs", rows, elapsed)
    return {"rows_upserted": rows, "duration_s": round(elapsed, 3)}


# ─── Email engagement UPSERT (Sprint 4) ────────────────────────────────────────
# Two-phase approach:
#   Phase 1 — aggregate email events per user/org from crm_events (30-day window).
#   Phase 2 — UPSERT the counts into the profile tables; reset zero for absent rows.
#
# Idempotency: running twice with the same event data produces identical column values
# because:
#   - Phase 1 is a pure read (SELECT/aggregate).
#   - Phase 2 uses ON CONFLICT … DO UPDATE SET, so re-running overwrites with the
#     same computed values.
#   - The "reset to zero" UPDATE at the end ensures users/orgs with no email events
#     in the last 30 days are not left with stale non-zero counts from a prior run.

_EMAIL_USER_AGG_SQL = text("""
SELECT
    user_location_id,
    COUNT(*) FILTER (WHERE event_type = 'email_sent')    AS emails_received_30d,
    COUNT(*) FILTER (WHERE event_type = 'email_opened')  AS emails_opened_30d,
    COUNT(*) FILTER (WHERE event_type = 'email_clicked') AS emails_clicked_30d,
    MAX(occurred_at) FILTER (WHERE event_type = 'email_sent')   AS last_email_received_at,
    MAX(occurred_at) FILTER (WHERE event_type = 'email_opened') AS last_email_opened_at
FROM crm_events
WHERE event_category = 'email'
  AND occurred_at > :window_30d
  AND user_location_id IS NOT NULL
GROUP BY user_location_id
""")

_EMAIL_ORG_AGG_SQL = text("""
SELECT
    organization_id,
    COUNT(*) FILTER (WHERE event_type = 'email_sent')    AS org_emails_received_30d,
    COUNT(*) FILTER (WHERE event_type = 'email_opened')  AS org_emails_opened_30d,
    COUNT(*) FILTER (WHERE event_type = 'email_clicked') AS org_emails_clicked_30d,
    MAX(occurred_at) FILTER (WHERE event_type = 'email_opened') AS org_last_email_opened_at
FROM crm_events
WHERE event_category = 'email'
  AND occurred_at > :window_30d
  AND organization_id IS NOT NULL
GROUP BY organization_id
""")


def refresh_email_engagement(db_session: Session) -> dict:
    """
    Aggregate email events from crm_events (30-day window) and UPSERT into
    crm_user_profiles and crm_org_profiles.

    Phase 1 — SELECT aggregate from crm_events.
    Phase 2 — For each user/org row: UPDATE crm_*_profiles with computed counts.
    Phase 3 — Reset rows with no email events in last 30 days to zero.

    Safe to call repeatedly (idempotent).
    Returns {"user_rows_updated": N, "org_rows_updated": M, "duration_s": X}.
    """
    from datetime import timedelta

    t0 = datetime.now(timezone.utc)
    window_30d = t0 - timedelta(days=30)
    params_window = {"window_30d": window_30d}

    # ── User: aggregate ────────────────────────────────────────────────────────
    user_rows = db_session.execute(_EMAIL_USER_AGG_SQL, params_window).fetchall()
    user_ids_updated: list = []
    for row in user_rows:
        (uid, recv, opened, clicked, last_recv, last_opened) = row
        db_session.execute(
            text("""
                UPDATE crm_user_profiles
                SET
                    emails_received_30d    = :recv,
                    emails_opened_30d      = :opened,
                    emails_clicked_30d     = :clicked,
                    last_email_received_at = :last_recv,
                    last_email_opened_at   = :last_opened,
                    updated_date           = NOW()
                WHERE user_location_id = :uid
            """),
            {
                "uid": uid,
                "recv": int(recv or 0),
                "opened": int(opened or 0),
                "clicked": int(clicked or 0),
                "last_recv": last_recv,
                "last_opened": last_opened,
            },
        )
        user_ids_updated.append(uid)

    # Phase 3 — reset users with no email events in last 30d to zero
    if user_ids_updated:
        db_session.execute(
            text("""
                UPDATE crm_user_profiles
                SET
                    emails_received_30d    = 0,
                    emails_opened_30d      = 0,
                    emails_clicked_30d     = 0,
                    last_email_received_at = NULL,
                    last_email_opened_at   = NULL,
                    updated_date           = NOW()
                WHERE user_location_id != ALL(:active_ids)
                  AND (emails_received_30d > 0
                       OR emails_opened_30d > 0
                       OR emails_clicked_30d > 0)
            """),
            {"active_ids": user_ids_updated},
        )
    else:
        # No email events at all in 30 days — reset everything
        db_session.execute(
            text("""
                UPDATE crm_user_profiles
                SET
                    emails_received_30d    = 0,
                    emails_opened_30d      = 0,
                    emails_clicked_30d     = 0,
                    last_email_received_at = NULL,
                    last_email_opened_at   = NULL,
                    updated_date           = NOW()
                WHERE emails_received_30d > 0
                   OR emails_opened_30d > 0
                   OR emails_clicked_30d > 0
            """),
        )

    # ── Org: aggregate ─────────────────────────────────────────────────────────
    org_rows = db_session.execute(_EMAIL_ORG_AGG_SQL, params_window).fetchall()
    org_ids_updated: list = []
    for row in org_rows:
        (oid, recv, opened, clicked, last_opened) = row
        db_session.execute(
            text("""
                UPDATE crm_org_profiles
                SET
                    org_emails_received_30d  = :recv,
                    org_emails_opened_30d    = :opened,
                    org_emails_clicked_30d   = :clicked,
                    org_last_email_opened_at = :last_opened,
                    updated_date             = NOW()
                WHERE organization_id = :oid
            """),
            {
                "oid": oid,
                "recv": int(recv or 0),
                "opened": int(opened or 0),
                "clicked": int(clicked or 0),
                "last_opened": last_opened,
            },
        )
        org_ids_updated.append(oid)

    # Phase 3 — reset orgs with no email events in last 30d to zero
    if org_ids_updated:
        db_session.execute(
            text("""
                UPDATE crm_org_profiles
                SET
                    org_emails_received_30d  = 0,
                    org_emails_opened_30d    = 0,
                    org_emails_clicked_30d   = 0,
                    org_last_email_opened_at = NULL,
                    updated_date             = NOW()
                WHERE organization_id != ALL(:active_ids)
                  AND (org_emails_received_30d > 0
                       OR org_emails_opened_30d > 0
                       OR org_emails_clicked_30d > 0)
            """),
            {"active_ids": org_ids_updated},
        )
    else:
        db_session.execute(
            text("""
                UPDATE crm_org_profiles
                SET
                    org_emails_received_30d  = 0,
                    org_emails_opened_30d    = 0,
                    org_emails_clicked_30d   = 0,
                    org_last_email_opened_at = NULL,
                    updated_date             = NOW()
                WHERE org_emails_received_30d > 0
                   OR org_emails_opened_30d > 0
                   OR org_emails_clicked_30d > 0
            """),
        )

    db_session.commit()
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    logger.info(
        "refresh_email_engagement: %d user rows, %d org rows in %.2fs",
        len(user_ids_updated), len(org_ids_updated), elapsed,
    )
    return {
        "user_rows_updated": len(user_ids_updated),
        "org_rows_updated": len(org_ids_updated),
        "duration_s": round(elapsed, 3),
    }


def run_full_refresh(db_session: Session) -> dict:
    """Run all three refreshes in sequence: users → orgs → email engagement."""
    user_result = refresh_user_profiles(db_session)
    org_result = refresh_org_profiles(db_session)
    email_result = refresh_email_engagement(db_session)
    return {
        "user_profiles": user_result,
        "org_profiles": org_result,
        "email_engagement": email_result,
    }


# ─── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Bootstrap database session using the same factory as Lambda
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    try:
        from GEPPPlatform.database import get_db_session  # type: ignore
        session = get_db_session()
        try:
            summary = run_full_refresh(session)
            logger.info("Full refresh complete: %s", summary)
        finally:
            session.close()
    except ImportError:
        # Fallback: allow import without GEPPPlatform context (for lint / type-check)
        logger.error(
            "Could not import GEPPPlatform.database. "
            "Run from the v3/backend directory with PYTHONPATH set."
        )
        sys.exit(1)
