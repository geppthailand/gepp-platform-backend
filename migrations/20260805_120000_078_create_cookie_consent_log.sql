-- ============================================================================
-- Migration: Cookie-consent audit log (cookie_consent_log)
-- Date: 2026-08-05
-- Description: Server-side record of PDPA cookie-consent decisions made on gepp.me
--              (and any other origin-allowlisted marketing surface). Append-only:
--              every accept / reject / custom-save writes a NEW row, so a visitor's
--              consent history (including later changes / withdrawals) is auditable.
--
--              PDPA data-minimization: we do NOT store the raw client IP. `ip_hash`
--              is sha256(ip + salt) so repeat visits can be correlated without
--              retaining the address; `country` is the coarse CloudFront viewer
--              country only. `consent_id` is an anonymous per-browser UUID (not tied
--              to a real identity unless the visitor is separately logged in).
-- ============================================================================

CREATE TABLE IF NOT EXISTS cookie_consent_log (
    id             BIGSERIAL PRIMARY KEY,
    consent_id     UUID        NOT NULL,               -- anonymous per-visitor id (from the browser)
    necessary      BOOLEAN     NOT NULL DEFAULT TRUE,  -- always granted (strictly necessary)
    analytics      BOOLEAN     NOT NULL DEFAULT FALSE,
    preferences    BOOLEAN     NOT NULL DEFAULT FALSE,
    marketing      BOOLEAN     NOT NULL DEFAULT FALSE,
    policy_version INTEGER     NOT NULL,               -- the cookie-policy version consented to
    action         VARCHAR(32),                        -- accept_all | reject_all | custom
    page_url       TEXT,
    referrer       TEXT,
    user_agent     TEXT,
    origin         TEXT,
    country        VARCHAR(8),                          -- CloudFront viewer country (coarse)
    ip_hash        VARCHAR(64),                         -- sha256(ip + salt); NO raw IP stored (PDPA)
    consented_at   TIMESTAMPTZ,                         -- client-reported decision time
    created_date   TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- server receive time
);

-- Correlate a single visitor's decision history + query the latest per consent_id.
CREATE INDEX IF NOT EXISTS idx_cookie_consent_log_consent_id
    ON cookie_consent_log (consent_id, created_date DESC);

-- Audit browsing by time (e.g. "who consented this week").
CREATE INDEX IF NOT EXISTS idx_cookie_consent_log_created
    ON cookie_consent_log (created_date DESC);
