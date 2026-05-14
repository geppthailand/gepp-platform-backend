-- ============================================================
-- Backfill default EF citations on existing esg_records
-- ============================================================
-- Records created before the EF-citation feature shipped have
-- NULL source_name / source_url. This SQL fills them in from the
-- per-Scope-3-category default table so the data warehouse
-- popover always shows a verifiable reference.
--
-- The Python equivalent (`SCOPE3_DEFAULT_CITATIONS`) is the
-- source of truth — keep them in sync if you change either side.
-- ============================================================

UPDATE esg_records SET
    ghg_source_name = COALESCE(ghg_source_name, m.source_name),
    ghg_source_url  = COALESCE(ghg_source_url,  m.source_url)
FROM (
    VALUES
      (1,  'GHG Protocol — Scope 3 Calculation Guidance (Cat 1: Purchased goods and services, spend-based method)', 'https://ghgprotocol.org/scope-3-calculation-guidance-2'),
      (2,  'GHG Protocol — Scope 3 Calculation Guidance (Cat 2: Capital goods)',                                     'https://ghgprotocol.org/scope-3-calculation-guidance-2'),
      (3,  'DEFRA 2024 GHG Conversion Factors — Well-to-tank fuels & T&D losses',                                    'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (4,  'DEFRA 2024 GHG Conversion Factors — Freight (tonne-km)',                                                 'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (5,  'DEFRA 2024 GHG Conversion Factors — Waste disposal',                                                     'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (6,  'DEFRA 2024 GHG Conversion Factors — Business travel (passenger.km)',                                     'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (7,  'DEFRA 2024 GHG Conversion Factors — Passenger transport (passenger.km)',                                 'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (8,  'TGO Thailand Grid Emission Factor (purchased electricity)',                                              'https://ghgreduction.tgo.or.th/'),
      (9,  'DEFRA 2024 GHG Conversion Factors — Freight (tonne-km)',                                                 'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (10, 'GHG Protocol — Scope 3 Calculation Guidance (Cat 10: Processing of sold products)',                      'https://ghgprotocol.org/scope-3-calculation-guidance-2'),
      (11, 'GHG Protocol — Scope 3 Calculation Guidance (Cat 11: Use of sold products)',                             'https://ghgprotocol.org/scope-3-calculation-guidance-2'),
      (12, 'DEFRA 2024 GHG Conversion Factors — Waste disposal (end-of-life)',                                       'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting'),
      (13, 'TGO Thailand Grid Emission Factor (purchased electricity)',                                              'https://ghgreduction.tgo.or.th/'),
      (14, 'GHG Protocol — Scope 3 Calculation Guidance (Cat 14: Franchises)',                                       'https://ghgprotocol.org/scope-3-calculation-guidance-2'),
      (15, 'GHG Protocol — Scope 3 Calculation Guidance (Cat 15: Investments)',                                      'https://ghgprotocol.org/scope-3-calculation-guidance-2')
) AS m(scope3_cat, source_name, source_url)
WHERE esg_records.scope3_category_id = m.scope3_cat
  AND (esg_records.ghg_source_name IS NULL OR esg_records.ghg_source_url IS NULL);
