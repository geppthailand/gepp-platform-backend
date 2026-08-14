-- ============================================================================
-- Migration: mark a weighing that measures material already reported upstream
-- Date: 2026-08-11
-- Description: A ผู้คัดแยก weighs material OUT of the building's waste room. The
--              same kilograms were already weighed IN from the tenant that
--              produced them, so both weighings create TransactionRecords and
--              any "total waste" that sums records counts the material twice —
--              100 kg of real waste reported as 200 kg.
--
--              The obvious fix — don't create a record for the sorter — does not
--              work: a traceability pile's weight comes only from its records
--              (transaction_record_id -> origin_weight_kg), so the waste-room
--              pile would weigh 0 and there would be nothing to dispatch.
--
--              So the weighing stays and is labelled instead. This flag means
--              "this transaction records MOVEMENT, not generation": the material
--              is real and its traceability leg matters, but its weight must not
--              be added to how much waste the organization produced.
--
--              Why not reuse transaction_method: 'scale_input' is what marks a
--              pile as per-weigh-in (migration 082), so overloading it would
--              silently change that grain; and no report filters on it anyway.
--
--              FALSE for every existing row and for every weighing except a
--              sorter's, so no reported number moves when this ships.
-- ============================================================================

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE;

-- Reports filter this out of tonnage; partial because the flag is FALSE on
-- essentially every row.
CREATE INDEX IF NOT EXISTS idx_transactions_internal_transfer
    ON transactions (organization_id)
    WHERE is_internal_transfer;

COMMENT ON COLUMN transactions.is_internal_transfer IS
    'TRUE = this weighing moved material that was already reported at its origin (e.g. a sorter weighing out of a waste room). Excluded from waste-generated totals; its traceability legs still count. See migration 083.';
