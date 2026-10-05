-- ============================================================================
-- Migration: Packaging catalogue (per brand) + GEPP Rewards packaging items
-- Date: 2026-10-04
-- Description:
--   A packaging item (e.g. "Singha drinking water 600 ml") converts to one or more
--   materials by weight per piece (e.g. PET 0.070 kg + HDPE 0.001 kg). GEPP manages the
--   catalogue in the back office (/v3-materials → Packaging tab); reward campaigns can
--   offer a packaging item so members claim by PIECES instead of weighing.
--
--   packaging_brands, packagings, packaging_materials   catalogue (global; organization_id
--                                                        reserved for org-owned items later)
--   reward_activity_materials.packaging_id              type = 'packaging' items
--   reward_point_transactions.quantity / quantity_unit  pieces claimed; `value` stays in KG
--                                                        (every weight aggregate sums value)
--   reward_point_transaction_components                 kg per material of a packaging claim,
--                                                        snapshotted at claim time (GHG, targets)
--   reward_claim_requests.quantity / quantity_unit / components   same for pending self-claims
--   reward_campaign_targets.target_unit                 adds 'pcs'
--
--   No FK from components to reward_point_transactions / transaction_records: the ledger row
--   of an approved self-claim is created inside a before_flush hook with a pre-assigned id,
--   and without an ORM relationship the unit of work does not order those INSERTs.
-- Idempotent.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS packaging_brands (
    id            BIGSERIAL PRIMARY KEY,
    name_th       VARCHAR(255) NOT NULL,
    name_en       VARCHAR(255),
    logo_file_id  BIGINT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_date  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date  TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date  TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_packaging_brands_name
    ON packaging_brands (lower(name_th)) WHERE deleted_date IS NULL;

CREATE TABLE IF NOT EXISTS packagings (
    id               BIGSERIAL PRIMARY KEY,
    brand_id         BIGINT REFERENCES packaging_brands(id),
    name_th          VARCHAR(255) NOT NULL,
    name_en          VARCHAR(255),
    size_label       VARCHAR(64),
    volume_ml        NUMERIC(10, 2),
    barcode          VARCHAR(64),
    packaging_type   VARCHAR(32) NOT NULL DEFAULT 'other',
    image_file_id    BIGINT,
    organization_id  BIGINT REFERENCES organizations(id),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date     TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date     TIMESTAMPTZ,
    CONSTRAINT packagings_type_check
        CHECK (packaging_type IN ('bottle', 'can', 'carton', 'pouch', 'cup', 'box', 'other'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_packagings_identity
    ON packagings (COALESCE(brand_id, 0), lower(name_th), COALESCE(lower(size_label), ''))
    WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS ix_packagings_brand ON packagings (brand_id);

CREATE TABLE IF NOT EXISTS packaging_materials (
    id            BIGSERIAL PRIMARY KEY,
    packaging_id  BIGINT NOT NULL REFERENCES packagings(id) ON DELETE CASCADE,
    material_id   BIGINT NOT NULL REFERENCES materials(id),
    weight_kg     NUMERIC(12, 6) NOT NULL CHECK (weight_kg > 0),
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_date  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date  TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date  TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_packaging_materials
    ON packaging_materials (packaging_id, material_id) WHERE deleted_date IS NULL;

ALTER TABLE reward_activity_materials
    ADD COLUMN IF NOT EXISTS packaging_id BIGINT REFERENCES packagings(id);

ALTER TABLE reward_point_transactions
    ADD COLUMN IF NOT EXISTS quantity NUMERIC(14, 3),
    ADD COLUMN IF NOT EXISTS quantity_unit VARCHAR(16);

CREATE TABLE IF NOT EXISTS reward_point_transaction_components (
    id                           BIGSERIAL PRIMARY KEY,
    organization_id              BIGINT NOT NULL REFERENCES organizations(id),
    reward_point_transaction_id  BIGINT NOT NULL,
    material_id                  BIGINT NOT NULL REFERENCES materials(id),
    weight_kg                    NUMERIC(14, 6) NOT NULL,
    transaction_record_id        BIGINT,
    is_active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_date                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date                 TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date                 TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_rpt_components_rpt ON reward_point_transaction_components (reward_point_transaction_id);
CREATE INDEX IF NOT EXISTS ix_rpt_components_material ON reward_point_transaction_components (material_id);

ALTER TABLE reward_claim_requests
    ADD COLUMN IF NOT EXISTS quantity NUMERIC(14, 3),
    ADD COLUMN IF NOT EXISTS quantity_unit VARCHAR(16),
    ADD COLUMN IF NOT EXISTS components JSONB;

ALTER TABLE reward_campaign_targets DROP CONSTRAINT IF EXISTS reward_campaign_targets_unit_check;
ALTER TABLE reward_campaign_targets ADD CONSTRAINT reward_campaign_targets_unit_check
    CHECK (target_unit IN ('kg', 'times', 'pcs'));

COMMIT;
