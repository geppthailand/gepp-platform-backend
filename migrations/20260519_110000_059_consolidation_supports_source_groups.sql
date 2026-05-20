-- Migration: Allow consolidation_sources to reference a transaction_group instead of a transport.
-- Date: 2026-05-19
-- Description:
--   The original design only let consolidations reference existing TransportTransactions
--   (arrived sources). Consolidating fresh-from-origin items had to go through a side
--   channel that wrote no consolidation rows — so the DB lineage was wrong.
--
--   This migration makes source_transport_id NULLable and adds source_group_id so the
--   same consolidation tables can record either kind of source. Exactly one of the two
--   FK columns must be set per row, enforced by a CHECK constraint.

ALTER TABLE traceability_consolidation_sources
    ALTER COLUMN source_transport_id DROP NOT NULL;

ALTER TABLE traceability_consolidation_sources
    ADD COLUMN IF NOT EXISTS source_group_id BIGINT
    REFERENCES traceability_transaction_group(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_consolidation_sources_group
    ON traceability_consolidation_sources(source_group_id);

-- Exactly one of source_transport_id / source_group_id must be set.
ALTER TABLE traceability_consolidation_sources
    DROP CONSTRAINT IF EXISTS traceability_consolidation_sources_source_xor;

ALTER TABLE traceability_consolidation_sources
    ADD CONSTRAINT traceability_consolidation_sources_source_xor
    CHECK (
        (source_transport_id IS NOT NULL AND source_group_id IS NULL)
        OR (source_transport_id IS NULL AND source_group_id IS NOT NULL)
    );

-- Replace the old composite UNIQUE (only valid when source_transport_id is set)
-- with two partial unique indexes covering each case independently.
ALTER TABLE traceability_consolidation_sources
    DROP CONSTRAINT IF EXISTS traceability_consolidation_sources_consolidation_id_source__key;
DROP INDEX IF EXISTS traceability_consolidation_sources_consolidation_id_source__key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consolidation_sources_transport
    ON traceability_consolidation_sources(consolidation_id, source_transport_id)
    WHERE source_transport_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consolidation_sources_group
    ON traceability_consolidation_sources(consolidation_id, source_group_id)
    WHERE source_group_id IS NOT NULL;

COMMENT ON COLUMN traceability_consolidation_sources.source_group_id IS
    'Source TraceabilityTransactionGroup that contributed weight to this consolidation. Exactly one of source_transport_id / source_group_id is set.';
