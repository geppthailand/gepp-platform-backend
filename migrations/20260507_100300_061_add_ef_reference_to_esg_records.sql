-- ============================================================
-- Add EF (emission factor) citation columns to esg_records
-- ============================================================
-- The LIFF data-warehouse modal shows "How was this kgCO₂e
-- computed?" — the user needs a verifiable reference. The LLM is
-- now required to cite an authoritative source per record (TGO
-- Thailand, DEFRA UK, IPCC, EPA, IEA, etc.) along with the EF
-- value it used. We persist that here so:
--   • The popover can render it as a clickable link.
--   • An auditor can re-derive the kgCO₂e from the cited number.
-- ============================================================

ALTER TABLE esg_records
    ADD COLUMN IF NOT EXISTS ghg_source_name TEXT,        -- e.g. "DEFRA 2024 GHG Conversion Factors"
    ADD COLUMN IF NOT EXISTS ghg_source_url  TEXT,        -- a real, openable URL the LLM cited
    ADD COLUMN IF NOT EXISTS ghg_ef_value    NUMERIC(20,8),  -- numeric EF (e.g. 0.18000000)
    ADD COLUMN IF NOT EXISTS ghg_ef_unit     VARCHAR(60);    -- e.g. "kgCO2e/km"
