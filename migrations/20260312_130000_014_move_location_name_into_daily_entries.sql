-- Migration: Move location_name inside daily_entries for Monthly Weight Recording Form
-- Date: 2026-03-12
-- Description: location_name should be per-entry (per day/material/location) not per-document

UPDATE ai_audit_document_types
SET extract_list = '{
  "year": "Recording year (YYYY). Look in header, title, or date fields.",
  "month": "Recording month (1-12 integer). Look in header, title, or date fields.",
  "month_name": "Month name as written on the document (e.g. กุมภาพันธ์, มีนาคม)",
  "daily_entries": {
    "day": "Day of month (1-31 integer)",
    "weight_kg": "Weight value in kg for that day and material. Extract the exact number as shown. Convert to kg if in other units.",
    "material_name": "Material/waste type column name as written (e.g. ขยะเศษอาหาร/ขยะอินทรีย์, ขยะทั่วไป, ขยะอิเล็กทรอนิกส์)",
    "location_name": "Location/building/origin for this entry. Look for rows labeled อาคาร (building), สถานที่ (location), สาขา (branch), or checkboxes like [☐นานาเหนือ ☑สุขุมวิท]. Also check sheet/tab name, header area, or cells next to labels like อาคาร:, Building:. If the document has one location for all entries, repeat the same value for every entry. Do NOT leave null if any location info exists in the document."
  },
  "monthly_totals": {
    "material_name": "Material/waste type name",
    "total_weight_kg": "Monthly total weight in kg for this material"
  }
}'::jsonb,
    updated_date = NOW()
WHERE id = 3;
