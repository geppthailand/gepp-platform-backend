-- Shared User Locations — Cross-organization location data sharing.
-- Company A shares one of its locations (source_user_location_id) to Company B
-- (resolved from target_email's owned org). B sees that location's data as read-only,
-- bounded by [start_date, end_date], via a VIRTUAL node in B's organization_setup.root_nodes.
-- All idempotent (IF NOT EXISTS / guarded constraint creation).

-- ─── shared_user_locations ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shared_user_locations (
    id                       BIGSERIAL    PRIMARY KEY,
    -- Sharer (Org A) and the specific location being shared.
    source_organization_id   BIGINT       NOT NULL REFERENCES organizations(id),
    source_user_location_id  BIGINT       NOT NULL REFERENCES user_locations(id),
    -- Recipient org (Org B), resolved from target_email's owned org; NULL when unresolved.
    target_organization_id   BIGINT       REFERENCES organizations(id),
    name                     VARCHAR(255),
    description              TEXT,
    target_email             VARCHAR(255) NOT NULL,
    -- Internal identifier (secrets.token_urlsafe(16)); not a click-to-accept token.
    share_code               VARCHAR(64)  NOT NULL,
    -- User on/off switch (from BaseModel semantics).
    is_active                BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Share-level expiry, distinct from the data window below.
    expired_date             TIMESTAMPTZ,
    -- SILENT compute/query flag: the single source of truth for "may this share's data
    -- actually be computed/surfaced". TRUE only when target_email resolves to an org owner
    -- and the share has not been rejected. Never surfaced as an error to the sharer.
    is_valid                 BOOLEAN      NOT NULL DEFAULT FALSE,
    -- Recipient (target owner) rejected the share by removing the node. Also forces is_valid=false.
    is_rejected              BOOLEAN      NOT NULL DEFAULT FALSE,
    -- Placement in the TARGET org's chart: the real user_location id this shared node hangs
    -- under, set when the recipient drags it in. NULL = not yet placed (unplaced tray item).
    -- Shared nodes are NEVER stored in organization_setup.root_nodes (they are not real
    -- locations); placement lives here so the fragile tree-save pipeline never touches them.
    placed_parent_node_id    BIGINT       REFERENCES user_locations(id),
    -- Data window: only source transactions within [start_date, end_date] are shared.
    start_date               TIMESTAMPTZ,
    end_date                 TIMESTAMPTZ,
    created_date             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_date             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_date             TIMESTAMPTZ
);

-- Unique share_code (guarded so the migration is re-runnable).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'shared_user_locations_share_code_unique'
           AND conrelid = 'shared_user_locations'::regclass
    ) THEN
        ALTER TABLE shared_user_locations
            ADD CONSTRAINT shared_user_locations_share_code_unique UNIQUE (share_code);
    END IF;
END $$;

-- Lookups: shares A created (list per source location), incoming for B, reciprocal-cycle check.
CREATE INDEX IF NOT EXISTS idx_shared_user_locations_source_org
    ON shared_user_locations (source_organization_id)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_shared_user_locations_source_location
    ON shared_user_locations (source_user_location_id)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_shared_user_locations_target_org
    ON shared_user_locations (target_organization_id)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_shared_user_locations_target_email
    ON shared_user_locations (target_email);

-- Placed shares in a target org (drives the canvas overlay + transaction injection).
CREATE INDEX IF NOT EXISTS idx_shared_user_locations_placed
    ON shared_user_locations (target_organization_id, placed_parent_node_id)
    WHERE deleted_date IS NULL AND placed_parent_node_id IS NOT NULL;
