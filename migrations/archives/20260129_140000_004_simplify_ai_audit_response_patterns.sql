-- Migration: Simplify ai_audit_response_patterns
-- Date: 2026-01-29
-- Description: Simplify condition field to use only code, update priority to default 1000, add new placeholder fields

-- Step 0: Drop any existing indexes on condition column
DO $$
DECLARE
    idx_name text;
BEGIN
    FOR idx_name IN
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'ai_audit_response_patterns'
        AND indexdef LIKE '%condition%'
    LOOP
        EXECUTE 'DROP INDEX IF EXISTS ' || idx_name;
    END LOOP;
END $$;

-- Step 1: Alter condition column to accept simplified format (just code string)
ALTER TABLE ai_audit_response_patterns
ALTER COLUMN condition TYPE VARCHAR(50);

-- Step 2: Update existing records to use simplified condition (just code)
-- This will extract the first condition that looks like code check
UPDATE ai_audit_response_patterns
SET condition = 'cc'
WHERE condition::text LIKE '%"cc"%' OR condition::text LIKE '%correct_category%';

UPDATE ai_audit_response_patterns
SET condition = 'wc'
WHERE condition::text LIKE '%"wc"%' OR condition::text LIKE '%wrong_category%';

UPDATE ai_audit_response_patterns
SET condition = 'ui'
WHERE condition::text LIKE '%"ui"%' OR condition::text LIKE '%unclear_image%';

UPDATE ai_audit_response_patterns
SET condition = 'hc'
WHERE condition::text LIKE '%"hc"%' OR condition::text LIKE '%heavy_contamination%';

UPDATE ai_audit_response_patterns
SET condition = 'lc'
WHERE condition::text LIKE '%"lc"%' OR condition::text LIKE '%light_contamination%';

UPDATE ai_audit_response_patterns
SET condition = 'ncm'
WHERE condition::text LIKE '%"ncm"%' OR condition::text LIKE '%non_complete_material%';

UPDATE ai_audit_response_patterns
SET condition = 'pe'
WHERE condition::text LIKE '%"pe"%' OR condition::text LIKE '%parse_error%';

UPDATE ai_audit_response_patterns
SET condition = 'ie'
WHERE condition::text LIKE '%"ie"%' OR condition::text LIKE '%image_error%';

-- Step 3: Set all priorities to 1000 for existing records
UPDATE ai_audit_response_patterns
SET priority = 1000
WHERE priority != 1000;

-- Step 4: Update default values
ALTER TABLE ai_audit_response_patterns
ALTER COLUMN priority SET DEFAULT 1000;

ALTER TABLE ai_audit_response_patterns
ALTER COLUMN condition SET DEFAULT 'cc';

-- Step 5: Add comment explaining new format
COMMENT ON COLUMN ai_audit_response_patterns.condition IS 'Simplified condition using code only: cc, wc, ui, hc, lc, ncm, pe, ie';
COMMENT ON COLUMN ai_audit_response_patterns.pattern IS 'Response message template with placeholders: {{code}}, {{detect_type}}, {{claimed_type}}, {{warning_items}}';
COMMENT ON COLUMN ai_audit_response_patterns.priority IS 'Priority level - default 1000 (not used for BMA audit)';
