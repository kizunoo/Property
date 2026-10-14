-- Migration 10: Property Price History
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.property_price_history (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  old_value   numeric NOT NULL,
  new_value   numeric NOT NULL,
  change_pct  numeric NOT NULL,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_property_price_history_property_id
  ON public.property_price_history(property_id, changed_at ASC);

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS last_price_change_at  timestamptz,
  ADD COLUMN IF NOT EXISTS last_price_change_pct numeric;

COMMIT;
