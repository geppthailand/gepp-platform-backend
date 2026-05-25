-- ============================================================
-- Fix reward_point_transactions.unit historical data
-- Date: 2026-05-13
-- Purpose: Bug fix — claim_service.py was storing activity_material.name
--          (e.g. "PET", "ใช้ถุงผ้า") in the `unit` column instead of the
--          measurement unit ('kg' / 'times'). This breaks the rank system
--          (_is_weight_unit() in redeem_service.py) — users stay at Lv 1
--          forever because their kg never accumulates.
-- Fix:     Backfill `unit` from the joined activity_material's type.
--          The code fix (going forward) is in claim_service.py:253.
-- ============================================================

UPDATE reward_point_transactions AS rpt
SET unit = CASE
    WHEN ram.type = 'activity' THEN 'times'
    ELSE 'kg'
  END
FROM reward_activity_materials AS ram
WHERE rpt.reward_activity_materials_id = ram.id
  AND rpt.reference_type = 'claim'
  AND (rpt.unit IS NULL OR rpt.unit NOT IN ('kg', 'times'));
