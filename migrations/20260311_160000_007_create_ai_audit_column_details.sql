-- Migration: Create ai_audit_column_details table
-- Date: 2026-03-11
-- Description: Column-level audit check definitions with human-readable descriptions and matching rules

CREATE TABLE IF NOT EXISTS ai_audit_column_details (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    description_en TEXT NOT NULL,
    description_th TEXT NOT NULL,
    check_rules TEXT,
    target_table VARCHAR(100),
    ref_column VARCHAR(100),
    target_column VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_audit_col_details_table ON ai_audit_column_details(table_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_audit_col_details_unique ON ai_audit_column_details(table_name, column_name) WHERE deleted_date IS NULL;

COMMENT ON TABLE ai_audit_column_details IS 'Defines which columns can be verified by AI audit, with human-readable descriptions and matching rules for prompts.';
COMMENT ON COLUMN ai_audit_column_details.check_rules IS 'Matching rule description injected into LLM prompt (e.g. "strict exact match", "fuzzy name matching allowed")';
COMMENT ON COLUMN ai_audit_column_details.target_table IS 'Table to JOIN for resolving the column value (e.g. materials, user_locations)';
COMMENT ON COLUMN ai_audit_column_details.ref_column IS 'Column in target_table to JOIN ON (e.g. id)';
COMMENT ON COLUMN ai_audit_column_details.target_column IS 'Column in target_table to SELECT for display value (e.g. name_en)';

-- Seed: Transaction-level columns
INSERT INTO ai_audit_column_details (table_name, column_name, description_en, description_th, check_rules, target_table, ref_column, target_column) VALUES
('transactions', 'origin_id', 'Origin / Seller Location', 'แหล่งที่มา / สถานที่ต้นทาง', 'Fuzzy name matching allowed. Thai/English name variations are acceptable. Origin and destination names may appear swapped in some documents.', 'user_locations', 'id', 'name_en'),
('transactions', 'destination_ids', 'Destination / Buyer Location', 'ปลายทาง / สถานที่ปลายทาง', 'Fuzzy name matching allowed. Match against buyer/destination names in evidence. May contain multiple destinations.', 'user_locations', 'id', 'name_en'),
('transactions', 'weight_kg', 'Total Weight (kg)', 'น้ำหนักรวม (กก.)', 'Sum of all material weights from evidence should approximately match. Allow 5% tolerance.', NULL, NULL, NULL),
('transactions', 'total_amount', 'Total Amount', 'จำนวนเงินรวม', 'Grand total from evidence should approximately match. Allow 5% tolerance.', NULL, NULL, NULL),
('transactions', 'transaction_date', 'Transaction Date', 'วันที่ทำรายการ', 'Date from evidence should match or be within 3 days of the transaction date.', NULL, NULL, NULL);

-- Seed: Transaction Record-level columns
INSERT INTO ai_audit_column_details (table_name, column_name, description_en, description_th, check_rules, target_table, ref_column, target_column) VALUES
('transaction_records', 'material_id', 'Material Type', 'ประเภทวัสดุ', 'Fuzzy name matching allowed. Names may differ between Thai and English (e.g. "Plastic PET Bottles" ≈ "ขวด PET").', 'materials', 'id', 'name_en'),
('transaction_records', 'origin_weight_kg', 'Weight per Material (kg)', 'น้ำหนักต่อวัสดุ (กก.)', 'Find the weight for this specific material in the evidence. Allow 5% tolerance.', NULL, NULL, NULL),
('transaction_records', 'origin_quantity', 'Quantity', 'จำนวน', 'Match quantity/count for this material if present in evidence. Allow 5% tolerance.', NULL, NULL, NULL),
('transaction_records', 'origin_price_per_unit', 'Price per Unit', 'ราคาต่อหน่วย', 'Match the unit price (per kg or per piece) for this material. This is NOT the line total. Allow 5% tolerance.', NULL, NULL, NULL),
('transaction_records', 'total_amount', 'Line Total Amount', 'จำนวนเงินรายการ', 'Match the line total for this specific material (not the grand total). Allow 5% tolerance.', NULL, NULL, NULL),
('transaction_records', 'transaction_date', 'Record Date', 'วันที่รายการ', 'Date from evidence should match or be within 3 days. Check both transaction-level and record-level evidence dates.', NULL, NULL, NULL),
('transaction_records', 'destination_id', 'Record Destination', 'ปลายทางรายการ', 'Match destination_name against buyer/company names in evidence. Fuzzy matching allowed.', 'user_locations', 'id', 'name_en');

-- Reset sequence
SELECT setval('ai_audit_column_details_id_seq', 12, true);
