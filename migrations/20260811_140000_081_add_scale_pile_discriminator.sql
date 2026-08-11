-- ============================================================================
-- Migration: one weigh-in = one pile, for scale-recorded waste only
-- Date: 2026-08-11
-- Description: A traceability pile is keyed by
--                (origin, material, org, tag, tenant, year, month)
--              i.e. ONE pile per tenant per material per MONTH. That grain was
--              fine while a human dispatched from the web board once a month.
--
--              A digital scale weighs several times a day, and the code appends
--              every later record into the month's existing pile even after that
--              pile already has a transport (transaction_service.py:3402), while
--              a pile that has a transport is dropped from the "waiting to ship"
--              column for good (traceability_service.py:189-196). Net effect on
--              a scale site: the first dispatch of the month closes the pile and
--              everything that tenant delivers for the rest of the month becomes
--              invisible and unshippable.
--
--              This column makes each scale weigh-in its own pile, so a pile is
--              always created by one reading and always dispatched whole. That
--              keeps absolute_percentage correct by construction — the formula
--              divides by the sum of sibling transports
--              (traceability_service.py:2937-2941), which now equals the pile
--              weight — with no change to the formula and no partial-consumption
--              machinery.
--
--              NULL means "the old monthly grain", which is every existing row
--              and every non-scale flow. Those keep behaving exactly as today:
--              the lookups compare the column with =, and SQLAlchemy renders
--              `== None` as IS NULL, so a NULL-keyed lookup still matches the
--              NULL-keyed rows it always matched.
-- ============================================================================

ALTER TABLE traceability_transaction_group
    ADD COLUMN IF NOT EXISTS source_transaction_id BIGINT NULL REFERENCES transactions(id);

-- The group lookup filters on this alongside the other key columns. Partial —
-- the column is NULL for every row that predates a scale.
CREATE INDEX IF NOT EXISTS idx_traceability_group_source_transaction
    ON traceability_transaction_group (source_transaction_id)
    WHERE source_transaction_id IS NOT NULL;

COMMENT ON COLUMN traceability_transaction_group.source_transaction_id IS
    'Scale transaction that created this pile, making it a per-weigh-in pile instead of the monthly one. NULL = monthly grain (all pre-existing and non-scale rows). See migration 081.';
