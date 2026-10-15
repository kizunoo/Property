-- Migration 20261015150000: Portal v2 Core Tables
-- Idempotent, safe to re-run

BEGIN;

CREATE TABLE IF NOT EXISTS public.portal_unit_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  contact_id uuid REFERENCES public.portal_contacts(id) ON DELETE SET NULL,
  interest text CHECK (interest IN ('interested', 'not_interested')),
  reason text CHECK (char_length(reason) <= 500),
  is_saved boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, property_id)
);

CREATE TABLE IF NOT EXISTS public.portal_quotes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  contact_id uuid REFERENCES public.portal_contacts(id) ON DELETE SET NULL,
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity BETWEEN 1 AND 1000),
  notes text CHECK (char_length(notes) <= 1000),
  status text NOT NULL DEFAULT 'requested'
    CHECK (status IN ('requested', 'sent', 'accepted', 'declined')),
  quoted_amount numeric(14,2) CHECK (quoted_amount IS NULL OR quoted_amount > 0),
  currency text NOT NULL DEFAULT 'MYR' CHECK (currency IN ('MYR', 'USD')),
  customer_note text,
  internal_notes text,
  valid_until date,
  requested_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  responded_at timestamptz,
  portal_response_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_quote_per_unit
  ON public.portal_quotes (client_id, property_id) WHERE status = 'requested';

CREATE TABLE IF NOT EXISTS public.inquiry_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inquiry_id uuid NOT NULL REFERENCES public.client_inquiries(id) ON DELETE CASCADE,
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  sender text NOT NULL CHECK (sender IN ('company', 'rep')),
  body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 4000),
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS inquiry_messages_inquiry_idx ON public.inquiry_messages(inquiry_id, created_at);

-- Idempotent backfill from client_inquiries
-- 1. Initial company inquiry message from client_inquiries.message
INSERT INTO public.inquiry_messages (inquiry_id, client_id, sender, body, read_at, created_at)
SELECT
  ci.id,
  ci.client_id,
  'company',
  ci.message,
  COALESCE(ci.replied_at, ci.created_at),
  ci.created_at
FROM public.client_inquiries ci
WHERE ci.message IS NOT NULL AND char_length(ci.message) >= 1
  AND NOT EXISTS (
    SELECT 1 FROM public.inquiry_messages im
    WHERE im.inquiry_id = ci.id AND im.sender = 'company' AND im.body = ci.message
  );

-- 2. Rep response message from client_inquiries.agent_reply (existing replies backfilled with read_at = null)
INSERT INTO public.inquiry_messages (inquiry_id, client_id, sender, body, read_at, created_at)
SELECT
  ci.id,
  ci.client_id,
  'rep',
  ci.agent_reply,
  NULL,
  COALESCE(ci.replied_at, ci.created_at)
FROM public.client_inquiries ci
WHERE ci.agent_reply IS NOT NULL AND char_length(ci.agent_reply) >= 1
  AND NOT EXISTS (
    SELECT 1 FROM public.inquiry_messages im
    WHERE im.inquiry_id = ci.id AND im.sender = 'rep' AND im.body = ci.agent_reply
  );

CREATE TABLE IF NOT EXISTS public.portal_profile_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  contact_id uuid REFERENCES public.portal_contacts(id) ON DELETE SET NULL,
  field text NOT NULL,
  old_value text,
  new_value text,
  changed_at timestamptz NOT NULL DEFAULT now()
);

-- RLS & Security Hardening: FastAPI service_role access only
ALTER TABLE public.portal_unit_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.portal_unit_feedback FROM anon, authenticated;
GRANT ALL ON TABLE public.portal_unit_feedback TO service_role;

ALTER TABLE public.portal_quotes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.portal_quotes FROM anon, authenticated;
GRANT ALL ON TABLE public.portal_quotes TO service_role;

ALTER TABLE public.inquiry_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.inquiry_messages FROM anon, authenticated;
GRANT ALL ON TABLE public.inquiry_messages TO service_role;

ALTER TABLE public.portal_profile_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.portal_profile_audit FROM anon, authenticated;
GRANT ALL ON TABLE public.portal_profile_audit TO service_role;

COMMIT;
