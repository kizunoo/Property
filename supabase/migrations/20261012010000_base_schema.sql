-- Migration 1: Base Schema
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.properties (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  address text NOT NULL,
  neighborhood text NOT NULL,
  property_value numeric NOT NULL,
  image_url text
);

ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS image_url text;

CREATE TABLE IF NOT EXISTS public.clients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  stated_budget numeric NOT NULL,
  preferred_neighborhood text NOT NULL,
  past_viewings integer NOT NULL DEFAULT 0,
  last_known_tier text
);

ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS last_known_tier text;

CREATE TABLE IF NOT EXISTS public.pipeline_evaluations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  ai_probability numeric NOT NULL,
  expected_value numeric NOT NULL,
  segment_tier text NOT NULL CHECK (segment_tier IN ('TIER_1', 'TIER_2', 'TIER_3')),
  UNIQUE (client_id, property_id)
);

CREATE TABLE IF NOT EXISTS public.signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type text NOT NULL,
  client_id uuid REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id uuid REFERENCES public.properties(id) ON DELETE SET NULL,
  message text NOT NULL,
  dismissed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signals_client_id ON public.signals(client_id);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON public.signals(created_at DESC);

COMMIT;
