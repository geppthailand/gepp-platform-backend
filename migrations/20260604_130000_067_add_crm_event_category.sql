-- Migration 067 — allow 'crm' in crm_events.event_category.
--
-- The code already emits CRM-domain events with event_category='crm'
--   (lead_service.change_status → 'lead_status_changed',
--    crm/__init__.py public event ingest)
-- but the original CHECK constraint (migration 029) never listed 'crm', so every
-- lead status change raised CheckViolation, poisoning the request transaction and
-- 500-ing the status endpoint. Add 'crm' to align the DB with code intent.

ALTER TABLE crm_events DROP CONSTRAINT IF EXISTS chk_crm_event_category;
ALTER TABLE crm_events ADD CONSTRAINT chk_crm_event_category CHECK (event_category IN (
    'auth', 'transaction', 'traceability', 'gri', 'reward', 'iot', 'page', 'email', 'system', 'crm'
));
