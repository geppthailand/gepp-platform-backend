-- Audit trail for reward_users account merges.
-- A merge happens when a walk-in (phone-only) member and a LINE member turn out to
-- be the same person: the victim's point transactions, redemptions, catalog ownership,
-- and org memberships are re-pointed to the survivor, then the victim is soft-deleted.
-- There is NO automatic unmerge — this table records exactly what moved so a merge can
-- be traced (and reversed by hand) if it was ever done in error.

CREATE TABLE IF NOT EXISTS reward_user_merges (
    id                    BIGSERIAL PRIMARY KEY,
    survivor_user_id      BIGINT NOT NULL REFERENCES reward_users(id),
    victim_user_id        BIGINT NOT NULL REFERENCES reward_users(id),
    organization_id       BIGINT,                 -- context org for admin/manual merges (nullable)
    merge_type            VARCHAR(20) NOT NULL,    -- auto_phone | manual_admin
    moved_counts          JSONB,                   -- {"point_tx":n,"redemptions":n,"memberships":n,"catalog":n}
    performed_by_user_id  BIGINT,                  -- platform users.id (admin manual merge)
    performed_by_staff_id BIGINT,                  -- organization_reward_users.id (if relevant)
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_date          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date          TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reward_user_merges_survivor ON reward_user_merges(survivor_user_id);
CREATE INDEX IF NOT EXISTS idx_reward_user_merges_victim   ON reward_user_merges(victim_user_id);

COMMENT ON TABLE reward_user_merges IS
    'Audit log of reward_users merges (walk-in -> LINE auto-merge and admin manual merges). No auto-unmerge.';
