-- Migration 19: Security Hardening (Phase 1)
-- Safe to re-run: uses dynamic DO block and IF EXISTS guards
BEGIN;

ALTER TABLE public.signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated"  ON public.signals;
DROP POLICY IF EXISTS "Public insert on signals"              ON public.signals;
DROP POLICY IF EXISTS "Read signals for authenticated"        ON public.signals;
DROP POLICY IF EXISTS "Insert signals for service role"       ON public.signals;

CREATE POLICY "Read signals for authenticated"
  ON public.signals FOR SELECT TO authenticated USING (true);

CREATE POLICY "Insert signals for service role"
  ON public.signals FOR INSERT TO service_role WITH CHECK (true);

ALTER TABLE public.whatsapp_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated"           ON public.whatsapp_messages;
DROP POLICY IF EXISTS "Public insert on whatsapp_messages"             ON public.whatsapp_messages;
DROP POLICY IF EXISTS "Service role full access on whatsapp_messages"  ON public.whatsapp_messages;

CREATE POLICY "Service role full access on whatsapp_messages"
  ON public.whatsapp_messages FOR ALL TO service_role
  USING (true) WITH CHECK (true);

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
    REVOKE SELECT ON public.clients FROM anon;

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
        EXECUTE format('GRANT SELECT (%s) ON public.clients TO anon;', array_to_string(v_existing, ', '));
        RAISE NOTICE 'Granted SELECT on public.clients to anon for columns: %', array_to_string(v_existing, ', ');
    END IF;

    IF array_length(v_skipped, 1) > 0 THEN
        RAISE NOTICE 'Skipped granting non-existent columns on public.clients: %', array_to_string(v_skipped, ', ');
    END IF;
END $$;

ALTER TABLE public.client_inquiries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated"            ON public.client_inquiries;
DROP POLICY IF EXISTS "Service role full access on client_inquiries"   ON public.client_inquiries;

CREATE POLICY "Service role full access on client_inquiries"
  ON public.client_inquiries FOR ALL TO service_role
  USING (true) WITH CHECK (true);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'claim_and_book_slot_offer'
    ) THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) FROM public, anon;';
        EXECUTE 'GRANT  EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) TO service_role;';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'claim_and_lock_pending_reminders'
    ) THEN
        EXECUTE 'REVOKE EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) FROM public, anon;';
        EXECUTE 'GRANT  EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) TO service_role;';
    END IF;
END $$;

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

COMMIT;
