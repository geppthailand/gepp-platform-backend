-- Migration: Add value_chain_position to gri306_1 table
-- Description: Adds a new column 'value_chain_position' to the 'gri306_1' table
-- Date: 2025-12-09 12:00:00

ALTER TABLE public.gri306_1
ADD COLUMN IF NOT EXISTS value_chain_position text;

-- Add comment for the new column
COMMENT ON COLUMN public.gri306_1.value_chain_position IS 'Position in the value chain where waste is generated (e.g. upstream, downstream, own_operation)';

