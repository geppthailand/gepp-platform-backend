-- ================================================================
-- Debug Audit Query - ตรวจสอบผล AI Audit จาก ai_audit_note
-- ================================================================

-- 1. ดูข้อมูล audit note ทั้งหมดของ transaction ล่าสุด
SELECT
    id,
    ext_id_1,
    ext_id_2,
    ai_audit_status,
    ai_audit_note::jsonb->'household_id' as household_id,
    ai_audit_note::jsonb->'step_1' as step_1_coverage,
    ai_audit_note::jsonb->'step_2' as step_2_materials,
    created_date
FROM transactions
WHERE organization_id = 8
  AND deleted_date IS NULL
  AND ai_audit_note IS NOT NULL
ORDER BY created_date DESC
LIMIT 10;

-- 2. ดูข้อมูล debug ของ material แต่ละประเภท
SELECT
    t.id as transaction_id,
    t.ext_id_1,
    t.ext_id_2,
    t.ai_audit_note::jsonb->'household_id' as household_id,
    material_key,
    (material_data->>'ct')::int as claimed_type_id,
    material_data->>'as' as audit_status,
    material_data->'_debug' as debug_info
FROM transactions t,
LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
WHERE t.organization_id = 8
  AND t.deleted_date IS NULL
  AND t.ai_audit_note IS NOT NULL
ORDER BY t.created_date DESC
LIMIT 50;

-- 3. หา transaction ที่มี visibility_status = "opaque" (มองไม่เห็น)
SELECT
    t.id as transaction_id,
    t.ext_id_1,
    t.ext_id_2,
    t.ai_audit_note::jsonb->'household_id' as household_id,
    material_key,
    material_data->'_debug'->>'visibility_status' as visibility_status,
    material_data->'_debug'->>'visibility_reason' as reason,
    material_data->'_debug'->>'visibility_raw' as raw_response
FROM transactions t,
LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
WHERE t.organization_id = 8
  AND t.deleted_date IS NULL
  AND t.ai_audit_note IS NOT NULL
  AND material_data->'_debug'->>'visibility_status' = 'opaque'
ORDER BY t.created_date DESC
LIMIT 20;

-- 4. หา transaction ตาม household_id เฉพาะ
SELECT
    t.id as transaction_id,
    t.ext_id_1,
    t.ext_id_2,
    t.ai_audit_note::jsonb->'household_id' as household_id,
    t.ai_audit_status,
    t.ai_audit_note::jsonb->'step_1' as coverage_check,
    jsonb_pretty(t.ai_audit_note::jsonb->'step_2') as materials_audit
FROM transactions t
WHERE t.organization_id = 8
  AND t.deleted_date IS NULL
  AND t.ai_audit_note::jsonb->>'household_id' = 'YOUR_HOUSEHOLD_ID_HERE'
ORDER BY t.created_date DESC;

-- 5. สรุปสถิติการ audit ทั้งหมด
SELECT
    ai_audit_status,
    COUNT(*) as transaction_count,
    COUNT(DISTINCT ext_id_2) as unique_households
FROM transactions
WHERE organization_id = 8
  AND deleted_date IS NULL
  AND ai_audit_note IS NOT NULL
GROUP BY ai_audit_status
ORDER BY transaction_count DESC;

-- 6. หาภาพที่ถูก predict ผิด (claimed vs detected type ไม่ตรงกัน)
SELECT
    t.id as transaction_id,
    t.ext_id_2 as household_id,
    material_key,
    (material_data->>'ct')::int as claimed_type_id,
    material_data->'_debug'->'decision'->>'dt' as detected_type_id,
    material_data->'_debug'->'decision'->>'code' as decision_code,
    material_data->'_debug'->>'visibility_status' as visibility,
    material_data->'_debug'->'classify_parsed' as ai_classification
FROM transactions t,
LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
WHERE t.organization_id = 8
  AND t.deleted_date IS NULL
  AND t.ai_audit_note IS NOT NULL
  AND (material_data->>'ct')::int != (material_data->'_debug'->'decision'->>'dt')::int
  AND (material_data->'_debug'->'decision'->>'dt') != '0'  -- Exclude errors
ORDER BY t.created_date DESC
LIMIT 20;

-- 7. ดู raw response จาก AI สำหรับ material ที่เลือก
SELECT
    t.id as transaction_id,
    t.ext_id_2 as household_id,
    material_key,
    material_data->'_debug'->>'claimed_type' as claimed_type,
    material_data->'_debug'->>'visibility_status' as visibility_status,
    material_data->'_debug'->>'visibility_raw' as visibility_raw_response,
    material_data->'_debug'->>'classify_raw' as classify_raw_response,
    material_data->'_debug'->'classify_parsed' as classify_parsed,
    material_data->'_debug'->'decision' as final_decision
FROM transactions t,
LATERAL jsonb_each(t.ai_audit_note::jsonb->'step_2') AS mat(material_key, material_data)
WHERE t.organization_id = 8
  AND t.deleted_date IS NULL
  AND t.id = YOUR_TRANSACTION_ID_HERE  -- ใส่ transaction_id ที่ต้องการดู
ORDER BY material_key;
