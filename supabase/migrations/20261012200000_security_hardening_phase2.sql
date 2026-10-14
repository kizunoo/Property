-- Migration 20: Security Hardening Phase 2
-- Revokes mutation privileges across all public tables, locks down internal tables,
-- removes wide-open policies, restricts authenticated client access, and adds verification helpers.
BEGIN;

-- 1. Revoke all mutation privileges on all public tables from anon and authenticated
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
  ON ALL TABLES IN SCHEMA public 
  FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public 
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
  ON TABLES FROM anon, authenticated;

-- 2. Drop overly permissive scheduled_viewings policies and restrict to service_role
DROP POLICY IF EXISTS "Allow all for anon and authenticated" ON public.scheduled_viewings;
DROP POLICY IF EXISTS "Allow all for authenticated"          ON public.scheduled_viewings;
DROP POLICY IF EXISTS "Service role full access on scheduled_viewings" ON public.scheduled_viewings;

CREATE POLICY "Service role full access on scheduled_viewings"
  ON public.scheduled_viewings FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- 3. Lock down tables not read directly by browser
ALTER TABLE IF EXISTS public.portal_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.invite_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.reasoning_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_facing_reasoning_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.model_training_runs ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    tbl text;
    internal_tables text[] := ARRAY[
        'portal_sessions',
        'client_accounts',
        'invite_drafts',
        'reasoning_cache',
        'client_facing_reasoning_cache',
        'whatsapp_conversations',
        'model_training_runs'
    ];
BEGIN
    FOR tbl IN SELECT unnest(internal_tables)
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated;', tbl);
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I;', 'Service role full access on ' || tbl, tbl);
            EXECUTE format('CREATE POLICY %I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true);', 'Service role full access on ' || tbl, tbl);
        END IF;
    END LOOP;
END $$;

-- 4. Restrict authenticated role on clients table:
-- Revoke table-level grant and apply dynamic column whitelist (identical to anon).
-- Explicitly omits portal_access_code and whatsapp_number.
DO $$
DECLARE
    v_whitelist TEXT[] := ARRAY[
        'id',
        'name',
        'stated_budget',
        'preferred_neighborhood',
        'past_viewings',
        'financing_status',
        'move_in_timeline',
        'property_type_preference',
        'secondary_neighborhood',
        'agent_notes',
        'assigned_agent_id',
        'relationship_stage',
        'source',
        'created_at',
        'updated_at'
    ];
    col TEXT;
    v_existing TEXT[] := ARRAY[]::TEXT[];
    v_skipped  TEXT[] := ARRAY[]::TEXT[];
BEGIN
    REVOKE ALL ON public.clients FROM authenticated;

    FOR col IN SELECT unnest(v_whitelist)
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'clients'
              AND column_name  = col
        ) THEN
            v_existing := array_append(v_existing, quote_ident(col));
        ELSE
            v_skipped := array_append(v_skipped, col);
        END IF;
    END LOOP;

    IF array_length(v_existing, 1) > 0 THEN
        EXECUTE format('GRANT SELECT (%s) ON public.clients TO authenticated;', array_to_string(v_existing, ', '));
        RAISE NOTICE 'Granted SELECT on public.clients to authenticated for columns: %', array_to_string(v_existing, ', ');
    END IF;

    IF array_length(v_skipped, 1) > 0 THEN
        RAISE NOTICE 'Skipped granting non-existent columns on public.clients to authenticated: %', array_to_string(v_skipped, ', ');
    END IF;
END $$;

-- 5. Verification helpers (service_role only)
CREATE OR REPLACE FUNCTION public.get_role_table_privileges()
RETURNS TABLE (
    table_name text,
    grantee text,
    privilege_type text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT r.table_name::text, r.grantee::text, r.privilege_type::text
    FROM information_schema.role_table_grants r
    WHERE r.table_schema = 'public'
      AND r.grantee IN ('anon', 'authenticated');
$$;

REVOKE EXECUTE ON FUNCTION public.get_role_table_privileges() FROM public, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.get_role_table_privileges() TO service_role;

COMMIT;
