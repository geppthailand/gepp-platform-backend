-- Migration: Cleanup ai_audit_column_details
-- Date: 2026-03-11
-- Description: Remove ALL transaction-level columns. Move origin/destination to record level.
--              All checks are now at transaction_records level only.

-- Remove ALL transaction-level columns
DELETE FROM ai_audit_column_details WHERE table_name = 'transactions';

-- Remove old record-level destination_id (replaced with origin_id and destination_id below)
DELETE FROM ai_audit_column_details WHERE table_name = 'transaction_records' AND column_name = 'destination_id';

-- Add origin_id at record level (moved from transactions)
INSERT INTO ai_audit_column_details (table_name, column_name, description_en, description_th, check_rules, target_table, ref_column, target_column)
VALUES (
    'transaction_records', 'origin_id',
    'Origin / Seller Location',
    'แหล่งที่มา / ต้นทางของวัสดุ',
    'The origin_id comes from the parent transaction (transactions.origin_id). Query user_locations by this id to get name_en. Fuzzy match against seller/origin names found in evidence documents. Thai/English name variations are acceptable. Origin and destination names may appear swapped in some documents — allow this ambiguity if names match.',
    'user_locations', 'id', 'name_en'
);

-- Add destination_id at record level (from transactions.destination_ids[index])
INSERT INTO ai_audit_column_details (table_name, column_name, description_en, description_th, check_rules, target_table, ref_column, target_column)
VALUES (
    'transaction_records', 'destination_id',
    'Destination / Buyer Location',
    'ปลายทาง / สถานที่ส่งวัสดุไป',
    'Each record''s destination comes from transactions.destination_ids where the index corresponds to the record position. Query user_locations by destination_id to get name_en. Match against buyer/destination/company names found in evidence (e.g. receipts, invoices). Each material may have a different destination. Origin and destination names may be swapped in some documents — allow this ambiguity if names match.',
    'user_locations', 'id', 'name_en'
);

-- Update existing record-level descriptions with richer check_rules
UPDATE ai_audit_column_details SET
    description_th = 'ประเภทวัสดุ',
    check_rules = 'Query materials by material_id to get name_en. Fuzzy match this material name against material names found in extracted evidence data. Names may differ between Thai and English (e.g. "Plastic PET Bottles" ≈ "ขวด PET", "Cardboard" ≈ "กระดาษลัง"). Search through ALL items in materials lists from receipts/tickets to find the matching material.'
WHERE table_name = 'transaction_records' AND column_name = 'material_id';

UPDATE ai_audit_column_details SET
    description_th = 'น้ำหนักของวัสดุ (กก.)',
    check_rules = 'Find the weight for this specific material in the evidence. The weight should already be converted to kg during the extraction step. Match against the extracted weight for this material. Allow 5% tolerance.'
WHERE table_name = 'transaction_records' AND column_name = 'origin_weight_kg';

UPDATE ai_audit_column_details SET
    description_th = 'จำนวนชิ้นของวัสดุ',
    check_rules = 'Some materials are sold by piece/unit rather than by weight. Match the quantity/count for this material if present in evidence. Allow 5% tolerance.'
WHERE table_name = 'transaction_records' AND column_name = 'origin_quantity';

UPDATE ai_audit_column_details SET
    description_th = 'ราคาต่อหน่วย (ต่อกิโลหรือต่อชิ้น)',
    check_rules = 'Match the unit price per kg or per piece for this material. This is NOT the line total or grand total — it is the price per unit. Allow 5% tolerance.'
WHERE table_name = 'transaction_records' AND column_name = 'origin_price_per_unit';

UPDATE ai_audit_column_details SET
    description_th = 'ราคาขายรวมของวัสดุนี้',
    check_rules = 'Match the line total for this specific material (weight × price_per_unit). This is NOT the grand total of the entire receipt — it is the subtotal for this material only. Commonly found in receipts and invoices. Allow 5% tolerance.'
WHERE table_name = 'transaction_records' AND column_name = 'total_amount';

UPDATE ai_audit_column_details SET
    description_th = 'วันที่ส่งวัสดุ',
    check_rules = 'Each transaction_record may have its own transaction_date representing the delivery date for that material. Evidence documents may be attached per-record or at the transaction level. If per-record evidence exists, match its date. Otherwise, fall back to transaction-level evidence date which is shared across all materials. Allow 3 days tolerance.'
WHERE table_name = 'transaction_records' AND column_name = 'transaction_date';
