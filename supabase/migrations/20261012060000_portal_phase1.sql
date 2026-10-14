-- Migration 6: Portal Phase 1 (Access code and reasoning cache)
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.clients
  ADD COLUMN IF NOT EXISTS portal_access_code text UNIQUE;

CREATE TABLE IF NOT EXISTS public.client_facing_reasoning_cache (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  reasoning   text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, property_id)
);

CREATE INDEX IF NOT EXISTS idx_client_facing_reasoning_client ON public.client_facing_reasoning_cache(client_id);

COMMIT;
