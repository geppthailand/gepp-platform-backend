-- Migration: Add traceability consolidation + per-transport attachment tables
-- Date: 2026-05-19
-- Description: Supports merging N "arrived" transport transactions into a single
--              onward consolidated transport, with per-transport file attachments.
--
-- Design goals
--   • traceability_consolidations            : header (one row per consolidation event)
--   • traceability_consolidation_sources     : N→1 join (source transports → consolidation)
--   • traceability_transport_files           : per-transport file attachment join
--
-- The new consolidated transport is itself a row in
-- traceability_transport_transactions whose id is referenced by
-- consolidated_transport_id. The existing single-source pickup flow stays
-- backward compatible because these tables are additive only.

-- ============================================================
-- 1) traceability_consolidations (header)
-- ============================================================
CREATE TABLE IF NOT EXISTS traceability_consolidations (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    consolidated_transport_id BIGINT NOT NULL REFERENCES traceability_transport_transactions(id) ON DELETE CASCADE,
    material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
    total_weight NUMERIC NOT NULL,
    created_by BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_consolidated_transport ON traceability_consolidations(consolidated_transport_id);
CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_org ON traceability_consolidations(organization_id);
CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_material ON traceability_consolidations(material_id);
CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_is_active ON traceability_consolidations(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_traceability_consolidations_deleted ON traceability_consolidations(deleted_date) WHERE deleted_date IS NULL;

COMMENT ON TABLE traceability_consolidations IS 'Header for a consolidation event: N source TransportTransactions merged into 1 consolidated TransportTransaction.';
COMMENT ON COLUMN traceability_consolidations.consolidated_transport_id IS 'The new TransportTransaction row produced by this consolidation.';
COMMENT ON COLUMN traceability_consolidations.material_id IS 'Material being consolidated (typically one consolidation per material).';
COMMENT ON COLUMN traceability_consolidations.total_weight IS 'Sum of contributed_weight across all source rows; cached for fast reads.';

-- ============================================================
-- 2) traceability_consolidation_sources (N→1)
-- ============================================================
CREATE TABLE IF NOT EXISTS traceability_consolidation_sources (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    consolidation_id BIGINT NOT NULL REFERENCES traceability_consolidations(id) ON DELETE CASCADE,
    source_transport_id BIGINT NOT NULL REFERENCES traceability_transport_transactions(id) ON DELETE CASCADE,
    contributed_weight NUMERIC NOT NULL,
    ordering SMALLINT DEFAULT 0,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    UNIQUE(consolidation_id, source_transport_id)
);

CREATE INDEX IF NOT EXISTS idx_consolidation_sources_source ON traceability_consolidation_sources(source_transport_id);
CREATE INDEX IF NOT EXISTS idx_consolidation_sources_consolidation ON traceability_consolidation_sources(consolidation_id);
CREATE INDEX IF NOT EXISTS idx_consolidation_sources_is_active ON traceability_consolidation_sources(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_consolidation_sources_deleted ON traceability_consolidation_sources(deleted_date) WHERE deleted_date IS NULL;

COMMENT ON TABLE traceability_consolidation_sources IS 'Each row = one source TransportTransaction contributing to a consolidation.';
COMMENT ON COLUMN traceability_consolidation_sources.source_transport_id IS 'The arrived transport whose weight is being merged into the consolidation.';
COMMENT ON COLUMN traceability_consolidation_sources.contributed_weight IS 'Weight (kg) this source contributes; may be < source.weight if partial.';
COMMENT ON COLUMN traceability_consolidation_sources.ordering IS 'Stable display order for UI rendering.';

-- ============================================================
-- 3) traceability_transport_files (per-transport attachment join)
-- ============================================================
CREATE TABLE IF NOT EXISTS traceability_transport_files (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    transport_transaction_id BIGINT NOT NULL REFERENCES traceability_transport_transactions(id) ON DELETE CASCADE,
    file_id BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    ordering SMALLINT DEFAULT 0,
    uploaded_by BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    UNIQUE(transport_transaction_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_transport_files_transport ON traceability_transport_files(transport_transaction_id);
CREATE INDEX IF NOT EXISTS idx_transport_files_file ON traceability_transport_files(file_id);
CREATE INDEX IF NOT EXISTS idx_transport_files_is_active ON traceability_transport_files(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_transport_files_deleted ON traceability_transport_files(deleted_date) WHERE deleted_date IS NULL;

COMMENT ON TABLE traceability_transport_files IS 'Per-TransportTransaction file attachments (waste manifests, photos, etc.). Shared by consolidation flow and normal pickup flow.';
COMMENT ON COLUMN traceability_transport_files.transport_transaction_id IS 'Owning transport transaction.';
COMMENT ON COLUMN traceability_transport_files.file_id IS 'Reference into files table (the actual S3-backed file row).';
COMMENT ON COLUMN traceability_transport_files.ordering IS 'Stable display order in the attachment list UI.';
