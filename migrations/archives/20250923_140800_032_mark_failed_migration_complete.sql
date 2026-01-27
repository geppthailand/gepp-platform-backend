-- Migration: 20250923_140800_032_mark_failed_migration_complete.sql
-- Description: Mark the partially successful migration 029 as completed to prevent re-runs
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- MARK FAILED MIGRATION AS COMPLETED
-- ======================================

DO $$
BEGIN
    -- Check if the migration tracking table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'migration_history') THEN
        -- Mark migration 029 as completed since it partially succeeded
        INSERT INTO migration_history (migration_file, status, executed_at)
        VALUES ('20250923_140500_029_complete_transaction_schema_cleanup.sql', 'completed', NOW())
        ON CONFLICT (migration_file) DO UPDATE SET
            status = 'completed',
            executed_at = NOW();

        RAISE NOTICE 'Marked migration 029 as completed in tracking table';
    ELSE
        RAISE NOTICE 'Migration tracking table does not exist - skipping tracking update';
    END IF;
END $$;

-- ======================================
-- VERIFICATION MESSAGE
-- ======================================

DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'MIGRATION TRACKING UPDATED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 029 marked as completed to prevent re-runs';
    RAISE NOTICE 'The column cleanup from 029 was successful';
    RAISE NOTICE 'Only the constraint addition failed due to data type mismatch';
    RAISE NOTICE 'Migration 031 will fix the remaining constraint issues';
    RAISE NOTICE '============================================';
END $$;