-- Migration 7: Portal Phase 2 (Estimated savings & client inquiries)
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS estimated_annual_savings numeric;

CREATE TABLE IF NOT EXISTS public.client_inquiries (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  message     text NOT NULL,
  status      text NOT NULL DEFAULT 'open',
  agent_reply text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  replied_at  timestamptz
);

CREATE INDEX IF NOT EXISTS client_inquiries_client_id_idx ON public.client_inquiries(client_id);
CREATE INDEX IF NOT EXISTS client_inquiries_property_id_idx ON public.client_inquiries(property_id);

COMMIT;
