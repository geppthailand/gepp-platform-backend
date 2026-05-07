-- Migration 053 — Rename device_* log tables → iot_device_* (Postgres only).
-- Date: 2026-05-05
--
-- The device_health / device_events / device_commands / device_health_history
-- tables were named without the `iot_` namespace prefix in migrations 046–
-- 050. This made them ambiguous with any future non-IoT "device" concept
-- and inconsistent with `iot_devices` + `iot_hardwares` which DO use the
-- prefix. Rename for clarity. Indexes and FKs follow the table rename
-- automatically; PK names are renamed explicitly so future ALTER stmts
-- targeting the PK don't fail.
--
-- Idempotent: every rename is gated on `IF EXISTS` and `IF NOT EXISTS`
-- so re-running the migration on a partially-applied DB is safe.

-- 1. device_health → iot_device_health
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'device_health') THEN
        ALTER TABLE device_health RENAME TO iot_device_health;
    END IF;
END $$;

-- 2. device_events → iot_device_events
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'device_events') THEN
        ALTER TABLE device_events RENAME TO iot_device_events;
    END IF;
END $$;

-- 3. device_commands → iot_device_commands
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'device_commands') THEN
        ALTER TABLE device_commands RENAME TO iot_device_commands;
    END IF;
END $$;

-- 4. device_health_history → iot_device_health_history
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'device_health_history') THEN
        ALTER TABLE device_health_history RENAME TO iot_device_health_history;
    END IF;
END $$;

-- Rename PK constraints so the namespace is consistent end-to-end.
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_constraint WHERE conname = 'device_health_pkey') THEN
        ALTER TABLE iot_device_health
            RENAME CONSTRAINT device_health_pkey TO iot_device_health_pkey;
    END IF;
    IF EXISTS (SELECT FROM pg_constraint WHERE conname = 'device_events_pkey') THEN
        ALTER TABLE iot_device_events
            RENAME CONSTRAINT device_events_pkey TO iot_device_events_pkey;
    END IF;
    IF EXISTS (SELECT FROM pg_constraint WHERE conname = 'device_commands_pkey') THEN
        ALTER TABLE iot_device_commands
            RENAME CONSTRAINT device_commands_pkey TO iot_device_commands_pkey;
    END IF;
    IF EXISTS (SELECT FROM pg_constraint WHERE conname = 'device_health_history_pkey') THEN
        ALTER TABLE iot_device_health_history
            RENAME CONSTRAINT device_health_history_pkey TO iot_device_health_history_pkey;
    END IF;
END $$;

-- Rename sequences for any BIGSERIAL pkeys so `pg_dump` / `\d` show
-- consistent names.
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_class WHERE relkind = 'S' AND relname = 'device_events_id_seq') THEN
        ALTER SEQUENCE device_events_id_seq RENAME TO iot_device_events_id_seq;
    END IF;
    IF EXISTS (SELECT FROM pg_class WHERE relkind = 'S' AND relname = 'device_commands_id_seq') THEN
        ALTER SEQUENCE device_commands_id_seq RENAME TO iot_device_commands_id_seq;
    END IF;
    IF EXISTS (SELECT FROM pg_class WHERE relkind = 'S' AND relname = 'device_health_history_id_seq') THEN
        ALTER SEQUENCE device_health_history_id_seq RENAME TO iot_device_health_history_id_seq;
    END IF;
END $$;

COMMENT ON TABLE iot_device_health IS
    'Latest health snapshot per IoT tablet. Upserted on every /sync.';
COMMENT ON TABLE iot_device_events IS
    'Append-only IoT device action trail. Daily rollover sweeper deletes records older than yesterday on the first /sync after midnight.';
COMMENT ON TABLE iot_device_commands IS
    'Admin → IoT device command queue. FSM: pending → delivered → succeeded|failed|expired.';
COMMENT ON TABLE iot_device_health_history IS
    '5-min health buckets per IoT device for the Fleet online% chart. 7-day retention enforced by aggregate_health_snapshot.';
