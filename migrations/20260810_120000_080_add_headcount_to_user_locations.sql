-- ============================================================================
-- Migration: Add headcount to user_locations
-- Date: 2026-08-10
-- Description: Number of people AT THIS NODE ONLY — deliberately not a subtree
--              total. The effective headcount of any node is its own value plus
--              the own-values of every descendant, so a node's stored value must
--              never already include its children or the rollup double-counts.
--              (The UI label says "excluding sub-levels" for exactly this reason.)
--
--              Powers the "Waste per Head" card on Reports → Overview: total waste
--              of the filtered locations divided by the rolled-up headcount of the
--              same subtree. A subtree with no value anywhere reports N/A rather
--              than 0, so "not filled in yet" never reads as "nobody works here".
--
--              NOT reusing user_locations.population: that column is semantically
--              overloaded (1,355 rows constant 1 from an EPR import, plus
--              district-level figures up to 228,000) and has no write path.
--              population is left untouched.
--
--              NULL = not filled in. No DEFAULT, because 0 people is a meaningful
--              value distinct from "unknown" and the N/A rule depends on telling
--              them apart.
-- ============================================================================

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS headcount INTEGER;

COMMENT ON COLUMN user_locations.headcount IS
    'People at this node only, excluding sub-levels. NULL = not set. Effective headcount = own + sum of all descendants.';

-- Reports sum this across a subtree for every overview request; the partial index
-- keeps that to the rows that actually carry a value.
CREATE INDEX IF NOT EXISTS idx_user_locations_headcount
    ON user_locations (organization_id, id)
    WHERE headcount IS NOT NULL;
