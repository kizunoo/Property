-- Migration 5: Scheduled viewings table, trigger, and base policy
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.scheduled_viewings (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id           uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id         uuid NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  scheduled_at        timestamptz NOT NULL,
  status              text NOT NULL DEFAULT 'upcoming'
                        CHECK (status IN ('upcoming', 'completed', 'cancelled')),
  cancellation_reason text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.scheduled_viewings ADD COLUMN IF NOT EXISTS cancellation_reason text;

CREATE INDEX IF NOT EXISTS idx_scheduled_viewings_status ON public.scheduled_viewings(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_viewings_client_id ON public.scheduled_viewings(client_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_viewings_property_id ON public.scheduled_viewings(property_id);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  new.updated_at := now();
  RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS trg_scheduled_viewings_updated_at ON public.scheduled_viewings;
CREATE TRIGGER trg_scheduled_viewings_updated_at
  BEFORE UPDATE ON public.scheduled_viewings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.scheduled_viewings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for anon and authenticated" ON public.scheduled_viewings;
CREATE POLICY "Allow all for anon and authenticated"
  ON public.scheduled_viewings
  FOR ALL
  TO anon, authenticated
  USING (true)
  WITH CHECK (true);

COMMIT;
