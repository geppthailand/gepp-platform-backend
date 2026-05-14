-- Add max_org_structure_nodes column to organizations
-- Limits the number of nodes an organization can create in the org chart
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS max_org_structure_nodes INTEGER NOT NULL DEFAULT 50;
