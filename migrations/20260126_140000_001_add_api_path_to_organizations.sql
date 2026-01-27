-- Migration: Add api_path column to organizations table
-- Date: 2026-01-26
-- Description: Adds api_path column for custom API routing

-- Add api_path column (unique identifier for API routing)
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS api_path VARCHAR(100) UNIQUE;

-- Create index for fast lookup
CREATE INDEX IF NOT EXISTS idx_organizations_api_path
ON organizations(api_path)
WHERE api_path IS NOT NULL;

-- Add comment
COMMENT ON COLUMN organizations.api_path IS 'Unique identifier for custom API routing. Used in /api/userapi/{api_path}/ endpoints.';

-- Generate random API paths for ALL existing organizations that don't have one
UPDATE organizations 
SET api_path = SUBSTRING(MD5(gen_random_uuid()::text) FROM 1 FOR 32)
WHERE api_path IS NULL AND deleted_date IS NULL;

-- Create function to auto-generate api_path for new organizations
CREATE OR REPLACE FUNCTION generate_organization_api_path()
RETURNS TRIGGER AS $$
DECLARE
    new_api_path TEXT;
    path_exists BOOLEAN;
    max_attempts INTEGER := 10;
    attempt INTEGER := 0;
BEGIN
    -- Only generate if api_path is NULL
    IF NEW.api_path IS NULL THEN
        LOOP
            -- Generate random 32-character string
            new_api_path := SUBSTRING(MD5(gen_random_uuid()::text) FROM 1 FOR 32);
            
            -- Check if this api_path already exists
            SELECT EXISTS(
                SELECT 1 FROM organizations 
                WHERE api_path = new_api_path
            ) INTO path_exists;
            
            -- Exit loop if unique or max attempts reached
            EXIT WHEN NOT path_exists OR attempt >= max_attempts;
            
            attempt := attempt + 1;
        END LOOP;
        
        -- Assign the generated api_path
        NEW.api_path := new_api_path;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-generate api_path on INSERT
DROP TRIGGER IF EXISTS trigger_generate_organization_api_path ON organizations;
CREATE TRIGGER trigger_generate_organization_api_path
    BEFORE INSERT ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION generate_organization_api_path();

