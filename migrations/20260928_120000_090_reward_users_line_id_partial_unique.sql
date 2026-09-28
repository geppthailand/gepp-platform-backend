-- Migration 090 — reward_users.line_user_id: unique among LIVE rows only
-- Description: Make the reward_users LINE-id uniqueness partial on deleted_date IS NULL so a soft-deleted member can register again
-- Date: 2026-09-28
--
-- Context: deleting a rewards member is a SOFT delete (`reward_users.deleted_date`
-- is stamped; the row stays for point/redemption history). But the uniqueness on
-- `line_user_id` was a plain table-wide UNIQUE:
--
--   reward_users_line_user_id_key UNIQUE (line_user_id)
--
-- `PublicRewardService.register_user` looks the member up with
-- `deleted_date IS NULL`, finds nothing for a deleted member, and INSERTs — which
-- collides with the tombstone row and returns a 500. The practical effect: once an
-- admin removes a member, that LINE account can never use GEPP Rewards again. It
-- cannot log in, cannot re-register, and the error says nothing useful.
--
-- The fix is to scope the constraint to live rows, which is what every other
-- "unique per member" rule in this table already does — `idx_reward_users_phone`
-- is partial on `deleted_date IS NULL` for exactly this reason. After this, a
-- re-registering member gets a FRESH row starting at zero points, and the
-- tombstone keeps its `line_user_id` so the old history stays attributable and an
-- accidental delete can still be traced.
--
-- Rejected: reviving the tombstone (clearing `deleted_date`) on re-register. It
-- needs no migration, but it silently hands back the balance an admin chose to
-- remove, and it contradicts `_ensure_membership`, which deliberately refuses to
-- reactivate a membership an admin deactivated. Deletion must not be undoable by
-- the deleted party simply re-scanning a QR.
--
-- Rejected: NULLing `line_user_id` on the tombstone at delete time. Also avoids a
-- migration, but it destroys the only link between old history and the person, so
-- a mistaken delete becomes unrecoverable.
--
-- Safe to re-run, and strictly weaker than what it replaces: every row set the old
-- constraint accepted is still accepted. `whatsapp_user_id` / `wechat_user_id` keep
-- their table-wide UNIQUE — neither channel is in use yet, so there is nothing to
-- fix and no data to validate the new shape against.

BEGIN;

ALTER TABLE reward_users
    DROP CONSTRAINT IF EXISTS reward_users_line_user_id_key;

-- Belt and braces: on databases where the same rule was created as a bare index
-- rather than a constraint, DROP CONSTRAINT above is a no-op.
DROP INDEX IF EXISTS reward_users_line_user_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_reward_users_line_user_id_live
    ON reward_users (line_user_id)
    WHERE line_user_id IS NOT NULL AND deleted_date IS NULL;

COMMENT ON INDEX uq_reward_users_line_user_id_live IS
    'One LIVE member per LINE account. Partial on deleted_date so a soft-deleted '
    'member can register again as a new row (see migration 090).';

COMMIT;
