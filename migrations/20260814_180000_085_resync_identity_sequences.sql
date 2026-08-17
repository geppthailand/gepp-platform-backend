-- ============================================================================
-- Migration: re-sync identity sequences that seed data left behind
-- Date: 2026-08-14
-- Description: Reference tables were bulk-loaded with explicit ids (banks,
--              currencies, location_*, material_categories, main_materials,
--              material_images, ...). Inserting an explicit id does NOT advance
--              the table's sequence, so every one of those sequences is still
--              parked at its start value with is_called = false.
--
--              The consequence only shows up the first time the application
--              inserts a row *without* an id: nextval() hands back 1, which is
--              already taken, and the insert dies with
--
--                duplicate key value violates unique constraint
--                "material_images_pkey"  DETAIL: Key (id)=(1) already exists.
--
--              That is what a backoffice material edit hit once image uploads
--              started working — the row had never been reachable before, so the
--              latent desync had never been exercised. 12 sequences were behind
--              in the same way; three of them (material_images, main_materials,
--              material_categories) sit directly under admin CRUD.
--
--              Fixed generically rather than by listing table names, because the
--              seed process that caused this will cause it again for the next
--              reference table somebody loads.
--
-- Safety: only ever RAISES a sequence, never lowers one, so it cannot hand out
--         an id that is already in use. Idempotent — re-running is a no-op once
--         every sequence is ahead of its column's max. Reads no application data
--         beyond max(id) and writes no table rows.
-- ============================================================================

DO $$
DECLARE
    r            RECORD;
    v_max        BIGINT;
    v_last       BIGINT;
    v_is_called  BOOLEAN;
    v_next       BIGINT;
    v_fixed      INT := 0;
    v_checked    INT := 0;
BEGIN
    FOR r IN
        SELECT s.oid          AS seq_oid,
               s.relname      AS seq_name,
               n.nspname      AS schema_name,
               t.relname      AS table_name,
               a.attname      AS column_name
        FROM pg_class s
        JOIN pg_depend d
          ON d.objid = s.oid
         AND d.classid = 'pg_class'::regclass
         AND d.deptype IN ('a', 'i')          -- owned by a column (serial / identity)
        JOIN pg_class t     ON t.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE s.relkind = 'S'
          AND n.nspname = 'public'
          AND t.relkind = 'r'
        ORDER BY t.relname
    LOOP
        v_checked := v_checked + 1;

        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I.%I',
                       r.column_name, r.schema_name, r.table_name)
           INTO v_max;

        -- Work out what the sequence would actually hand out next. is_called must be
        -- read from the sequence itself: pg_sequence_last_value() returns NULL both
        -- for "never called" AND for "setval(..., false)", so it cannot tell an
        -- unfixed sequence from an already-fixed one — which made an earlier version
        -- of this migration re-report the same tables on every run.
        EXECUTE format('SELECT last_value, is_called FROM %I.%I', r.schema_name, r.seq_name)
           INTO v_last, v_is_called;
        v_next := CASE WHEN v_is_called THEN v_last + 1 ELSE v_last END;

        IF v_max > 0 AND v_next <= v_max THEN
            -- is_called = false, so the NEXT nextval() returns exactly v_max + 1.
            PERFORM setval(format('%I.%I', r.schema_name, r.seq_name), v_max + 1, false);
            v_fixed := v_fixed + 1;
            RAISE NOTICE 'resynced %.% -> next id %  (would have handed out %, max(%) = %)',
                r.schema_name, r.seq_name, v_max + 1, v_next, r.column_name, v_max;
        END IF;
    END LOOP;

    RAISE NOTICE 'sequence resync complete: % checked, % corrected', v_checked, v_fixed;
END
$$;
