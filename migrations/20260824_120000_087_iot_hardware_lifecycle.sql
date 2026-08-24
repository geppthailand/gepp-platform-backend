-- Migration 087 — IoT hardware lifecycle status, telemetry + history
-- Date: 2026-08-24
--
-- Context: `/v3-iot-hardwares` in the backoffice was a flat pair/unpair
-- table. Ops (non-technical) need to run the physical tablet fleet from
-- it: retire units, park them in maintenance, see which one is flat, and
-- read back "what happened to this tablet" — including problems a human
-- logged by hand.
--
-- Three additions:
--
--   1. Lifecycle status on `iot_hardwares` (active / maintenance / repair
--      / storage / retired) + who changed it and why. Plain whitelisted
--      VARCHAR rather than a lookup table: five values that ops read as
--      words, no join, nothing to administer.
--
--   2. Latest battery / network telemetry ON THE HARDWARE ROW. Battery
--      already lands in `iot_device_health`, but that table is keyed on
--      `device_id` — so a tablet that has never been paired (exactly the
--      population this page exists to triage) has no battery anywhere.
--      `/api/iot-hardwares/checkin` is the only writer that sees those
--      units, so it writes here.
--
--   3. Two history tables:
--      * `iot_hardware_battery_history` — 15-min buckets, upserted by
--        checkin. No worker needed: checkin already fires every ~5 s.
--      * `iot_hardware_history` — append-only timeline carrying BOTH
--        system events (pair / unpair / status_change / delete / restore)
--        AND human-entered issues + notes. One table, because "what
--        happened to this tablet?" is one question.

-- ── 1. Lifecycle status ───────────────────────────────────────────────

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(24) NOT NULL DEFAULT 'active';

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS status_note TEXT;

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS status_changed_by BIGINT;  -- user_locations.id

-- CHECK is added separately + guarded so re-running the migration on a
-- partially-applied DB doesn't error on a duplicate constraint name.
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_constraint WHERE conname = 'iot_hardwares_lifecycle_status_chk'
    ) THEN
        ALTER TABLE iot_hardwares
            ADD CONSTRAINT iot_hardwares_lifecycle_status_chk
            CHECK (lifecycle_status IN (
                'active', 'maintenance', 'repair', 'storage', 'retired'
            ));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS iot_hardwares_lifecycle_status
    ON iot_hardwares(lifecycle_status);

-- Default list order in the admin UI is `created_date DESC` (newest
-- registration first) — stable across the 5 s live refresh, unlike
-- last_checkin_at which reshuffles on every heartbeat.
CREATE INDEX IF NOT EXISTS iot_hardwares_created_date
    ON iot_hardwares(created_date DESC);

COMMENT ON COLUMN iot_hardwares.lifecycle_status IS
    'Physical-unit lifecycle: active | maintenance | repair | storage | retired. Independent of pairing. `retired` blocks force_login on checkin.';
COMMENT ON COLUMN iot_hardwares.status_note IS
    'Free-text reason for the current lifecycle_status (e.g. "screen cracked, sent to vendor 24/08").';

-- ── 2. Telemetry snapshot on the hardware row ─────────────────────────

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_battery_level INT;          -- 0–100
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_battery_charging BOOLEAN;
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_network_type VARCHAR(16);   -- wifi|cellular|ethernet|none
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_network_strength INT;       -- 0–100
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_storage_free_mb INT;
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_telemetry_at TIMESTAMPTZ;
-- Cheap "is this unit actually being used?" counter. Incremented on every
-- checkin; lets the UI distinguish a tablet that has phoned home twice
-- from one that has been in the field for months.
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS checkin_count BIGINT NOT NULL DEFAULT 0;
ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS first_checkin_at TIMESTAMPTZ;

COMMENT ON COLUMN iot_hardwares.last_battery_level IS
    'Battery % from the most recent /api/iot-hardwares/checkin. Present even for never-paired tablets, unlike iot_device_health.battery_level.';
COMMENT ON COLUMN iot_hardwares.checkin_count IS
    'Lifetime checkin count. Used by the admin UI to show usage intensity and to spot units that were provisioned but never deployed.';

-- ── 3a. Battery / online history (15-min buckets) ─────────────────────

CREATE TABLE IF NOT EXISTS iot_hardware_battery_history (
    hardware_id      BIGINT NOT NULL REFERENCES iot_hardwares(id) ON DELETE CASCADE,
    bucket_start     TIMESTAMPTZ NOT NULL,
    -- Last sample wins for the headline value; min/max preserve the
    -- in-bucket swing so a 15-min bucket can still show a discharge dip.
    battery_level    INT,
    battery_min      INT,
    battery_max      INT,
    battery_charging BOOLEAN,
    network_type     VARCHAR(16),
    network_strength INT,
    samples          INT NOT NULL DEFAULT 1,
    last_checkin_at  TIMESTAMPTZ,
    PRIMARY KEY (hardware_id, bucket_start)
);

CREATE INDEX IF NOT EXISTS iot_hardware_battery_history_bucket
    ON iot_hardware_battery_history (bucket_start DESC);

COMMENT ON TABLE iot_hardware_battery_history IS
    'Per-physical-tablet battery + network history in 15-min buckets. Upserted directly by /api/iot-hardwares/checkin (no worker). Retention 30 days, purged by POST /admin/iot-devices/snapshot-aggregate.';

-- ── 3b. Event + issue timeline ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS iot_hardware_history (
    id           BIGSERIAL PRIMARY KEY,
    hardware_id  BIGINT NOT NULL REFERENCES iot_hardwares(id) ON DELETE CASCADE,
    -- pair | unpair | status_change | delete | restore | note | issue |
    -- battery_low | offline_gap | checkin_after_delete
    event_type   VARCHAR(32) NOT NULL,
    -- info | warning | critical — drives the timeline colour and the
    -- "needs attention" counter (open rows with severity <> 'info').
    severity     VARCHAR(16) NOT NULL DEFAULT 'info',
    title        VARCHAR(200) NOT NULL,
    detail       TEXT,
    payload      JSONB,
    -- Only `issue` rows are resolvable; system events are facts, not
    -- tickets. NULL resolved_date on an issue = still open.
    resolved_date TIMESTAMPTZ,
    resolved_by   BIGINT,
    created_by    BIGINT,   -- user_locations.id; NULL = written by the system
    created_date  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS iot_hardware_history_hw_time
    ON iot_hardware_history (hardware_id, created_date DESC);

-- Drives the "open issues" badge per row in the list — partial index so
-- it stays tiny regardless of how much system-event chatter accumulates.
CREATE INDEX IF NOT EXISTS iot_hardware_history_open_issues
    ON iot_hardware_history (hardware_id)
    WHERE event_type = 'issue' AND resolved_date IS NULL;

COMMENT ON TABLE iot_hardware_history IS
    'Append-only timeline per physical tablet. Carries system events (pair/unpair/status_change/delete/restore) AND ops-entered notes/issues so "what happened to this unit?" is one query.';

-- ── Backfill: give existing rows a sane starting point ────────────────
-- status_changed_at defaults to the row creation time so the UI never
-- shows "changed —" for a fleet that predates this migration.
UPDATE iot_hardwares
   SET status_changed_at = COALESCE(status_changed_at, created_date)
 WHERE status_changed_at IS NULL;

-- Any hardware that has ever checked in gets first_checkin_at seeded to
-- its last known checkin (best available approximation) so "in service
-- since" isn't blank for the existing fleet.
UPDATE iot_hardwares
   SET first_checkin_at = last_checkin_at
 WHERE first_checkin_at IS NULL
   AND last_checkin_at IS NOT NULL;
