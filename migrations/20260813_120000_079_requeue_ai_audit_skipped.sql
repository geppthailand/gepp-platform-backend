-- Re-queue transactions that were skipped by the old per-project ai_audit
-- gate. That gate is gone (worker.process_transaction audits everything now),
-- but the already-skipped rows were marked done and would never be revisited.
--
-- Run AFTER deploying the gate removal — otherwise these get skipped again.

INSERT INTO epr_dedup_jobs (transaction_id, stage)
SELECT id, 'embedding'
FROM epr_transactions_embeded
WHERE status = 'skipped'
  AND flags->>'reason' = 'ai_audit_disabled'
  AND deleted_date IS NULL
ON CONFLICT (transaction_id, stage) DO UPDATE
SET status         = 'pending',
    attempts       = 0,
    started_date   = NULL,
    completed_date = NULL,
    last_error     = NULL;
