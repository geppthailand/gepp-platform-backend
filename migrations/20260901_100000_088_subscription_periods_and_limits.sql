-- Migration 088 — subscription periods, transaction + file-size limits
-- Date: 2026-09-01
--
-- Context: ops needs to bill organizations by usage. The backoffice grows a
-- `Subscription` tab per org where each *subscription period* carries the plan,
-- a date range, a transactions-per-month allowance and a max file size; the
-- Configuration tab grows org-level DEFAULTS for the same two limits plus an
-- image-dimension cap.
--
-- The two limits mean deliberately opposite things and that shapes everything:
--
--   * transactions/month — NEVER blocks. A customer over their allowance keeps
--     entering data; the overage becomes a line on an invoice. So nothing here
--     is a constraint, and usage is recomputed from `transactions` rather than
--     counted (see below).
--   * max file size — DOES block. An upload above it is refused, after the
--     client has been given a chance to shrink the image.
--
-- `subscriptions` is EXTENDED rather than joined by a new `subscription_periods`
-- table. That row already IS a period: organization_id, plan_id, status,
-- current_period_starts_at / current_period_ends_at (both real TIMESTAMPTZ —
-- migration 063 writes NOW() into them, despite the ORM mis-declaring them as
-- String(50), which this change also fixes), create_transaction_limit and
-- duration_type. A parallel table would make "which plan is this org on?"
-- answerable two ways, with `organizations.subscription_id` pointing into one of
-- them arbitrarily.
--
-- So only TWO genuinely new things are needed on the period: a file-size limit
-- and a human label. Everything else already exists and is reused as-is —
-- notably `create_transaction_limit`, which is the per-MONTH allowance. The
-- period total is derived (allowance x months covered), never stored, so editing
-- the date range cannot leave a stale total behind.
--
-- Deliberately NOT added: a usage counter column. `subscription_monthly_quotas`
-- already has `create_transaction_usage`, and it is incremented on exactly one
-- write path (the BMA integration, bma_service.py:311) out of several — so it is
-- already wrong for most orgs and must not become a billing input. Usage is
-- derived from `transactions` at report time: idempotent, back-dateable, and
-- unable to drift.

-- ── 1. Period columns on `subscriptions` ──────────────────────────────

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS max_file_size_mb NUMERIC(8, 2);

-- Human label so ops can tell two periods apart in a list ("2026 renewal").
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS period_label VARCHAR(120);

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS notes TEXT;

-- Resolving "the period covering this date" is the hottest read in the feature.
CREATE INDEX IF NOT EXISTS idx_subscriptions_org_period
    ON subscriptions (organization_id, current_period_starts_at, current_period_ends_at)
    WHERE deleted_date IS NULL;

-- ── 2. Org-level defaults ─────────────────────────────────────────────
--
-- These are DEFAULTS, not enforcement: a period's own value wins whenever one
-- covers the date being asked about. They exist so a new org (or a gap between
-- periods) still has a sane answer, and so ops can set a house standard once.
--
-- All three are NULLable on purpose. NULL means "fall through to the system
-- default" and stays distinguishable from a deliberate 0, which would otherwise
-- read as "no transactions allowed" / "no uploads allowed".

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS default_transaction_limit_per_month INTEGER;

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS default_max_file_size_mb NUMERIC(8, 2);

-- Longest-edge cap applied when re-encoding an uploaded image to webp. Config
-- only — deliberately NOT a period column: it is a storage/rendering concern
-- rather than something billed, and per-period values would mean the same photo
-- is kept at different resolutions depending on when it happened to be sent.
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS max_image_dimension_px INTEGER;

-- ── 3. Documentation the next reader will actually see ────────────────

COMMENT ON COLUMN subscriptions.max_file_size_mb IS
    'Max size of a single uploaded file, in MB, for this period. ENFORCED (S3 content-length-range at presign + decoded-length check on the base64/QR path). NULL -> organizations.default_max_file_size_mb -> system default.';
COMMENT ON COLUMN subscriptions.create_transaction_limit IS
    'Transactions allowed per MONTH during this period. ADVISORY: never blocks creation, used for billing only. Period total = this x months covered.';
COMMENT ON COLUMN subscriptions.period_label IS
    'Optional human name for the period, shown in the backoffice list.';
COMMENT ON COLUMN subscriptions.current_period_starts_at IS
    'Period start. Despite the "current_" name this is the period''s own range — an org may have many rows, one per period.';

COMMENT ON COLUMN organizations.default_transaction_limit_per_month IS
    'Org default used when no subscription period covers the date. Advisory. NULL -> system default.';
COMMENT ON COLUMN organizations.default_max_file_size_mb IS
    'Org default max upload size in MB, used when no subscription period covers the date. NULL -> system default.';
COMMENT ON COLUMN organizations.max_image_dimension_px IS
    'Longest-edge cap for uploaded images, re-encoded to webp client-side. Config only, never per-period. NULL -> system default.';
