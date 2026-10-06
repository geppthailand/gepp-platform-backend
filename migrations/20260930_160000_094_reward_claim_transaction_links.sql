-- ============================================================================
-- Migration: Link older reward claims to the waste transactions they created
-- Date: 2026-09-30
-- Description:
--   1. reward_point_transactions.transaction_id (added in 093) is filled for new claims only.
--      Older staff claims wrote the reward rows and their waste transaction with the SAME
--      timestamp (one `now` in ClaimService), so an exact claimed_date = transaction_date
--      match inside the organization finds the transaction. Only rows with exactly one
--      candidate are linked; nothing ambiguous is guessed. Lets /waste-transactions open the
--      right campaign ledger row ("ระบบรางวัล" badge → search by transaction id).
--   2. Reward-created waste transactions show "ระบบรางวัล" as their creator. Admin-attached
--      claims made before this change stored the admin in transactions.created_by_id; the
--      admin stays recorded on the reward row (reward_point_transactions.created_by_user_location_id).
-- Idempotent: re-running changes nothing.
-- ============================================================================

BEGIN;

UPDATE reward_point_transactions r
SET transaction_id = m.tx_id
FROM (
    SELECT r2.id AS rid, MIN(t.id) AS tx_id, COUNT(t.id) AS candidates
    FROM reward_point_transactions r2
    JOIN transactions t
      ON t.organization_id = r2.organization_id
     AND t.transaction_method = 'reward'
     AND t.transaction_date = r2.claimed_date
     AND t.deleted_date IS NULL
    WHERE r2.transaction_id IS NULL
      AND r2.reference_type = 'claim'
    GROUP BY r2.id
) m
WHERE r.id = m.rid
  AND m.candidates = 1;

UPDATE transactions
SET created_by_id = NULL
WHERE transaction_method = 'reward'
  AND created_by_id IS NOT NULL;

COMMIT;
