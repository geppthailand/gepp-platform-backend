-- ──────────────────────────────────────────────────────────────────────────────
-- 039 — Add is_active column to all CRM tables
--
-- Sprint 0 quick-fix follow-up. Discovered while smoke-testing migration 038.
--
-- Why: All CRM SQLAlchemy models inherit BaseModel which declares
--      `is_active = Column(Boolean, nullable=False, default=True)`.
--      The CRM table migrations (029-037) were authored without this column,
--      causing INSERTs from SQLAlchemy to fail with:
--          column "is_active" of relation "crm_segments" does not exist
--      (visible the moment anyone POSTs a segment via the admin API).
--
-- What: Adds `is_active BOOLEAN NOT NULL DEFAULT TRUE` to the 8 CRM tables
--       missing it. Idempotent via IF NOT EXISTS.
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE crm_events              ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_org_profiles        ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_user_profiles       ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_segments            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_segment_members     ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_campaigns           ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_campaign_deliveries ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE crm_unsubscribes        ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
