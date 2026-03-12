-- Migration: Create ai_audit_document_types table
-- Date: 2026-03-11
-- Description: Document type definitions for AI audit evidence classification

CREATE TABLE IF NOT EXISTS ai_audit_document_types (
    id BIGSERIAL PRIMARY KEY,
    name_en VARCHAR(255) NOT NULL,
    name_th VARCHAR(255) NOT NULL,
    description TEXT,
    extract_list JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_audit_doc_types_active ON ai_audit_document_types(is_active);

COMMENT ON TABLE ai_audit_document_types IS 'Document type definitions for AI audit evidence classification. Each type defines what data can be extracted from that document type.';
COMMENT ON COLUMN ai_audit_document_types.extract_list IS 'JSONB defining extractable fields. Leaf nodes: {"field_name": "description"}. List nodes: {"list_name": {"sub_field": "description"}} for repeated data.';

-- Seed 5 default document types
INSERT INTO ai_audit_document_types (id, name_en, name_th, description, extract_list) VALUES
(1, 'Waste Photos', 'รูปภาพขยะ',
 'Photographs of waste materials at collection or sorting points. Used to verify waste type and condition.',
 '{"waste_type": "Type of waste visible in the image (e.g. plastic, organic, metal, paper, mixed)", "contamination": "Contamination level observed (none, low, medium, high)", "estimated_volume": "Estimated volume or amount of waste visible"}'::jsonb),

(2, 'Daily Weight Recording Form', 'เอกสารกรอกการชั่งน้ำหนักรายวัน',
 'Daily weight recording forms filled by operators. Contains date and material weights recorded throughout the day.',
 '{"date": "Recording date on the form (YYYY-MM-DD)", "weights": {"material_name": "Material name or type as written on the form", "weight_kg": "Weight in kg. If weight is in other units, convert to kg", "origin_name": "Origin or source location name if present"}}'::jsonb),

(3, 'Monthly Weight Recording Form', 'เอกสารกรอกการชั่งน้ำหนักรายเดือน',
 'Monthly summary weight recording forms. Contains aggregated weights per material per month.',
 '{"month": "Recording month (1-12)", "year": "Recording year (YYYY)", "entries": {"date": "Date of entry", "material_name": "Material name or type", "weight_kg": "Weight in kg, convert from other units if needed"}}'::jsonb),

(4, 'Weight Ticket', 'ใบชั่งน้ำหนัก (จากการขายวัสดุ)',
 'Weight tickets issued during material sales or transfers. Contains weighing details including buyer, seller, and material weights.',
 '{"ticket_number": "Ticket or reference number", "date": "Transaction date (YYYY-MM-DD)", "buyer_name": "Buyer or destination company name", "seller_name": "Seller or origin company name", "materials": {"material_name": "Material sub-type name (e.g. PET Bottles, Cardboard)", "weight_kg": "Net weight in kg. Convert to kg if in other units", "price_per_unit": "Price per kg or per unit if shown", "total": "Line total amount for this material"}}'::jsonb),

(5, 'Sales Receipt', 'ใบเสร็จการขาย',
 'Sales receipts or invoices from material sales. Contains itemized material list with quantities, prices, and totals.',
 '{"receipt_number": "Receipt or invoice number", "date": "Receipt date (YYYY-MM-DD)", "seller_name": "Seller or origin company name", "buyer_name": "Buyer or destination company name", "materials": {"material_name": "Material sub-type name (e.g. PET Bottles, HDPE, Aluminum Cans)", "quantity": "Quantity of items if sold by piece", "weight_kg": "Weight in kg. Convert from other units if needed", "price_per_unit": "Unit price per kg or per piece", "total": "Line total amount for this material"}, "grand_total": "Grand total amount on the receipt"}'::jsonb);

-- Reset sequence to avoid conflicts with future inserts
SELECT setval('ai_audit_document_types_id_seq', 5, true);
