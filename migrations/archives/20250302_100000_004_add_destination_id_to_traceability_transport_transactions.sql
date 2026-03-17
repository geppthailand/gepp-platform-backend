-- Migration: Add destination_id to traceability_transport_transactions
-- Date: 2025-03-02
-- Description: Destination user_location for the transport (where materials are delivered)

ALTER TABLE traceability_transport_transactions
ADD COLUMN IF NOT EXISTS destination_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_traceability_transport_transactions_destination_id ON traceability_transport_transactions(destination_id);

COMMENT ON COLUMN traceability_transport_transactions.destination_id IS 'Destination user_location id (where materials are delivered)';
