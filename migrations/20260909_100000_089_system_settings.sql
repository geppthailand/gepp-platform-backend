-- Migration 089 — global (platform-wide) settings
-- Date: 2026-09-09
--
-- Context: migration 088 made a subscription period mandatory in effect — no
-- period covering today and the org cannot log in or do anything (see
-- `services/subscriptions/access.py`). That policy is correct but it is also a
-- LOCKOUT, and it was hardcoded: the only way to soften it was a deploy. On the
-- current data 237 of 2,792 organizations would be blocked the moment it ships,
-- so ops needs a switch they can hold themselves.
--
-- Hence a general key/value store rather than one boolean column somewhere:
--
--   * A platform-wide flag has no natural home. It is not an org attribute, and
--     `organizations` is the wrong table for something that is not per-org —
--     putting it there means 2,792 copies of one truth.
--   * More global switches are coming (the backoffice grows a Global Settings
--     page with tabbed sections). One row per setting means the next one is an
--     INSERT, not a migration + model change + deploy.
--
-- JSONB for `value`, not TEXT: a setting is a boolean today and will be a
-- number or a small object soon (thresholds, allowlists). Storing '"true"' as
-- text and re-parsing it per call site is how two call sites end up disagreeing
-- about whether the string "false" is truthy.
--
-- The KEY SET IS NOT OPEN. `services/settings/global_settings.py` holds a
-- registry naming every known key, its type and its default, and refuses to
-- read or write anything else. A typo'd key must not silently become a new
-- setting that nothing honours — that reads as "I turned it off and nothing
-- happened".
--
-- A missing row is NOT an error: every key has a code default, so a fresh
-- database, a failed seed and a deleted row all behave identically. The table
-- only ever holds deliberate overrides.

BEGIN;

CREATE TABLE IF NOT EXISTS system_settings (
    -- The registry key, e.g. 'subscription.disable_when_not_in_period'.
    -- Dotted `section.name` so the backoffice can group without a second column.
    key           VARCHAR(120) PRIMARY KEY,
    value         JSONB NOT NULL,
    -- Who last changed it and when. A global switch that silently changes the
    -- behaviour of every tenant is the first thing anyone asks about during an
    -- incident, so the audit trail is part of the row, not an afterthought.
    updated_by    BIGINT,
    created_date  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE system_settings IS
    'Platform-wide settings, one row per key. Keys are validated against the '
    'registry in services/settings/global_settings.py; a missing row means '
    'the code default applies.';

-- NOTHING IS SEEDED, on purpose — the table starts empty.
--
-- The subscription gate ships OFF, but that default lives in the registry, not
-- in a row here. Seeding it would create a row with a NULL `updated_by` and an
-- `updated_date` of the deploy, which reads back as "somebody switched this at
-- 09:55" — a false audit entry about the single most consequential switch in
-- the platform. The registry default is the one source of truth, and an empty
-- table means "nobody has overridden anything", which is exactly true.
--
-- (The gate ships off because turning it on is a LOCKOUT: on current data 237
-- of 2,792 organizations have no period covering today, so enabling it blocks
-- 224 users and takes 20 QR forms dark. Ops back-dates periods for the
-- customers who should have them, watches the impact counter on the Global
-- Settings page fall, and flips the switch when that number is one they accept
-- — rather than discovering the number from a deploy.)

COMMIT;
