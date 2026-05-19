-- ==========================================
-- Add structured_data JSONB column to esg_organization_data_extraction
-- New compact schema (ver=2) replaces legacy datapoint_matches + refs
-- Old columns kept for backward compatibility
-- ==========================================

ALTER TABLE esg_organization_data_extraction
  ADD COLUMN IF NOT EXISTS structured_data JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_esg_extraction_structured_data
  ON esg_organization_data_extraction USING GIN (structured_data);

COMMENT ON COLUMN esg_organization_data_extraction.structured_data IS
  'Compact extraction: {rows:[{lbl,cat,sub,attrs:[{dp,v,u,c,t,cur,tags}],atm}],tots,dm,add,ver}';
