-- ==============================================================================
-- Security Hardening Script for Supabase
-- Addresses vulnerabilities identified during Anon Key Security Probe.
-- SAFE TO RE-RUN: uses IF EXISTS / IF NOT EXISTS guards throughout.
-- Run in Supabase SQL Editor → New Query.
-- ==============================================================================


-- ────────────────────────────────────────────────────────────────────────────
-- 1. Revoke write / mutation privileges across all public tables
-- ────────────────────────────────────────────────────────────────────────────
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public
  FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLES FROM anon, authenticated;


-- ────────────────────────────────────────────────────────────────────────────
-- 2. Lock down tables the browser does not read directly
-- ────────────────────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS public.portal_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.invite_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.reasoning_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_facing_reasoning_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_contact_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_slot_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.whatsapp_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_inquiries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.model_training_runs ENABLE ROW LEVEL SECURITY;

-- Revoke all table-level access from anon and authenticated on internal tables
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
        'whatsapp_messages',
        'whatsapp_contact_state',
        'whatsapp_slot_offers',
        'whatsapp_reminders',
        'client_inquiries',
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
        END IF;
    END LOOP;
END $$;

-- Drop legacy permissive policies and ensure service_role full access
DROP POLICY IF EXISTS "Allow all for anon and authenticated"           ON public.whatsapp_messages;
DROP POLICY IF EXISTS "Public insert on whatsapp_messages"             ON public.whatsapp_messages;
DROP POLICY IF EXISTS "Service role full access on whatsapp_messages"  ON public.whatsapp_messages;
CREATE POLICY "Service role full access on whatsapp_messages"
  ON public.whatsapp_messages FOR ALL TO service_role
  USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow all for anon and authenticated"           ON public.client_inquiries;
DROP POLICY IF EXISTS "Service role full access on client_inquiries"   ON public.client_inquiries;
CREATE POLICY "Service role full access on client_inquiries"
  ON public.client_inquiries FOR ALL TO service_role
  USING (true) WITH CHECK (true);

DO $$
DECLARE
    tbl text;
    policy_tables text[] := ARRAY[
        'portal_sessions',
        'client_accounts',
        'invite_drafts',
        'reasoning_cache',
        'client_facing_reasoning_cache',
        'whatsapp_conversations',
        'whatsapp_contact_state',
        'model_training_runs'
    ];
BEGIN
    FOR tbl IN SELECT unnest(policy_tables)
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I;', 'Service role full access on ' || tbl, tbl);
            EXECUTE format('CREATE POLICY %I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true);', 'Service role full access on ' || tbl, tbl);
        END IF;
    END LOOP;
END $$;


-- ────────────────────────────────────────────────────────────────────────────
-- 3. scheduled_viewings — drop wide-open policy and restrict to service_role
-- ────────────────────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS public.scheduled_viewings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated" ON public.scheduled_viewings;
DROP POLICY IF EXISTS "Allow all for authenticated"          ON public.scheduled_viewings;
DROP POLICY IF EXISTS "Service role full access on scheduled_viewings" ON public.scheduled_viewings;

CREATE POLICY "Service role full access on scheduled_viewings"
  ON public.scheduled_viewings FOR ALL TO service_role
  USING (true) WITH CHECK (true);


-- ────────────────────────────────────────────────────────────────────────────
-- 4. signals table — authenticated read, service_role insert
-- ────────────────────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS public.signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated"  ON public.signals;
DROP POLICY IF EXISTS "Public insert on signals"              ON public.signals;
DROP POLICY IF EXISTS "Read signals for authenticated"        ON public.signals;
DROP POLICY IF EXISTS "Insert signals for service role"       ON public.signals;

CREATE POLICY "Read signals for authenticated"
  ON public.signals FOR SELECT TO authenticated USING (true);

CREATE POLICY "Insert signals for service role"
  ON public.signals FOR INSERT TO service_role WITH CHECK (true);


-- ────────────────────────────────────────────────────────────────────────────
-- 5. clients — revoke portal_access_code and whatsapp_number from anon & authenticated
-- In PostgreSQL, REVOKE SELECT (col) does nothing if role has a table-level SELECT grant.
-- The table-level grant must be revoked first from BOTH anon and authenticated,
-- then replaced with explicit column-level GRANTs for only the columns the dashboard reads.
-- Explicitly excludes portal_access_code and whatsapp_number.
-- ────────────────────────────────────────────────────────────────────────────
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
    -- Revoke all table-level access from both anon and authenticated
    REVOKE ALL ON public.clients FROM anon, authenticated;

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
        EXECUTE format('GRANT SELECT (%s) ON public.clients TO anon, authenticated;', array_to_string(v_existing, ', '));
        RAISE NOTICE 'Granted SELECT on public.clients to anon and authenticated for columns: %', array_to_string(v_existing, ', ');
    END IF;

    IF array_length(v_skipped, 1) > 0 THEN
        RAISE NOTICE 'Skipped granting non-existent columns on public.clients: %', array_to_string(v_skipped, ', ');
    END IF;
END $$;


-- ────────────────────────────────────────────────────────────────────────────
-- 6. Revoke public execute on RPC functions
-- ────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'claim_and_book_slot_offer'
    ) THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) FROM public, anon, authenticated;';
        EXECUTE 'GRANT  EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) TO service_role;';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'claim_and_lock_pending_reminders'
    ) THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) FROM public, anon, authenticated;';
        EXECUTE 'GRANT  EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) TO service_role;';
    END IF;
END $$;


-- ────────────────────────────────────────────────────────────────────────────
-- 7. Verification helpers (service_role only)
-- ────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.check_column_privilege(
    p_role      TEXT,
    p_table     TEXT,
    p_column    TEXT,
    p_privilege TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN has_column_privilege(p_role, 'public.' || quote_ident(p_table), p_column, p_privilege);
EXCEPTION
    WHEN undefined_column THEN
        RETURN FALSE;
    WHEN undefined_table THEN
        RETURN FALSE;
    WHEN others THEN
        RETURN FALSE;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.check_column_privilege(TEXT, TEXT, TEXT, TEXT) FROM public, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.check_column_privilege(TEXT, TEXT, TEXT, TEXT) TO service_role;

-- Table privilege inspector for scripts/verify_anon_security.py
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
