-- Migration: Fix transactions.weight_kg and transaction_records.origin_weight_kg
-- Date: 2026-03-13
-- Description: Recalculate origin_weight_kg = origin_quantity * materials.unit_weight
--              and transactions.weight_kg = SUM(records.origin_weight_kg)

-- Step 1: Recalculate ALL transaction_records.origin_weight_kg
UPDATE transaction_records tr
SET origin_weight_kg = ROUND(tr.origin_quantity * m.unit_weight, 3),
    updated_date = NOW()
FROM materials m
WHERE tr.material_id = m.id
  AND tr.deleted_date IS NULL
  AND m.unit_weight > 0
  AND tr.origin_weight_kg IS DISTINCT FROM ROUND(tr.origin_quantity * m.unit_weight, 3);

-- Step 2: Recalculate ALL transactions.weight_kg from their records
UPDATE transactions t
SET weight_kg = sub.total_weight,
    updated_date = NOW()
FROM (
    SELECT tr.created_transaction_id AS tx_id,
           ROUND(COALESCE(SUM(tr.origin_weight_kg), 0), 3) AS total_weight
    FROM transaction_records tr
    WHERE tr.deleted_date IS NULL
    GROUP BY tr.created_transaction_id
) sub
WHERE t.id = sub.tx_id
  AND t.deleted_date IS NULL
  AND t.weight_kg IS DISTINCT FROM sub.total_weight;
