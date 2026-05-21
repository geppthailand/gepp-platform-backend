-- Migration: Allow traceability_consolidation_sources to reference a source GROUP
--            in addition to a source TRANSPORT.
-- Date: 2026-05-19
-- Why: Origin-column items (raw material in transaction_groups, no transport yet)
--      need to participate in the same consolidation event as arrived transports.
--      Today the join table only has source_transport_id, so origin-group
--      consolidations have no place to record their lineage.
--
--      After this migration, exactly ONE of (source_transport_id, source_group_id)
--      is populated per row. Existing rows are untouched.

-- 1) Add source_group_id (nullable)
ALTER TABLE traceability_consolidation_sources
    ADD COLUMN IF NOT EXISTS source_group_id BIGINT
        REFERENCES traceability_transaction_group(id) ON DELETE CASCADE;

-- 2) source_transport_id may be NULL when source_group_id is set
ALTER TABLE traceability_consolidation_sources
    ALTER COLUMN source_transport_id DROP NOT NULL;

-- 3) Enforce exclusivity: exactly one of the two FKs is set
ALTER TABLE traceability_consolidation_sources
    DROP CONSTRAINT IF EXISTS chk_consolidation_source_kind;
ALTER TABLE traceability_consolidation_sources
    ADD CONSTRAINT chk_consolidation_source_kind
    CHECK (
        (source_transport_id IS NOT NULL AND source_group_id IS NULL)
        OR (source_transport_id IS NULL AND source_group_id IS NOT NULL)
    );

-- 4) Drop the old UNIQUE(consolidation_id, source_transport_id) — it conflicted
--    with multi-NULL rows post-relaxation — and replace with two partial uniques.
ALTER TABLE traceability_consolidation_sources
    DROP CONSTRAINT IF EXISTS traceability_consolidation_sources_consolidation_id_sour_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consolidation_source_transport
    ON traceability_consolidation_sources(consolidation_id, source_transport_id)
    WHERE source_transport_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consolidation_source_group
    ON traceability_consolidation_sources(consolidation_id, source_group_id)
    WHERE source_group_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_consolidation_sources_group
    ON traceability_consolidation_sources(source_group_id)
    WHERE source_group_id IS NOT NULL;

COMMENT ON COLUMN traceability_consolidation_sources.source_group_id IS
    'Set when the consolidation source is a raw origin transaction_group (not yet shipped). Mutually exclusive with source_transport_id.';
