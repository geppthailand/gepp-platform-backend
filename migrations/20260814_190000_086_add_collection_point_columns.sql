-- ============================================================================
-- Migration: collection points ("ทุกจุดที่มีตาชั่ง คือถัง")
-- Date: 2026-08-14
-- Description: Two columns that let the platform treat a scale station as a
--              TANK — a place with an inflow, an outflow and a balance —
--              instead of a waypoint every shipment must be dragged through.
--
--              transactions.collection_location_id
--                The tank a scale weigh-in was resolved to at approval time
--                (explicit ห้องขยะ binding first, else the nearest ancestor
--                that has a ผู้คัดแยก bound). A ROUTING fact, not proof of
--                arrival: balance terms combine it with the actual transport
--                rows. NULL = not a scale weigh-in, or no tank resolvable —
--                which is every pre-existing row, so nothing changes until
--                the new code stamps it.
--
--              traceability_transport_transactions.delivered_to_collection
--                This hop's destination is a collection point: terminal for
--                the SENDER's scope ("ส่งถึงจุดรวมแล้ว"), neither an outcome
--                (no disposal_method — the tank still has to ship it) nor an
--                unfinished shipment (nobody will ever drag it onward; the
--                tank's own weigh-outs continue the story). The recycling
--                rate uses it to hand the weight over to the tank's outbound
--                records instead of guessing from material category, and the
--                tank balance counts it as inflow.
--
--              ORDERING: this migration MUST run before the Lambda deploy
--              that maps these columns — SQLAlchemy emits mapped columns in
--              every full-entity SELECT, so code-ahead-of-schema 500s every
--              approval and the whole traceability board.
-- ============================================================================

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS collection_location_id BIGINT NULL
    REFERENCES user_locations(id);

ALTER TABLE traceability_transport_transactions
    ADD COLUMN IF NOT EXISTS delivered_to_collection BOOLEAN NOT NULL DEFAULT FALSE;

-- Balance queries walk exactly these two predicates; both are tiny partial sets.
CREATE INDEX IF NOT EXISTS idx_ttt_delivered_dest
    ON traceability_transport_transactions (destination_id)
    WHERE delivered_to_collection;

CREATE INDEX IF NOT EXISTS idx_tx_collection_loc
    ON transactions (collection_location_id)
    WHERE collection_location_id IS NOT NULL;

COMMENT ON COLUMN transactions.collection_location_id IS
    'Tank (collection point) this scale weigh-in was resolved to at approval. Routing fact, not proof of arrival. NULL = non-scale or unresolvable. See migration 086.';
COMMENT ON COLUMN traceability_transport_transactions.delivered_to_collection IS
    'Destination is a collection point: terminal for the sender''s scope, not an outcome. Balance inflow + rate hand-over marker. See migration 086.';

-- ----------------------------------------------------------------------------
-- Backfill — DEV DATA ONLY by construction (production has never run the scale
-- flows; every qualifying row can only exist on dev). Knowingly partial:
-- hopless tank==origin piles left no transport to identify (expected count 0
-- on dev — verify with the SELECTs below before trusting balances for months
-- that predate this migration). Keyed on LIVE waste-room bindings, which is
-- acceptable for dev-created rows only.
-- ----------------------------------------------------------------------------

-- Flag auto-created scale hops that landed on a waste room.
UPDATE traceability_transport_transactions ttt
SET delivered_to_collection = TRUE
FROM traceability_transaction_group g
WHERE ttt.transaction_group_id = g.id
  AND g.source_transaction_id IS NOT NULL
  AND g.is_active = TRUE AND g.deleted_date IS NULL
  AND ttt.is_root = TRUE
  AND ttt.status = 'arrived'
  AND (ttt.disposal_method IS NULL OR ttt.disposal_method = '')
  AND ttt.is_active = TRUE AND ttt.deleted_date IS NULL
  AND ttt.destination_id IN (
      SELECT DISTINCT waste_room_location_id FROM user_locations
      WHERE waste_room_location_id IS NOT NULL AND deleted_date IS NULL
  );

-- Stamp the matching weigh-in transactions (single destination per scale tx).
UPDATE transactions t
SET collection_location_id = sub.destination_id
FROM (
    SELECT DISTINCT g.source_transaction_id AS tx_id, ttt.destination_id
    FROM traceability_transport_transactions ttt
    JOIN traceability_transaction_group g ON ttt.transaction_group_id = g.id
    WHERE ttt.delivered_to_collection = TRUE
      AND g.source_transaction_id IS NOT NULL
) sub
WHERE t.id = sub.tx_id
  AND t.is_internal_transfer IS NOT TRUE
  AND t.collection_location_id IS NULL;

-- Hand-check queries (run manually, expected 0 / 0):
--   SELECT COUNT(*) FROM traceability_transaction_group g
--     JOIN transactions t ON t.id = g.source_transaction_id
--     WHERE g.origin_id = t.collection_location_id
--       AND NOT EXISTS (SELECT 1 FROM traceability_transport_transactions x
--                       WHERE x.transaction_group_id = g.id AND x.deleted_date IS NULL);
--   SELECT COUNT(*) FROM traceability_consolidation_sources s
--     JOIN traceability_transaction_group g ON g.id = s.source_group_id
--     WHERE g.source_transaction_id IS NOT NULL AND s.deleted_date IS NULL;
