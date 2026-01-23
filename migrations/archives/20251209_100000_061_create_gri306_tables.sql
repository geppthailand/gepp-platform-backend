-- Migration: Create GRI 306 tables
-- Description: Create tables for GRI 306 waste reporting standards (306-1, 306-2, 306-3) and export history
-- Date: 2025-12-09 10:00:00

-- Create gri306_1 table
CREATE TABLE IF NOT EXISTS gri306_1 (
    id BIGSERIAL PRIMARY KEY,
    is_active boolean DEFAULT true,
    input_material varchar(255),
    activity varchar(255),
    output_material bigint REFERENCES materials(id),
    output_category bigint REFERENCES material_categories(id),
    method varchar(255),
    onsite boolean,
    weight numeric,
    description text,
    record_year varchar(20),
    organization bigint REFERENCES organizations(id),
    created_by bigint REFERENCES user_locations(id),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    deleted_date timestamp with time zone
);

-- Indexes for gri306_1
CREATE INDEX IF NOT EXISTS idx_gri306_1_output_material ON gri306_1(output_material);
CREATE INDEX IF NOT EXISTS idx_gri306_1_output_category ON gri306_1(output_category);
CREATE INDEX IF NOT EXISTS idx_gri306_1_organization ON gri306_1(organization);
CREATE INDEX IF NOT EXISTS idx_gri306_1_created_by ON gri306_1(created_by);

-- Comments for gri306_1
COMMENT ON TABLE gri306_1 IS 'Stores GRI 306-1 data: Waste generation and significant waste-related impacts';
COMMENT ON COLUMN gri306_1.input_material IS 'Description of input material';
COMMENT ON COLUMN gri306_1.activity IS 'Activity leading to waste generation';
COMMENT ON COLUMN gri306_1.output_material IS 'Reference to the generated waste material';
COMMENT ON COLUMN gri306_1.output_category IS 'Reference to the waste material category';
COMMENT ON COLUMN gri306_1.method IS 'Method of waste generation or handling';
COMMENT ON COLUMN gri306_1.onsite IS 'Whether the waste was generated onsite';
COMMENT ON COLUMN gri306_1.weight IS 'Weight of the waste generated';
COMMENT ON COLUMN gri306_1.record_year IS 'The reporting year for this record';

-- Create gri306_2 table
CREATE TABLE IF NOT EXISTS gri306_2 (
    id BIGSERIAL PRIMARY KEY,
    is_active boolean DEFAULT true,
    approached_id bigint REFERENCES gri306_1(id),
    prevention_action varchar(255),
    verify_method varchar(255),
    collection_method varchar(255),
    record_year varchar(20),
    organization bigint REFERENCES organizations(id),
    created_by bigint REFERENCES user_locations(id),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    deleted_date timestamp with time zone
);

-- Indexes for gri306_2
CREATE INDEX IF NOT EXISTS idx_gri306_2_approached_id ON gri306_2(approached_id);
CREATE INDEX IF NOT EXISTS idx_gri306_2_organization ON gri306_2(organization);
CREATE INDEX IF NOT EXISTS idx_gri306_2_created_by ON gri306_2(created_by);

-- Comments for gri306_2
COMMENT ON TABLE gri306_2 IS 'Stores GRI 306-2 data: Management of significant waste-related impacts';
COMMENT ON COLUMN gri306_2.approached_id IS 'Reference to the related GRI 306-1 record';
COMMENT ON COLUMN gri306_2.prevention_action IS 'Actions taken to prevent waste generation';
COMMENT ON COLUMN gri306_2.verify_method IS 'Method used to verify waste management';
COMMENT ON COLUMN gri306_2.collection_method IS 'Method used for collecting waste';

-- Create gri306_3 table
CREATE TABLE IF NOT EXISTS gri306_3 (
    id BIGSERIAL PRIMARY KEY,
    is_active boolean DEFAULT true,
    spill_type varchar(255),
    surface_type varchar(255),
    location varchar(255),
    volume numeric,
    unit varchar(50),
    cleanup_cost numeric,
    record_year varchar(20),
    organization bigint REFERENCES organizations(id),
    created_by bigint REFERENCES user_locations(id),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    deleted_date timestamp with time zone
);

-- Indexes for gri306_3
CREATE INDEX IF NOT EXISTS idx_gri306_3_organization ON gri306_3(organization);
CREATE INDEX IF NOT EXISTS idx_gri306_3_created_by ON gri306_3(created_by);

-- Comments for gri306_3
COMMENT ON TABLE gri306_3 IS 'Stores GRI 306-3 data: Waste generated';
COMMENT ON COLUMN gri306_3.spill_type IS 'Type of spill or waste release';
COMMENT ON COLUMN gri306_3.surface_type IS 'Type of surface where spill occurred';
COMMENT ON COLUMN gri306_3.location IS 'Location of the spill or waste';
COMMENT ON COLUMN gri306_3.volume IS 'Volume of waste or spill';
COMMENT ON COLUMN gri306_3.cleanup_cost IS 'Cost associated with cleanup';

-- Create gri306_export table
CREATE TABLE IF NOT EXISTS gri306_export (
    id BIGSERIAL PRIMARY KEY,
    is_active boolean DEFAULT true,
    version integer,
    export_file_url text,
    record_year varchar(20),
    organization bigint REFERENCES organizations(id),
    created_by bigint REFERENCES user_locations(id),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    deleted_date timestamp with time zone
);

-- Indexes for gri306_export
CREATE INDEX IF NOT EXISTS idx_gri306_export_organization ON gri306_export(organization);
CREATE INDEX IF NOT EXISTS idx_gri306_export_created_by ON gri306_export(created_by);

-- Comments for gri306_export
COMMENT ON TABLE gri306_export IS 'Stores history of GRI 306 report exports';
COMMENT ON COLUMN gri306_export.version IS 'Version number of the export';
COMMENT ON COLUMN gri306_export.export_file_url IS 'URL to the exported file';
