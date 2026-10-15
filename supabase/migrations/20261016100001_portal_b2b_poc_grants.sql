-- Migration: 20261016100001_portal_b2b_poc_grants.sql
-- Description: Revoke direct anon/authenticated column access on B2B POC & ROI columns

BEGIN;

-- Lock down column-level grants: ensure new columns are NOT granted to anon or authenticated
DO $$
DECLARE
    ci_legacy text[] := ARRAY['id', 'client_id', 'property_id', 'message', 'created_at', 'status', 'agent_reply'];
    sv_legacy text[] := ARRAY['id', 'client_id', 'property_id', 'scheduled_date', 'scheduled_time', 'status', 'confirmation_status', 'notes', 'created_at', 'updated_at', 'agent_id', 'source'];
    ci_valid text[] := ARRAY[]::text[];
    sv_valid text[] := ARRAY[]::text[];
    col text;
BEGIN
    -- 1. client_inquiries: revoke table grant, re-grant only legacy columns
    REVOKE SELECT ON public.client_inquiries FROM anon, authenticated;
    FOR col IN SELECT unnest(ci_legacy)
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'client_inquiries' AND column_name = col) THEN
            ci_valid := array_append(ci_valid, quote_ident(col));
        END IF;
    END LOOP;
    IF array_length(ci_valid, 1) > 0 THEN
        EXECUTE format('GRANT SELECT (%s) ON public.client_inquiries TO anon, authenticated;', array_to_string(ci_valid, ', '));
    END IF;

    -- 2. scheduled_viewings: revoke table grant, re-grant only legacy columns
    REVOKE SELECT ON public.scheduled_viewings FROM anon, authenticated;
    FOR col IN SELECT unnest(sv_legacy)
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'scheduled_viewings' AND column_name = col) THEN
            sv_valid := array_append(sv_valid, quote_ident(col));
        END IF;
    END LOOP;
    IF array_length(sv_valid, 1) > 0 THEN
        EXECUTE format('GRANT SELECT (%s) ON public.scheduled_viewings TO anon, authenticated;', array_to_string(sv_valid, ', '));
    END IF;
END $$;

-- Service role full access
GRANT ALL ON TABLE public.client_inquiries TO service_role;
GRANT ALL ON TABLE public.clients TO service_role;
GRANT ALL ON TABLE public.scheduled_viewings TO service_role;

COMMIT;
