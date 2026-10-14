-- Migration 8: Relationship stages and invite drafts
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS relationship_stage text DEFAULT 'new'
  CHECK (relationship_stage IN ('new', 'contacted', 'viewing', 'negotiation', 'closed_won', 'closed_lost'));

CREATE TABLE IF NOT EXISTS public.invite_drafts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid REFERENCES public.properties(id) ON DELETE CASCADE,
  subject     text,
  body        text,
  sent_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.invite_drafts ADD COLUMN IF NOT EXISTS sent_at timestamptz;

COMMIT;
