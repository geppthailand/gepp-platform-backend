-- Migration: Create organization_setup table for versioned organization structure
-- Date: 2025-09-18
-- Description: Creates the organization_setup table to store versioned hierarchical structure configurations for organizations

-- Create organization_setup table
CREATE TABLE IF NOT EXISTS organization_setup (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    root_nodes JSONB,
    hub_node JSONB,
    metadata JSONB,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Foreign key constraints
    CONSTRAINT fk_organization_setup_organization_id
        FOREIGN KEY (organization_id) REFERENCES organizations(id)
        ON DELETE CASCADE,

    -- Ensure only one current version per organization
    CONSTRAINT uq_organization_setup_current_version
        UNIQUE (organization_id, is_active)
        DEFERRABLE INITIALLY DEFERRED
);

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_organization_setup_organization_id
    ON organization_setup(organization_id);

CREATE INDEX IF NOT EXISTS idx_organization_setup_is_active
    ON organization_setup(is_active);

CREATE INDEX IF NOT EXISTS idx_organization_setup_version
    ON organization_setup(organization_id, version);

CREATE INDEX IF NOT EXISTS idx_organization_setup_created_date
    ON organization_setup(created_date);

-- Add updated_date trigger
CREATE OR REPLACE FUNCTION update_organization_setup_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_organization_setup_updated_date
    BEFORE UPDATE ON organization_setup
    FOR EACH ROW
    EXECUTE FUNCTION update_organization_setup_updated_date();

-- Add comments for documentation
COMMENT ON TABLE organization_setup IS 'Versioned organization structure setup table storing hierarchical configurations';
COMMENT ON COLUMN organization_setup.organization_id IS 'Reference to the organization this setup belongs to';
COMMENT ON COLUMN organization_setup.version IS 'Version identifier for this configuration (e.g., "1.0", "1.1")';
COMMENT ON COLUMN organization_setup.is_active IS 'Indicates if this is the current active version for the organization';
COMMENT ON COLUMN organization_setup.root_nodes IS 'JSON array containing simplified rootNodes structure with nodeId and children references';
COMMENT ON COLUMN organization_setup.hub_node IS 'JSON object containing hub structure with children array and hubData';
COMMENT ON COLUMN organization_setup.metadata IS 'JSON object containing additional metadata like totalNodes, maxLevel, createdAt, version';

-- Create function to ensure only one active version per organization
CREATE OR REPLACE FUNCTION ensure_single_active_organization_setup()
RETURNS TRIGGER AS $$
BEGIN
    -- If setting is_active to true, deactivate all other versions for this organization
    IF NEW.is_active = TRUE THEN
        UPDATE organization_setup
        SET is_active = FALSE
        WHERE organization_id = NEW.organization_id
          AND id != NEW.id
          AND is_active = TRUE;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ensure_single_active_organization_setup
    BEFORE INSERT OR UPDATE ON organization_setup
    FOR EACH ROW
    WHEN (NEW.is_active = TRUE)
    EXECUTE FUNCTION ensure_single_active_organization_setup();

-- Sample data structure documentation
COMMENT ON COLUMN organization_setup.root_nodes IS 'Expected JSON structure: [{"nodeId": "{user_location.id}", "children": [{"nodeId": "{user_location.id}", "children": [...]}]}]';
COMMENT ON COLUMN organization_setup.hub_node IS 'Expected JSON structure: {"children": [{"nodeId": "{user_location.id}", "hubData": {"traceabilityFlows": {"children": [{"nodeId": "{user_location.id}", "name": "", "children": [...]}]}}}]}';