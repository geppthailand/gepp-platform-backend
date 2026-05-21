-- 061  Promote consolidation to a first-class entity.
--
-- Why
--   Today a "consolidation" is recognised only by the presence of rows in
--   traceability_consolidation_sources and a sentinel string inside the
--   consolidated transport's meta_data JSON. Anyone reading the schema cold
--   cannot tell that consolidation is a deliberate event distinct from a
--   normal per-location pickup. This migration lifts the relevant fields onto
--   the consolidation header and adds an explicit source_kind discriminator
--   to the sources table.
--
-- Changes
--   traceability_consolidations
--     + consolidation_point_id   FK → user_locations.id  (where the batch lands)
--     + batch_name               varchar(255)            (user-supplied label)
--     + status                   varchar(20)             ('active' | 'reverted')
--
--   traceability_consolidation_sources
--     + source_kind              varchar(20)             ('transport' | 'group')
--                                derived from existing data, then NOT NULL
--
-- Backward compatibility
--   Reads against the old shape still work: consolidation_point_id and
--   batch_name are populated for new rows; old rows get back-filled from
--   their consolidated transport's destination + meta_data.batch_origin_name.

BEGIN;

------------------------------------------------------------------
-- traceability_consolidations
------------------------------------------------------------------

ALTER TABLE traceability_consolidations
    ADD COLUMN IF NOT EXISTS consolidation_point_id BIGINT
        REFERENCES user_locations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS batch_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';

-- Back-fill consolidation_point_id from the consolidated transport's destination
UPDATE traceability_consolidations c
   SET consolidation_point_id = t.destination_id
  FROM traceability_transport_transactions t
 WHERE t.id = c.consolidated_transport_id
   AND c.consolidation_point_id IS NULL;

-- Back-fill batch_name from the consolidated transport's meta_data.batch_origin_name
UPDATE traceability_consolidations c
   SET batch_name = t.meta_data->>'batch_origin_name'
  FROM traceability_transport_transactions t
 WHERE t.id = c.consolidated_transport_id
   AND c.batch_name IS NULL
   AND t.meta_data ? 'batch_origin_name';

-- Mark soft-deleted rows as reverted so the status reflects reality
UPDATE traceability_consolidations
   SET status = 'reverted'
 WHERE deleted_date IS NOT NULL
   AND status <> 'reverted';

CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_point
    ON traceability_consolidations(consolidation_point_id);
CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_status
    ON traceability_consolidations(status);

COMMENT ON COLUMN traceability_consolidations.consolidation_point_id IS
    'Explicit consolidation point (user_location). Mirrors the destination of consolidated_transport but is denormalised here so the schema clearly identifies the merge target without joining transports.';
COMMENT ON COLUMN traceability_consolidations.batch_name IS
    'User-supplied label for the merged batch. Surfaces in the Summary path and Item Details.';
COMMENT ON COLUMN traceability_consolidations.status IS
    'Lifecycle: active = in effect, reverted = the consolidation event was undone.';

------------------------------------------------------------------
-- traceability_consolidation_sources
------------------------------------------------------------------

ALTER TABLE traceability_consolidation_sources
    ADD COLUMN IF NOT EXISTS source_kind VARCHAR(20);

-- Back-fill source_kind from which of the two FKs is populated
UPDATE traceability_consolidation_sources
   SET source_kind = CASE
        WHEN source_transport_id IS NOT NULL THEN 'transport'
        WHEN source_group_id     IS NOT NULL THEN 'group'
        ELSE 'transport'
   END
 WHERE source_kind IS NULL;

ALTER TABLE traceability_consolidation_sources
    ALTER COLUMN source_kind SET NOT NULL;

-- Enforce the discriminator: source_kind must match which FK is set.
ALTER TABLE traceability_consolidation_sources
    DROP CONSTRAINT IF EXISTS chk_consolidation_source_kind;
ALTER TABLE traceability_consolidation_sources
    ADD CONSTRAINT chk_consolidation_source_kind CHECK (
        (source_kind = 'transport' AND source_transport_id IS NOT NULL AND source_group_id     IS NULL)
     OR (source_kind = 'group'     AND source_group_id     IS NOT NULL AND source_transport_id IS NULL)
    );

CREATE INDEX IF NOT EXISTS idx_consolidation_sources_kind
    ON traceability_consolidation_sources(source_kind);

COMMENT ON COLUMN traceability_consolidation_sources.source_kind IS
    'Explicit discriminator. transport = pre-arrived TransportTransaction; group = raw transaction group from the origin column.';

COMMIT;
