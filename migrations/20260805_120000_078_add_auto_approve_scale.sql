-- ============================================================================
-- Migration: Add auto_approve_scale_transactions flag to organizations
-- Date: 2026-08-05
-- Description: Org-level switch for auto-approving transactions that arrive from
--              IoT digital scales (POST /api/iot-devices/records). When TRUE the
--              transaction (and its records) are written as `approved` instead of
--              `pending`, with an auto-approval row logged in `transaction_audits`
--              (audit_type='auto_scale', by_human=FALSE).
--
--              Per-DEVICE override lives in iot_devices.device_settings JSONB as
--              `auto_approve_mode` ('inherit' | 'on' | 'off', default 'inherit')
--              so no column is needed there — see admin_service._normalize_device_settings.
--              Resolution order: device override → this org flag → FALSE.
--
--              DEFAULT FALSE keeps every existing organization on the current
--              pending-then-audit behaviour, so deploying this is a no-op until
--              an admin flips the flag.
-- ============================================================================

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS auto_approve_scale_transactions BOOLEAN NOT NULL DEFAULT FALSE;
