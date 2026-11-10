-- Migration: 20261110090000_supplier_quotes.sql
-- Description: Tables for simulated supplier quote agent (rep console only)

-- 1. Table: supplier_quote_requests
CREATE TABLE IF NOT EXISTS public.supplier_quote_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id uuid,
    client_id uuid REFERENCES public.clients(id) ON DELETE CASCADE,
    property_id uuid REFERENCES public.properties(id) ON DELETE CASCADE,
    kind text CHECK (kind IN ('quote', 'requote')),
    status text CHECK (status IN ('draft', 'sent', 'quoted', 'failed', 'cancelled')),
    draft_subject text,
    draft_body text,
    market_price_myr numeric CHECK (market_price_myr > 0),
    sent_at timestamptz,
    reply_due_at timestamptz,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_quote_requests_agent_status ON public.supplier_quote_requests (agent_id, status);
CREATE INDEX IF NOT EXISTS idx_supplier_quote_requests_client_property ON public.supplier_quote_requests (client_id, property_id);

-- 2. Table: supplier_quotes
CREATE TABLE IF NOT EXISTS public.supplier_quotes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid REFERENCES public.supplier_quote_requests(id) ON DELETE SET NULL,
    agent_id uuid,
    client_id uuid,
    property_id uuid,
    price_myr numeric NOT NULL CHECK (price_myr > 0),
    lead_time_weeks integer,
    terms text,
    source_text text NOT NULL,
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    is_simulated boolean NOT NULL DEFAULT true CHECK (is_simulated),
    superseded_by uuid REFERENCES public.supplier_quotes(id) ON DELETE SET NULL,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_quotes_client_property ON public.supplier_quotes (client_id, property_id);

-- 3. Table: agent_activity
CREATE TABLE IF NOT EXISTS public.agent_activity (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id uuid,
    kind text NOT NULL,
    summary text NOT NULL,
    ref_id uuid,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_activity_agent_created ON public.agent_activity (agent_id, created_at DESC);

-- 4. Enable RLS and Lock Down Public Grants (no access for portal / anon / authenticated; service_role only)
ALTER TABLE public.supplier_quote_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.supplier_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_activity ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.supplier_quote_requests FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.supplier_quotes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.agent_activity FROM PUBLIC, anon, authenticated;

GRANT ALL ON TABLE public.supplier_quote_requests TO service_role;
GRANT ALL ON TABLE public.supplier_quotes TO service_role;
GRANT ALL ON TABLE public.agent_activity TO service_role;

